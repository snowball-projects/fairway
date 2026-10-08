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
const states = new Set(Object.values(regions).flat());
const stages = new Set(["discovery", "verification", "review", "queued"]);
export const facilityIdentity = (record) =>
  JSON.stringify([record.name, record.state, record.address ?? null]);
const sha = (value) =>
  typeof value === "string" && /^[a-f0-9]{40}$/i.test(value) ? value : null;
const count = (value) =>
  Number.isSafeInteger(value) && value >= 0 ? value : null;
const utc = (value) =>
  typeof value === "string" &&
  /(?:Z|\+00:00)$/.test(value) &&
  Number.isFinite(Date.parse(value))
    ? value
    : null;
export function parseAdditions(value) {
  if (
    !value ||
    value.schema_version !== 1 ||
    value.time_basis !== "git_commit_time" ||
    value.count_unit !== "provisional_facility_entry" ||
    !Array.isArray(value.batches)
  )
    throw new Error("Unsupported additions log");
  const batches = value.batches.map((batch) => {
    const redacted =
      batch?.redacted_entries === undefined ? 0 : count(batch.redacted_entries);
    const removed =
      batch?.facilities_removed === undefined
        ? 0
        : count(batch.facilities_removed);
    if (
      !batch ||
      !sha(batch.commit) ||
      !utc(batch.committed_at) ||
      typeof batch.initial_baseline !== "boolean" ||
      count(batch.facilities_added) === null ||
      !Array.isArray(batch.added_facilities) ||
      redacted === null ||
      removed === null ||
      batch.facilities_added !== batch.added_facilities.length + redacted ||
      batch.added_facilities.some(
        (r) =>
          !r ||
          typeof r.name !== "string" ||
          !r.name.trim() ||
          !states.has(r.state) ||
          (r.address != null && typeof r.address !== "string"),
      )
    )
      throw new Error("Invalid additions batch");
    return {
      commit: batch.commit,
      committedAt: batch.committed_at,
      baseline: batch.initial_baseline,
      added: batch.facilities_added,
      redacted,
      removed,
      facilities: batch.added_facilities.map((r) => ({
        name: r.name,
        state: r.state,
        address: r.address ?? null,
      })),
    };
  });
  return { completeFrom: utc(value.history_complete_from), batches };
}
export function parseProgress(value, now = Date.now()) {
  if (!value || value.schema_version !== 1)
    throw new Error("Unsupported progress snapshot");
  const updatedAt = utc(value.updated_at);
  return {
    updatedAt,
    stale:
      !updatedAt ||
      now - Date.parse(updatedAt) > 2 * 86400000 ||
      Date.parse(updatedAt) - now > 600000,
    catalogCommit: sha(value.catalog_commit),
    activeRegions: (Array.isArray(value.active_regions)
      ? value.active_regions
      : []
    )
      .filter((r) => r && states.has(r.state) && stages.has(r.stage))
      .map((r) => ({
        state: r.state,
        countyFips:
          typeof r.county_fips === "string" && /^\d{5}$/.test(r.county_fips)
            ? r.county_fips
            : null,
        stage: r.stage,
      })),
    recentBatches: (Array.isArray(value.recent_batches)
      ? value.recent_batches
      : []
    )
      .filter((b) => b && typeof b === "object")
      .map((b) => ({
        publishedAt: utc(b.published_at),
        commit: sha(b.commit),
        added: count(b.facilities_added),
        updated: count(b.facilities_updated),
        facilities: (Array.isArray(b.added_facilities)
          ? b.added_facilities
          : []
        )
          .filter(
            (r) =>
              r &&
              typeof r.name === "string" &&
              r.name.trim() &&
              states.has(r.state) &&
              (r.address == null || typeof r.address === "string"),
          )
          .map((r) => ({
            name: r.name,
            state: r.state,
            address: r.address ?? null,
          })),
      })),
  };
}
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
    !catalog ||
    !Array.isArray(catalog.facilities) ||
    !Array.isArray(catalog.county_checklist) ||
    catalog.facilities.some(
      (r) =>
        !r ||
        typeof r.name !== "string" ||
        !r.name.trim() ||
        !states.has(r.state),
    ) ||
    catalog.county_checklist.some(
      (c) =>
        !c ||
        !/^\d{5}$/.test(c.fips) ||
        !states.has(c.state) ||
        typeof c.name !== "string",
    )
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
    const county =
      typeof record.county === "string" && record.county.trim()
        ? byName.get(`${record.state}|${record.county}`)
        : undefined;
    if (county) {
      county.records.push(record);
      assigned.set(record, county.id);
    }
  }
  return { records: catalog.facilities, counties, byId, assigned };
}
export function addedFacilities(previous, next) {
  const identities = new Set(previous.map(facilityIdentity));
  const uniqueKeys = (records, key) => {
    const counts = new Map();
    for (const record of records) {
      const value = key(record);
      if (value) counts.set(value, (counts.get(value) || 0) + 1);
    }
    return counts;
  };
  const name = (r) => JSON.stringify([r.state, r.name]);
  const address = (r) =>
    r.address ? JSON.stringify([r.state, r.address]) : null;
  const keys = [name, address].map((key) => [
    key,
    uniqueKeys(previous, key),
    uniqueKeys(next, key),
  ]);
  return next.filter(
    (r) =>
      !identities.has(facilityIdentity(r)) &&
      !keys.some(
        ([key, before, after]) =>
          before.get(key(r)) === 1 && after.get(key(r)) === 1,
      ),
  );
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
