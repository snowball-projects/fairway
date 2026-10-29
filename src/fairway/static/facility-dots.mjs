import { mapEligible, recordLabel, cityLabel, accessLabel } from "./catalog-read.mjs";

// Individual paths share one canvas. A screen grid keeps hit testing local;
// the one DOM highlight can move without repainting the canvas underneath it.
export function createFacilityDots(L, map, onSelect, onCoincident) {
  const markers = new Map(), grid = new Map();
  let source = null, coincident = new Map(), active = null, radius = null;
  let hovered = null, tapped = null, pointerType = "mouse", lastClick = null;
  const cell = 16;
  const pointKey = f => `${f.map_location.latitude},${f.map_location.longitude}`;
  const highlight = document.createElement("span");
  highlight.className = "facility-hover";
  const tooltip = L.tooltip({direction:"top",offset:[0,-10],opacity:1,className:"facility-preview"});

  function preview(marker) {
    if(hovered === marker)return;
    hovered = marker;
    if(!marker) {
      highlight.remove();map.removeLayer(tooltip);
      return;
    }
    const record = marker.facilityRecord, content = document.createElement("div");
    const title = document.createElement("strong"), place = document.createElement("div"), facts = document.createElement("div");
    title.textContent = recordLabel(record);
    place.textContent = [cityLabel(record),record.state].filter(Boolean).join(", ");
    facts.textContent = [Number.isFinite(record.physical_holes)?`${record.physical_holes} holes`:"Holes not recorded",
      `${record.course_count} ${record.course_count===1?"course":"courses"}`,accessLabel(record.access)].join(" · ");
    content.append(title,place,facts);
    tooltip.setLatLng(marker.getLatLng()).setContent(content).addTo(map);
    highlight.style.width = highlight.style.height = `${2*radius}px`;
    L.DomUtil.setPosition(highlight,marker._point);
    map.getPanes().overlayPane.append(highlight);
  }
  function indexPoints() {
    grid.clear();
    for(const marker of markers.values()) {
      const p = marker._point;
      const key = `${Math.floor(p.x/cell)},${Math.floor(p.y/cell)}`;
      const bucket = grid.get(key) || [];
      bucket.push(marker);grid.set(key,bucket);
    }
  }
  function hit(point) {
    const x = Math.floor(point.x/cell), y = Math.floor(point.y/cell);
    let found;
    for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++)
      for(const marker of grid.get(`${x+dx},${y+dy}`)||[])
        if(marker._containsPoint(point)&&(!found||marker.facilityRecord.facility_id===active||found.facilityRecord.facility_id!==active&&marker.dotOrder>found.dotOrder))found=marker;
    return found;
  }
  const DotCanvas = L.Canvas.extend({
    _updatePaths() {
      L.Canvas.prototype._updatePaths.call(this);
      indexPoints();
    },
    _handleMouseHover(event,point) {
      if(pointerType==="touch")return;
      const marker = hit(point);
      if(marker!==this._hoveredLayer||marker!==hovered) {
        this._handleMouseOut(event);
        if(marker) {
          L.DomUtil.addClass(this._container,"leaflet-interactive");
          this._hoveredLayer=marker;
        }
        preview(marker);
      }
    },
    _handleMouseOut(event) {
      L.Canvas.prototype._handleMouseOut.call(this,event);
      if(pointerType!=="touch")preview(null);
    },
    _onClick(event) {
      // A second tap can recenter the map before Leaflet synthesizes dblclick
      // at the old screen position. Consume that follow-up at its original dot.
      if(event.type==="dblclick"&&lastClick&&Date.now()-lastClick.at<500&&Math.hypot(event.clientX-lastClick.x,event.clientY-lastClick.y)<16) {
        L.DomEvent.stop(event);return;
      }
      const marker=hit(this._map.mouseEventToLayerPoint(event));
      if(marker&&this._map._draggableMoved(marker))return;
      this._fireEvent(marker?[marker]:false,event);
    },
  });
  const renderer = new DotCanvas({padding:0.25,tolerance:0});
  const layer = L.layerGroup().addTo(map);
  const style = selected => ({
    radius: selected ? radius+3 : radius,
    fillColor:"#216d4d",fillOpacity:selected?1:0.58,
    stroke:true,color:selected?"#e7b447":"#fff",weight:selected?2:1.5,opacity:1,
  });
  map.getContainer().addEventListener("pointerdown",event=>{pointerType=event.pointerType;});
  map.getContainer().addEventListener("pointermove",event=>{if(event.pointerType!=="touch")pointerType=event.pointerType;});
  map.on("movestart zoomstart click",()=>{tapped=null;preview(null);});
  document.addEventListener("keydown",event=>{if(event.key==="Escape"){tapped=null;preview(null);}});

  function update(records,selected) {
    const zoom = map.getZoom(), nextRadius = zoom>=14?6:zoom>=10?5:zoom>=6?4:3.5;
    const resized = radius!==nextRadius, refreshed = source!==records;
    radius=nextRadius;
    if(refreshed) {
      source=records;
      const eligible=records.filter(mapEligible), ids=new Set(eligible.map(f=>f.facility_id));
      coincident=new Map();
      for(const f of eligible) {
        const key=pointKey(f), idsAtPoint=coincident.get(key)||[];
        idsAtPoint.push(f.facility_id);coincident.set(key,idsAtPoint);
      }
      for(const [id,marker] of markers)if(!ids.has(id)){layer.removeLayer(marker);markers.delete(id);}
      let order=0;
      for(const f of eligible) {
        const coordinates=[f.map_location.latitude,f.map_location.longitude];
        let marker=markers.get(f.facility_id);
        if(marker)marker.setLatLng(coordinates);
        else {
          marker=L.circleMarker(coordinates,{renderer,...style(f.facility_id===selected),bubblingMouseEvents:false});
          marker.on("click",event=>{
            const touch=pointerType==="touch"||event?.originalEvent?.pointerType==="touch";
            if(touch&&tapped!==marker){tapped=marker;preview(marker);return;}
            tapped=null;preview(null);
            const original=event?.originalEvent;
            lastClick={at:Date.now(),x:original?.clientX,y:original?.clientY};
            const ids=coincident.get(marker.facilityPointKey);
            if(ids?.length>1)onCoincident(ids,marker.getLatLng());
            else onSelect(f.facility_id,marker.getLatLng());
          });
          marker.on("dblclick",()=>{});
          marker.addTo(layer);markers.set(f.facility_id,marker);
        }
        marker.facilityPointKey=pointKey(f);marker.facilityRecord=f;
        marker.dotOrder=order++;
      }
    }
    if(resized||refreshed)for(const [id,marker] of markers)marker.setStyle(style(id===selected));
    else if(active!==selected) {
      markers.get(active)?.setStyle(style(false));markers.get(selected)?.setStyle(style(true));
    }
    if(selected&&(active!==selected||resized||refreshed))markers.get(selected)?.bringToFront();
    active=selected;
    if(refreshed)indexPoints();
    return markers;
  }
  return {update};
}
