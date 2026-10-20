import test from "node:test";
import assert from "node:assert/strict";
import nativeCorica from "./fixtures/catalog-native/facility-corica-example.json" with {type:"json"};
import nativeEmpty from "./fixtures/catalog-native/facility-empty-cog-hill-example.json" with {type:"json"};
import {
  mapEligible,
  catalogCounts,
  searchCatalog,
  shapeRings,
} from "../src/fairway/static/catalog.mjs";
import { project } from "../docs/research-map/model.mjs";
import { createFacilityDots } from "../src/fairway/static/facility-dots.mjs";
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

const nativeFacility={...facility,facility_id:facility.id};delete nativeFacility.id;

test("canvas dots retain every eligible identity and coordinate across national and local zoom", () => {
  const fake = dotMap();
  const selected = [];
  const layer = createFacilityDots(fake.L, fake.map, (id) => selected.push(id));
  const records = [
    nativeFacility,
    {
      ...nativeFacility,
      facility_id: "nearby",
      map_location: { ...nativeFacility.map_location, longitude: -79.389 },
    },
    {
      ...nativeFacility,
      facility_id: "estimate",
      map_location: {
        ...nativeFacility.map_location,
        kind: "address_range_estimate",
      },
    },
  ];
  const markers = layer.update(records, null);
  assert.equal(markers.size, 2);
  assert.equal(fake.paths.size, 2);
  assert.equal(fake.creations, 2);
  const first = markers.get(nativeFacility.facility_id);
  assert.deepEqual(first.coordinates, [42.1576593, -79.3887563]);
  assert.equal(first.options.renderer, fake.renderer);
  assert.equal(first.options.radius, 2.5);
  assert.equal(first.options.stroke, false);
  assert.ok(first.options.fillOpacity < 1);
  const styles = first.styles;
  for (let pan = 0; pan < 10; pan++) layer.update(records, null);
  assert.equal(first.styles, styles);
  fake.map.zoom = 15;
  layer.update(records, nativeFacility.facility_id);
  assert.equal(first.options.radius, 7);
  assert.equal(first.options.stroke, true);
  assert.equal(first.front, true);
  assert.equal(markers.get("nearby").options.radius, 4);
  assert.equal(fake.creations, 2);
  assert.deepEqual(first.coordinates, [42.1576593, -79.3887563]);
  first.click();
  assert.deepEqual(selected, [nativeFacility.facility_id]);
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
  const duplicate = { ...nativeFacility, facility_id: "same-point" };
  const markers = layer.update([nativeFacility, duplicate], null);
  const retained = markers.get(nativeFacility.facility_id);
  retained.click();
  assert.deepEqual(clicks[0].ids, [nativeFacility.facility_id, duplicate.facility_id]);
  const moved = {
    ...nativeFacility,
    map_location: { ...nativeFacility.map_location, longitude: -80 },
  };
  layer.update([moved, { ...duplicate, map_location: null }], nativeFacility.facility_id);
  assert.equal(markers.size, 1);
  assert.equal(fake.paths.size, 1);
  assert.equal(markers.get(nativeFacility.facility_id), retained);
  assert.deepEqual(retained.coordinates, [42.1576593, -80]);
  retained.click();
  assert.equal(clicks[1], nativeFacility.facility_id);
});

test("native query examples retain one persistent canvas path per mapped facility across pans and zooms",()=>{
  const facilities=[...nativeCorica.facilities,...nativeEmpty.facilities];
  const fake=dotMap(),layer=createFacilityDots(fake.L,fake.map,()=>{},()=>{});
  const markers=layer.update(facilities,null);assert.equal(markers.size,2);assert.equal(fake.creations,2);
  for(const zoom of [4,7,11,15,7,4]){fake.map.zoom=zoom;layer.update(facilities,null);assert.equal(markers.size,2);assert.equal(fake.creations,2);}
  layer.update(facilities.map(f=>({...f,access:'private'})),null);assert.equal(markers.size,2);assert.equal(fake.creations,2);
});
