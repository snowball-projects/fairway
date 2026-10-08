import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  buildModel,
  selectCounties,
  selectRecords,
  summarize,
  located,
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
