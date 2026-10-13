import test from "node:test";
import assert from "node:assert/strict";
import {
  mapEligible,
  catalogCounts,
  searchCatalog,
  shapeRings,
  clusterPoints,
} from "../src/fairway/static/catalog.mjs";
import { project } from "../docs/research-map/model.mjs";
import {
  canRemoveOrigin,
  originLimit,
  requiredOriginRows,
} from "../src/fairway/static/origin-rows.mjs";
const facility = {
  id: "f-example",
  name: "Public 27",
  state: "NY",
  physical_holes: 27,
  public_access: "public",
  website: null,
  courses: [],
  address: { text: "72 Main St, Bemus Point, NY 14712" },
  map_location: {
    latitude: 42.1576593,
    longitude: -79.3887563,
    kind: "property_point",
  },
};
test("planning retains two origin rows through repeated removals and restored counts", () => {
  const rows = ["first", "second", "third", "fourth", "fifth"];
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const index = rows.length - 1;
    if (canRemoveOrigin(rows.length, index)) rows.splice(index, 1);
  }
  assert.deepEqual(rows, ["first", "second"]);
  assert.equal(canRemoveOrigin(2, 0), false);
  assert.equal(canRemoveOrigin(2, 1), false);
  assert.equal(canRemoveOrigin(3, 0), false);
  assert.equal(canRemoveOrigin(3, 1), false);
  assert.equal(canRemoveOrigin(3, 2), true);
  assert.equal(canRemoveOrigin(4, 3), true);
  assert.equal(requiredOriginRows(0), 2);
  assert.equal(requiredOriginRows(1), 1);
  assert.equal(requiredOriginRows(2), 0);
  assert.equal(originLimit(1, 8), 2);
  assert.equal(originLimit(8, 8), 8);
});
test("public 27-hole facility with no website or invented courses is eligible, estimates remain pending", () => {
  assert.equal(mapEligible(facility), true);
  assert.equal(mapEligible({ ...facility, public_access: "unknown" }), false);
  assert.equal(
    mapEligible({
      ...facility,
      map_location: {
        ...facility.map_location,
        kind: "address_range_estimate",
      },
    }),
    false,
  );
  assert.deepEqual(
    catalogCounts([
      facility,
      { ...facility, id: "pending", map_location: null },
    ]),
    { total: 2, onMap: 1, pending: 1, estimates: 0 },
  );
});
test("facility/city/state search preserves duplicate-name geography and unmapped records", () => {
  const other = {
    ...facility,
    id: "other",
    state: "WI",
    map_location: null,
    address: { text: "10 Main St, Bemus Point, WI 54321" },
  };
  const results = searchCatalog(
    [facility, other],
    [{ id: "NY", name: "New York" }],
    "public",
  );
  assert.deepEqual(
    results.map((r) => r.subtitle),
    ["Bemus Point, NY", "Bemus Point, WI"],
  );
  assert.equal(
    searchCatalog([facility, other], [], "Bemus Point").filter(
      (r) => r.kind === "city",
    ).length,
    2,
  );
  assert.equal(
    searchCatalog([], [{ id: "NY", name: "New York" }], "ny")[0].id,
    "NY",
  );
});
test("Census state geometry inverts its projection without supplying fabricated facility bounds", () => {
  const [x, y] = project(-89, 42, "IL");
  const rings = shapeRings({ state: "IL", d: `M${x},${y}L${x},${y}Z` });
  assert.ok(Math.abs(rings[0][0][0] - 42) < 1e-9);
  assert.ok(Math.abs(rings[0][0][1] + 89) < 1e-9);
});
test("screen clusters conserve facility identities and separate actual points at local zoom", () => {
  const records = [
    facility,
    {
      ...facility,
      id: "b",
      map_location: { ...facility.map_location, longitude: -79.389 },
    },
  ];
  const projection = (p) => ({ x: p.longitude * 1000, y: p.latitude * 1000 });
  assert.equal(clusterPoints(records, projection, 4).length, 1);
  assert.equal(clusterPoints(records, projection, 15).length, 2);
  assert.deepEqual(
    clusterPoints(records, projection, 4)
      .flatMap((g) => g.records.map((f) => f.id))
      .sort(),
    ["b", "f-example"],
  );
});
