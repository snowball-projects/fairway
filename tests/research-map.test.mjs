import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  buildModel,
  selectCounties,
  selectRecords,
  summarize,
  located,
  parseProgress,
  facilityIdentity,
} from "../docs/research-map/model.mjs";

const catalog = JSON.parse(
  readFileSync(new URL("../data/public-courses.json", import.meta.url)),
);
const boundaries = JSON.parse(
  readFileSync(
    new URL("../docs/research-map/boundaries.json", import.meta.url),
  ),
);
const model = buildModel(catalog);
test("derived metrics agree with published catalog totals without inferring course layouts", () => {
  const totals = summarize(model.records);
  assert.equal(totals.facilities, catalog.coverage.facility_entry_count);
  assert.equal(totals.courses, catalog.coverage.course_entry_count);
  assert.equal(totals.four, catalog.coverage.complete_essentials);
  assert.equal(totals.five, catalog.coverage.complete_with_website);
  assert.equal(totals.located, catalog.coverage.facilities_with_coordinates);
  assert.equal(
    model.counties.filter((c) => c.records.length).length,
    catalog.coverage.counties_represented,
  );
});
test("public progress contract retains only region, stage, counts, time and exact identity", () => {
  const now = Date.parse("2026-10-08T12:00:00Z");
  const source = {
    schema_version: 1,
    updated_at: "2026-10-08T11:00:00Z",
    catalog_commit: "a".repeat(40),
    active_regions: [
      {
        state: "MN",
        county_fips: "27053",
        stage: "verification",
        note: "Do not display research notes",
        extra: "internal",
      },
      { state: "XX", stage: "discovery" },
      { state: "WI", county_fips: null, stage: "queued" },
    ],
    recent_batches: [
      {
        published_at: "2026-10-08T10:00:00Z",
        commit: "b".repeat(40),
        facilities_added: 1,
        facilities_updated: 0,
        added_facilities: [{ name: "Example", state: "MN", address: null }],
      },
    ],
  };
  const parsed = parseProgress(source, now);
  assert.equal(parsed.stale, false);
  assert.deepEqual(parsed.activeRegions, [
    { state: "MN", countyFips: "27053", stage: "verification" },
    { state: "WI", countyFips: null, stage: "queued" },
  ]);
  assert.equal(parsed.recentBatches[0].updated, 0);
  assert.ok(!JSON.stringify(parsed).includes("research notes"));
  assert.notEqual(
    facilityIdentity({ name: "Example", state: "MN", address: "1 Main St" }),
    facilityIdentity({ name: "Example", state: "MN", address: null }),
  );
});
test("missing, stale, future and malformed progress is conservative", () => {
  assert.throws(() => parseProgress({ schema_version: 2 }));
  const now = Date.parse("2026-10-08T12:00:00Z");
  const missing = parseProgress({ schema_version: 1 }, now);
  assert.equal(missing.stale, true);
  assert.deepEqual(missing.activeRegions, []);
  for (const updated_at of [
    "2026-10-01T00:00:00Z",
    "2026-10-09T00:00:00Z",
    "2026-10-08T11:00:00",
    "not a time",
  ])
    assert.equal(
      parseProgress({ schema_version: 1, updated_at }, now).stale,
      true,
    );
  const malformed = parseProgress(
    {
      schema_version: 1,
      active_regions: [null, { state: "MN", stage: "unknown" }],
      recent_batches: [
        null,
        {
          facilities_added: -1,
          facilities_updated: "12",
          added_facilities: [null, { name: "Example", state: "XX" }],
          commit: "javascript:alert(1)",
        },
      ],
    },
    now,
  );
  assert.equal(malformed.recentBatches[0].added, null);
  assert.equal(malformed.recentBatches[0].updated, null);
  assert.equal(malformed.recentBatches[0].commit, null);
  assert.deepEqual(malformed.recentBatches[0].facilities, []);
});
test("geometry covers every current county equivalent with no invented joins", () => {
  assert.deepEqual(
    boundaries.counties.map((c) => c.id).sort(),
    model.counties.map((c) => c.id).sort(),
  );
});
test("searched counties stay incomplete and records without county/coordinates remain in state totals", () => {
  const f = { state: "CA", region: "", query: "", status: "all" };
  const records = selectRecords(model, f, selectCounties(model, f));
  assert.equal(records.length, catalog.coverage.state_facility_entry_counts.CA);
  assert.ok(records.some((r) => !model.assigned.has(r)));
  assert.ok(records.some((r) => !located(r)));
  assert.ok(
    model.counties
      .filter((c) => c.status === "searched_incomplete")
      .every((c) => c.searched && !c.confirmed),
  );
});
test("missing fields and unverified totals do not imply course counts or completeness", () => {
  const records = [
    {
      name: "Example",
      address: "1 Main St",
      state: "CA",
      county: "Example County",
      holes: 36,
      courses: [],
      coordinates: { latitude: NaN, longitude: 1 },
    },
  ];
  const totals = summarize(records);
  assert.equal(totals.courses, 0);
  assert.equal(totals.four, 1);
  assert.equal(totals.five, 0);
  assert.equal(totals.located, 0);
});
