import { mapEligible, recordLabel, cityLabel, accessLabel } from "./catalog-read.mjs";

// Individual paths share one canvas. A screen grid keeps hit testing local;
// the one DOM highlight can move without repainting the canvas underneath it.
export function createFacilityDots(L, map, onSelect, onCoincident) {
  const markers = new Map(), grid = new Map();
  let source = null, coincident = new Map(), active = null, radius = null;
  let hovered = null, tapped = null, pointerType = "mouse", lastClick = null;
  const cell = 16;
  let indexedZoom=null, anchor=null;
  const pointKey = f => `${f.map_location.latitude},${f.map_location.longitude}`;
  const highlight = document.createElement("span");
  highlight.className = "facility-hover";
  const tooltip = L.tooltip({direction:"top",offset:[0,-10],opacity:1,className:"facility-preview"});
  const stamps=new Map();
  let stampFrame=null, drawFrame=null, painted=false;
  for(const base of [3.5,4,5,6])for(const selected of [false,true]) {
    const r=selected?base+3:base,size=2*(r+1),image=new Image();
    const stamp={image,size,bitmap:null};
    image.onload=async()=>{
      stamp.bitmap=await createImageBitmap(image);
      if(!renderer._map||stampFrame!==null)return;
      stampFrame=requestAnimationFrame(()=>{stampFrame=null;renderer._redraw();});
    };
    const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${size*devicePixelRatio}" height="${size*devicePixelRatio}" viewBox="0 0 ${size} ${size}"><circle cx="${r+1}" cy="${r+1}" r="${r}" fill="#216d4d" fill-opacity="${selected?1:0.58}" stroke="${selected?"#e7b447":"#fff"}" stroke-width="${selected?2:1.5}"/></svg>`;
    image.src=`data:image/svg+xml,${encodeURIComponent(svg)}`;
    stamps.set(`${r}:${selected}`,stamp);
  }

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
    if(indexedZoom===map.getZoom())return;
    indexedZoom=map.getZoom();grid.clear();
    const marker=markers.values().next().value;
    anchor=marker?{marker,x:marker._point.x,y:marker._point.y}:null;
    for(const marker of markers.values()) {
      const p = marker._point;
      const key = `${Math.floor(p.x/cell)},${Math.floor(p.y/cell)}`;
      const bucket = grid.get(key) || [];
      bucket.push(marker);grid.set(key,bucket);
    }
  }
  function hit(point) {
    if(!anchor)return;
    const x = Math.floor((point.x-anchor.marker._point.x+anchor.x)/cell);
    const y = Math.floor((point.y-anchor.marker._point.y+anchor.y)/cell);
    let found;
    for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++)
      for(const marker of grid.get(`${x+dx},${y+dy}`)||[])
        if(marker._containsPoint(point)&&(!found||marker.facilityRecord.facility_id===active||found.facilityRecord.facility_id!==active&&marker.dotOrder>found.dotOrder))found=marker;
    return found;
  }
  const DotCanvas = L.Canvas.extend({
    _draw() {
      if(drawFrame!==null)cancelAnimationFrame(drawFrame);
      const canvas=this,ctx=this._ctx,bounds=this._redrawBounds,incremental=painted;
      let order=this._drawFirst;
      const normal=stamps.get(`${radius}:false`),selected=stamps.get(`${radius+3}:true`);
      function paintDots() {
        drawFrame=null;
        if(!canvas._map)return;
        const start=performance.now();ctx.save();
        if(bounds) {
          const size=bounds.getSize();ctx.beginPath();ctx.rect(bounds.min.x,bounds.min.y,size.x,size.y);ctx.clip();
        }
        canvas._drawing=true;ctx.globalAlpha=1;
        while(order) {
          const marker=order.layer;order=order.next;
          if(!marker._empty()&&(!bounds||marker._pxBounds.intersects(bounds))) {
            const {bitmap,size}=marker.facilityRecord?.facility_id===active?selected:normal,p=marker._point;
            if(bitmap)ctx.drawImage(bitmap,p.x-size/2,p.y-size/2,size,size);
            else {L.Canvas.prototype._updateCircle.call(canvas,marker);ctx.globalAlpha=1;}
          }
          if(incremental&&performance.now()-start>=4&&order) {
            drawFrame=requestAnimationFrame(paintDots);break;
          }
        }
        canvas._drawing=false;ctx.restore();
      }
      paintDots();
      if(this._drawFirst)painted=true;
    },
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
      source=records;indexedZoom=null;
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
    if(resized&&!refreshed) {
      for(const [id,marker] of markers) {
        marker._radius=marker.options.radius=id===selected?radius+3:radius;
        marker._updateBounds();
      }
    }
    if(active!==selected) {
      markers.get(active)?.setStyle(style(false));markers.get(selected)?.setStyle(style(true));
    }
    if(selected&&(active!==selected||resized||refreshed))markers.get(selected)?.bringToFront();
    active=selected;
    if(refreshed)indexPoints();
    return markers;
  }
  return {update};
}
