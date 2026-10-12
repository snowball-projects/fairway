import { located } from "./research-map/model.mjs";
export const publicPlay = (facility) =>
  facility.public_access === "public" ||
  (facility.public_access == null &&
    facility.courses?.some((c) => c.access === "public"));
export const mapEligible = (facility) =>
  Boolean(
    facility.id &&
      facility.name?.trim() &&
      publicPlay(facility) &&
      Number.isFinite(facility.physical_holes) &&
      facility.physical_holes > 0 &&
      located(facility) &&
      ["property_point", "reviewed_osm_point", "verified_entrance"].includes(
        facility.map_location.kind,
      ),
  );
export function catalogCounts(records) {
  const onMap = records.filter(mapEligible).length;
  return {
    total: records.length,
    onMap,
    pending: records.length - onMap,
    estimates: records.filter(
      (f) => located(f) && f.map_location.kind === "address_range_estimate",
    ).length,
  };
}
export function cityLabel(f) {
  const text = f.address?.text || "";
  const match = text.match(/,\s*([^,]+),\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?\s*$/i);
  return match ? match[1].trim() : null;
}
export function searchCatalog(records, states, query) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const results = states
    .filter((s) => s.id.toLowerCase() === q || s.name.toLowerCase().includes(q))
    .map((s) => ({
      kind: "state",
      id: s.id,
      label: `${s.name} (${s.id})`,
      state: s,
    }));
  const cities = new Map();
  for (const f of records) {
    const city = cityLabel(f);
    if (city) {
      const label = `${city}, ${f.state}`;
      if (label.toLowerCase().includes(q)) {
        const group = cities.get(label) || { kind: "city", label, records: [] };
        group.records.push(f);
        cities.set(label, group);
      }
    }
    if (`${f.name} ${city || ""} ${f.state}`.toLowerCase().includes(q))
      results.push({
        kind: "facility",
        id: f.id,
        label: f.name,
        subtitle: `${city ? city + ", " : ""}${f.state}`,
        facility: f,
      });
  }
  return [
    ...results.filter((r) => r.kind === "state"),
    ...cities.values(),
    ...results.filter((r) => r.kind === "facility"),
  ];
}
// Invert the existing Census display projection; these are state/county geometry,
// not invented facility polygons. Alaska's antimeridian is kept in one world copy.
export function unproject(x, y, state) {
  if (state === "AK") return [72 - (y - 435) / 6, (x - 25) / 4.5 - 180];
  if (state === "HI") return [23 - (y - 490) / 19, (x - 250) / 19 - 161];
  const rad = Math.PI / 180;
  const n = (Math.sin(29.5 * rad) + Math.sin(45.5 * rad)) / 2;
  const c = Math.cos(29.5 * rad) ** 2 + 2 * n * Math.sin(29.5 * rad);
  const rho0 = Math.sqrt(c - 2 * n * Math.sin(38 * rad)) / n;
  const px = (x - 510) / 1100,
    py = rho0 + (y - 270) / 1100;
  const rho = Math.hypot(px, py);
  return [
    Math.asin((c - (rho * n) ** 2) / (2 * n)) / rad,
    Math.atan2(px, py) / n / rad - 96,
  ];
}
export function shapeRings(shape) {
  return shape.d
    .split("M")
    .filter(Boolean)
    .map((part) =>
      [...part.matchAll(/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/g)].map((m) =>
        unproject(Number(m[1]), Number(m[2]), shape.state),
      ),
    );
}
export function clusterPoints(records, project, zoom) {
  const groups = new Map();
  for (const f of records.filter(located)) {
    const point = project(f.map_location);
    const key =
      zoom >= 15
        ? `${point.x},${point.y}`
        : `${Math.floor(point.x / 64)},${Math.floor(point.y / 64)}`;
    const g = groups.get(key) || { x: 0, y: 0, records: [] };
    g.x += point.x;
    g.y += point.y;
    g.records.push(f);
    groups.set(key, g);
  }
  const clusters = [...groups.values()].map((g) => ({
    ...g,
    x: g.x / g.records.length,
    y: g.y / g.records.length,
  }));
  if (zoom >= 15) return clusters;
  let merged = true;
  while (merged) {
    merged = false;
    for (let i = 0; i < clusters.length; i++)
      for (let j = i + 1; j < clusters.length; j++) {
        const a = clusters[i],
          b = clusters[j];
        if (Math.hypot(a.x - b.x, a.y - b.y) >= 45) continue;
        const count = a.records.length + b.records.length;
        a.x = (a.x * a.records.length + b.x * b.records.length) / count;
        a.y = (a.y * a.records.length + b.y * b.records.length) / count;
        a.records.push(...b.records);
        clusters.splice(j--, 1);
        merged = true;
      }
  }
  return clusters;
}
