import assert from "node:assert/strict";
import test from "node:test";

import {
  deriveSearchBounds,
  originsFitGeographicSearchEnvelope,
  shortlistVenuesGeometrically,
  type GeographicSearchOptions,
  type Coordinates,
  type LocatedCandidateVenue,
  type SearchBounds,
} from "../src/core/geographic-candidates.ts";

const searchOptions = {
  bufferKilometers: 16,
  minimumSpanKilometers: 40,
  maximumSpanKilometers: 100,
} as const satisfies GeographicSearchOptions;

test("nearby origins receive the minimum search span", () => {
  const bounds = deriveSearchBounds(
    [
      { latitude: 41.88, longitude: -87.63 },
      { latitude: 41.89, longitude: -87.62 },
    ],
    searchOptions,
  );

  assert.ok(Math.abs(latitudeSpanKilometers(bounds) - 40) < 0.001);
  assert.ok(Math.abs(longitudeSpanKilometers(bounds) - 40) < 0.001);
});

test("the configured buffer expands an origin envelope on every side", () => {
  const origins = [
    { latitude: 41.8, longitude: -87.8 },
    { latitude: 41.9, longitude: -87.6 },
  ] as const;
  const unbuffered = deriveSearchBounds(origins, {
    bufferKilometers: 0,
    minimumSpanKilometers: 1,
    maximumSpanKilometers: 100,
  });
  const buffered = deriveSearchBounds(origins, {
    bufferKilometers: 10,
    minimumSpanKilometers: 1,
    maximumSpanKilometers: 100,
  });

  assert.ok(
    Math.abs(
      latitudeSpanKilometers(buffered) -
        latitudeSpanKilometers(unbuffered) -
        20,
    ) < 0.001,
  );
  assert.ok(
    Math.abs(
      longitudeSpanKilometers(buffered) -
        longitudeSpanKilometers(unbuffered) -
        20,
    ) < 0.001,
  );
  assert.ok(buffered.west < -87.8);
  assert.ok(buffered.east > -87.6);
  assert.ok(
    Math.abs((buffered.west + buffered.east) / 2 - -87.7) < 0.000001,
  );
});

test("widely separated origins are capped at the maximum search span", () => {
  const bounds = deriveSearchBounds(
    [
      { latitude: 41.45, longitude: -88.7 },
      { latitude: 42.5, longitude: -87.3 },
    ],
    { ...searchOptions, maximumSpanKilometers: 80 },
  );

  assert.ok(Math.abs(latitudeSpanKilometers(bounds) - 80) < 0.001);
  assert.ok(Math.abs(longitudeSpanKilometers(bounds) - 80) < 0.001);
});

test("regional-envelope validation includes the required search buffer", () => {
  assert.equal(
    originsFitGeographicSearchEnvelope(
      [
        { latitude: 41.88, longitude: -87.63 },
        { latitude: 42.1, longitude: -87.8 },
      ],
      searchOptions,
    ),
    true,
  );
  assert.equal(
    originsFitGeographicSearchEnvelope(
      [
        { latitude: 41.88, longitude: -87.63 },
        { latitude: 40.71, longitude: -74.01 },
      ],
      searchOptions,
    ),
    false,
  );
});

test("the shortlist preserves candidates favored by maximum, total, and spread criteria", () => {
  const origins = objectiveOrigins();
  const venues = objectiveVenues();

  assert.deepEqual(
    shortlistVenuesGeometrically(origins, venues, 3).map(({ id }) => id),
    ["max", "total", "spread"],
  );
});

test("union truncation is deterministic across provider response order", () => {
  const origins = objectiveOrigins();
  const venues = objectiveVenues();
  const expected = ["max", "total", "spread", "north"];

  assert.deepEqual(
    shortlistVenuesGeometrically(origins, venues, 4).map(({ id }) => id),
    expected,
  );
  assert.deepEqual(
    shortlistVenuesGeometrically(
      origins,
      [...venues].reverse(),
      4,
    ).map(({ id }) => id),
    expected,
  );
});

test("equal-distance ties use ascending venue ID", () => {
  const coordinates = { latitude: 41.9, longitude: -87.7 };
  const venues = [
    venue("zulu", coordinates.latitude, coordinates.longitude),
    venue("alpha", coordinates.latitude, coordinates.longitude),
  ];

  assert.deepEqual(
    shortlistVenuesGeometrically(
      [
        { latitude: 41.8, longitude: -87.8 },
        { latitude: 42, longitude: -87.6 },
      ],
      venues,
      1,
    ).map(({ id }) => id),
    ["alpha"],
  );
});

test("invalid origin and venue coordinates are rejected", () => {
  assert.throws(
    () =>
      deriveSearchBounds(
        [{ latitude: 91, longitude: -87.7 }],
        searchOptions,
      ),
    /invalid coordinates/u,
  );
  assert.throws(
    () =>
      deriveSearchBounds(
        [{ latitude: 41.9, longitude: 181 }],
        searchOptions,
      ),
    /invalid coordinates/u,
  );
  assert.throws(
    () =>
      shortlistVenuesGeometrically(
        [
          { latitude: 41.8, longitude: -87.8 },
          { latitude: 42, longitude: -87.6 },
        ],
        [venue("bad", Number.NaN, -87.7)],
        1,
      ),
    /invalid coordinates/u,
  );
});

function objectiveOrigins(): readonly Coordinates[] {
  return [
    { latitude: 0, longitude: 0 },
    { latitude: 0, longitude: 0.4 },
    { latitude: 0.05, longitude: 0.1 },
  ];
}

function objectiveVenues(): readonly LocatedCandidateVenue[] {
  return [
    venue("max", 0, 0.2),
    venue("total", 0.05, 0.1),
    venue("spread", -0.28, 0.2),
    venue("north", 0.2, 0.2),
    venue("east", 0, 0.35),
    venue("west", 0, 0.05),
    venue("south", -0.1, 0.1),
  ];
}

function venue(
  id: string,
  latitude: number,
  longitude: number,
): LocatedCandidateVenue {
  return {
    id,
    name: id,
    coordinates: { latitude, longitude },
  };
}

function latitudeSpanKilometers(bounds: SearchBounds): number {
  return (bounds.north - bounds.south) * 111.32;
}

function longitudeSpanKilometers(bounds: SearchBounds): number {
  const centerLatitude = (bounds.south + bounds.north) / 2;
  return (
    (bounds.east - bounds.west) *
    111.32 *
    Math.cos((centerLatitude * Math.PI) / 180)
  );
}
