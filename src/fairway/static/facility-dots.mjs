import { mapEligible } from "./catalog-read.mjs";

// One persistent canvas path per eligible facility. Leaflet handles projection,
// viewport clipping and hit testing; pan/zoom never rebuilds the catalog layer.
export function createFacilityDots(L, map, onSelect, onCoincident) {
  const renderer = L.canvas({ padding: 0.25, tolerance: 4 });
  const layer = L.layerGroup().addTo(map);
  const markers = new Map();
  let source = null;
  let coincident = new Map();
  let active = null;
  let radius = null;
  const pointKey = (f) =>
    `${f.map_location.latitude},${f.map_location.longitude}`;
  const style = (selected) => ({
    radius: selected ? radius + 3 : radius,
    fillColor: "#216d4d",
    fillOpacity: selected ? 1 : 0.58,
    stroke: selected,
    color: "#e7b447",
    weight: 2,
    opacity: 1,
  });

  function update(records, selected) {
    const zoom = map.getZoom();
    const nextRadius = zoom >= 14 ? 4 : zoom >= 10 ? 3.25 : 2.5;
    const resized = radius !== nextRadius;
    radius = nextRadius;
    const refreshed = source !== records;
    if (refreshed) {
      source = records;
      const eligible = records.filter(mapEligible);
      const ids = new Set(eligible.map((f) => f.facility_id));
      coincident = new Map();
      for (const f of eligible) {
        const key = pointKey(f);
        const idsAtPoint = coincident.get(key) || [];
        idsAtPoint.push(f.facility_id);
        coincident.set(key, idsAtPoint);
      }
      for (const [id, marker] of markers) {
        if (!ids.has(id)) {
          layer.removeLayer(marker);
          markers.delete(id);
        }
      }
      for (const f of eligible) {
        const coordinates = [
          f.map_location.latitude,
          f.map_location.longitude,
        ];
        let marker = markers.get(f.facility_id);
        if (marker) marker.setLatLng(coordinates);
        else {
          marker = L.circleMarker(coordinates, {
            renderer,
            ...style(f.facility_id === selected),
            bubblingMouseEvents: false,
          });
          marker.on("click", () => {
            const ids = coincident.get(marker.facilityPointKey);
            if (ids?.length > 1) onCoincident(ids, marker.getLatLng());
            else onSelect(f.facility_id);
          });
          marker.addTo(layer);
          markers.set(f.facility_id, marker);
        }
        marker.facilityPointKey = pointKey(f);
      }
    }
    if (resized || refreshed)
      for (const [id, marker] of markers)
        marker.setStyle(style(id === selected));
    else if (active !== selected) {
      markers.get(active)?.setStyle(style(false));
      markers.get(selected)?.setStyle(style(true));
    }
    if (selected && (active !== selected || resized || refreshed))
      markers.get(selected)?.bringToFront();
    active = selected;
    return markers;
  }
  return { update };
}
