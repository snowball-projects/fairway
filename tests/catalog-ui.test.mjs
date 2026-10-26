import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  mapEligible,
  catalogCounts,
  searchCatalog,
} from "../src/fairway/static/catalog-read.mjs";
import {shapeRings} from "../src/fairway/static/map-geometry.mjs";
import {gunzipSync} from "node:zlib";
import { createFacilityDots } from "../src/fairway/static/facility-dots.mjs";
import {
  canRemoveOrigin,
  originLimit,
  requiredOriginRows,
} from "../src/fairway/static/origin-rows.mjs";
const facility = {
  facility_id: "f-example",
  name: "Public 27",
  state: "NY",
  physical_holes: 27,
  access: "public",
  website: null,
  courses: [],
  address: { text: "72 Main St, Bemus Point, NY 14712", city:"Bemus Point" },
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
  assert.equal(mapEligible({ ...facility, access: "unknown" }), true);
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
      { ...facility, facility_id: "pending", map_location: null },
    ]),
    { total: 2, onMap: 1, pending: 1 },
  );
});
test("facility/city/state search preserves duplicate-name geography and unmapped records", () => {
  const other = {
    ...facility,
    facility_id: "other",
    state: "WI",
    map_location: null,
    address: { text: "10 Main St, Bemus Point, WI 54321", city:"Bemus Point" },
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
  // Independent known Albers point at 42 N, 89 W.
  const [x, y] = [609.0744224868213, 188.86980716407058];
  const rings = shapeRings({ state: "IL", d: `M${x},${y}L${x},${y}Z` });
  assert.ok(Math.abs(rings[0][0][0] - 42) < 1e-9);
  assert.ok(Math.abs(rings[0][0][1] + 89) < 1e-9);
});

function dotMap() {
  const paths = new Set();
  const renderer = {};
  const map = {
    zoom: 4,
    getZoom() {
      return this.zoom;
    },
  };
  let creations = 0;
  const L = {
    canvas(options) {
      renderer.options = options;
      return renderer;
    },
    layerGroup() {
      return {
        addTo() {
          return this;
        },
        removeLayer(path) {
          paths.delete(path);
        },
      };
    },
    circleMarker(coordinates, options) {
      creations++;
      return {
        coordinates,
        options,
        styles: 0,
        setLatLng(value) {
          this.coordinates = value;
          return this;
        },
        getLatLng() {
          return this.coordinates;
        },
        on(event, handler) {
          this[event] = handler;
          return this;
        },
        addTo() {
          paths.add(this);
          return this;
        },
        setStyle(value) {
          Object.assign(this.options, value);
          this.styles++;
        },
        bringToFront() {
          this.front = true;
        },
      };
    },
  };
  return {
    L,
    map,
    paths,
    renderer,
    get creations() {
      return creations;
    },
  };
}

test("canvas dots retain every eligible identity and coordinate across national and local zoom", () => {
  const fake = dotMap();
  const selected = [];
  const layer = createFacilityDots(fake.L, fake.map, (id) => selected.push(id));
  const records = [
    facility,
    {
      ...facility,
      facility_id: "nearby",
      map_location: { ...facility.map_location, longitude: -79.389 },
    },
    {
      ...facility,
      facility_id: "estimate",
      map_location: {
        ...facility.map_location,
        kind: "address_range_estimate",
      },
    },
  ];
  const markers = layer.update(records, null);
  assert.equal(markers.size, 2);
  assert.equal(fake.paths.size, 2);
  assert.equal(fake.creations, 2);
  const first = markers.get(facility.facility_id);
  assert.deepEqual(first.coordinates, [42.1576593, -79.3887563]);
  assert.equal(first.options.renderer, fake.renderer);
  assert.equal(first.options.radius, 2.5);
  assert.equal(first.options.stroke, false);
  assert.ok(first.options.fillOpacity < 1);
  const styles = first.styles;
  for (let pan = 0; pan < 10; pan++) layer.update(records, null);
  assert.equal(first.styles, styles);
  fake.map.zoom = 15;
  layer.update(records, facility.facility_id);
  assert.equal(first.options.radius, 7);
  assert.equal(first.options.stroke, true);
  assert.equal(first.front, true);
  assert.equal(markers.get("nearby").options.radius, 4);
  assert.equal(fake.creations, 2);
  assert.deepEqual(first.coordinates, [42.1576593, -79.3887563]);
  first.click();
  assert.deepEqual(selected, [facility.facility_id]);
  layer.update(records, "nearby");
  assert.equal(first.options.stroke, false);
  assert.equal(markers.get("nearby").options.stroke, true);
});

test("snapshot refresh removes newly ineligible dots and updates coincident popup identities", () => {
  const fake = dotMap();
  const clicks = [];
  const layer = createFacilityDots(
    fake.L,
    fake.map,
    (id) => clicks.push(id),
    (ids, point) => clicks.push({ ids, point }),
  );
  const duplicate = { ...facility, facility_id: "same-point" };
  const markers = layer.update([facility, duplicate], null);
  const retained = markers.get(facility.facility_id);
  retained.click();
  assert.deepEqual(clicks[0].ids, [facility.facility_id, duplicate.facility_id]);
  const moved = {
    ...facility,
    map_location: { ...facility.map_location, longitude: -80 },
  };
  layer.update([moved, { ...duplicate, map_location:null }], facility.facility_id);
  assert.equal(markers.size, 1);
  assert.equal(fake.paths.size, 1);
  assert.equal(markers.get(facility.facility_id), retained);
  assert.deepEqual(retained.coordinates, [42.1576593, -80]);
  retained.click();
  assert.equal(clicks[1], facility.facility_id);
});

test("the published national catalog keeps one persistent canvas path per mapped facility", () => {
  const catalog = JSON.parse(gunzipSync(readFileSync(new URL("../data/catalog-release/catalog.json.gz",import.meta.url))));
  const eligible = catalog.facilities.filter(mapEligible);
  assert.ok(eligible.length > 4000);
  const fake = dotMap();
  const layer = createFacilityDots(
    fake.L,
    fake.map,
    () => {},
    () => {},
  );
  const markers = layer.update(catalog.facilities, null);
  assert.equal(markers.size, eligible.length);
  assert.equal(fake.creations, eligible.length);
  for (const zoom of [4, 7, 11, 15, 7, 4]) {
    fake.map.zoom = zoom;
    layer.update(catalog.facilities, null);
    assert.equal(markers.size, eligible.length);
    assert.equal(fake.creations, eligible.length);
  }
});
