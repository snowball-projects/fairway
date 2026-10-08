export const regions = {
  Northeast: ["CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"],
  Midwest: [
    "IN",
    "IL",
    "MI",
    "OH",
    "WI",
    "IA",
    "KS",
    "MN",
    "MO",
    "NE",
    "ND",
    "SD",
  ],
  South: [
    "DE",
    "DC",
    "FL",
    "GA",
    "MD",
    "NC",
    "SC",
    "VA",
    "WV",
    "AL",
    "KY",
    "MS",
    "TN",
    "AR",
    "LA",
    "OK",
    "TX",
  ],
  West: [
    "AZ",
    "CO",
    "ID",
    "MT",
    "NV",
    "NM",
    "UT",
    "WY",
    "AK",
    "CA",
    "HI",
    "OR",
    "WA",
  ],
};
export const essentials = ["name", "address", "county", "holes"];
export const complete = (record, fields = essentials) =>
  fields.every((key) =>
    key === "holes"
      ? Number.isFinite(record[key]) && record[key] > 0
      : typeof record[key] === "string" && record[key].trim(),
  );
export function located(record) {
  const c = record.coordinates;
  return (
    c &&
    Number.isFinite(c.latitude) &&
    Number.isFinite(c.longitude) &&
    Math.abs(c.latitude) <= 90 &&
    Math.abs(c.longitude) <= 180
  );
}
export function summarize(records) {
  return {
    facilities: records.length,
    courses: records.reduce(
      (n, r) => n + (Array.isArray(r.courses) ? r.courses.length : 0),
      0,
    ),
    four: records.filter((r) => complete(r)).length,
    five: records.filter((r) => complete(r, [...essentials, "website"])).length,
    located: records.filter(located).length,
    unresolved: records.filter((r) => r.course_details_complete !== true)
      .length,
    missing: Object.fromEntries(
      ["address", "county", "holes", "website"].map((key) => [
        key,
        records.filter((r) => !complete(r, [key])).length,
      ]),
    ),
  };
}
export function buildModel(catalog) {
  if (
    !Array.isArray(catalog.facilities) ||
    !Array.isArray(catalog.county_checklist)
  ) {
    throw new Error("Unsupported catalog");
  }
  const counties = catalog.county_checklist.map((c) => ({
    id: c.fips,
    state: c.state,
    name: c.name,
    status: c.search_status,
    searched:
      c.search_status === "searched_incomplete" ||
      c.search_status === "searched_complete",
    confirmed: c.search_status === "searched_complete",
    searchedOn: c.searched_on || null,
    records: [],
  }));
  const byId = new Map(counties.map((c) => [c.id, c]));
  const byName = new Map(counties.map((c) => [`${c.state}|${c.name}`, c]));
  const assigned = new Map();
  for (const record of catalog.facilities) {
    const evidence = byId.get(record.county_evidence?.county_fips);
    const county =
      evidence?.state === record.state
        ? evidence
        : byName.get(`${record.state}|${record.county}`);
    if (county) {
      county.records.push(record);
      assigned.set(record, county.id);
    }
  }
  return { records: catalog.facilities, counties, byId, assigned };
}
export function selectCounties(model, filters) {
  return model.counties.filter(
    (c) =>
      (!filters.state || c.state === filters.state) &&
      (!filters.region || regions[filters.region].includes(c.state)) &&
      (!filters.query ||
        `${c.name} ${c.state}`
          .toLowerCase()
          .includes(filters.query.toLowerCase())) &&
      (filters.status === "all" ||
        (filters.status === "represented" && c.records.length > 0) ||
        (filters.status === "searched" && c.searched) ||
        (filters.status === "unsearched" && c.status === "unsearched") ||
        (filters.status === "confirmed" && c.confirmed)),
  );
}
export function selectRecords(model, filters, counties) {
  const ids = new Set(counties.map((c) => c.id));
  return model.records.filter(
    (r) =>
      (!filters.state || r.state === filters.state) &&
      (!filters.region || regions[filters.region].includes(r.state)) &&
      (ids.has(model.assigned.get(r)) ||
        (filters.status === "all" && !filters.query && !model.assigned.has(r))),
  );
}
export function project(longitude, latitude, state) {
  if (state === "AK")
    return [
      (longitude < 0 ? longitude + 180 : longitude - 180) * 4.5 + 25,
      (72 - latitude) * 6 + 435,
    ];
  if (state === "HI")
    return [(longitude + 161) * 19 + 250, (23 - latitude) * 19 + 490];
  const rad = Math.PI / 180;
  const n = (Math.sin(29.5 * rad) + Math.sin(45.5 * rad)) / 2;
  const c = Math.cos(29.5 * rad) ** 2 + 2 * n * Math.sin(29.5 * rad);
  const rho = Math.sqrt(c - 2 * n * Math.sin(latitude * rad)) / n;
  const rho0 = Math.sqrt(c - 2 * n * Math.sin(38 * rad)) / n;
  const theta = n * (longitude + 96) * rad;
  return [
    510 + 1100 * rho * Math.sin(theta),
    270 + 1100 * (rho * Math.cos(theta) - rho0),
  ];
}
