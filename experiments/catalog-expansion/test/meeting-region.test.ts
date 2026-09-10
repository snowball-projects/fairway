import assert from "node:assert/strict";
import test from "node:test";

import {
  shortlistMeetingRegionCandidates,
  type Coordinates,
  type LocatedPoint,
  type MeetingRegionParameters,
} from "../src/core/meeting-region.ts";
import {
  dispersedFairwayOrigins,
  fairwayShortlistingParameters,
  syntheticGolfCourses,
} from "../examples/fairway-meeting-region-fixture.ts";

const PARAMETERS: MeetingRegionParameters = {
  localSearchRadiiKilometers: [5, 25, 50],
  localTargetCandidateCount: 2,
  globalMinimumTotalCandidateCount: 1,
  globalMinimumMaximumCandidateCount: 1,
};

type GeographicCase = readonly [
  name: string,
  coordinates: readonly (readonly [number, number])[],
  coverageKilometers: number,
];

const GEOGRAPHIC_CASES: readonly GeographicCase[] = [
  ["Chicago regional", [[41.8781, -87.6298], [41.7508, -88.1535], [42.0451, -87.6877], [41.525, -88.0817]], 5],
  ["continental corners", [[47.6062, -122.3321], [34.0522, -118.2437], [25.7617, -80.1918], [40.7128, -74.006]], 50],
  ["asymmetric East Coast", [[42.3601, -71.0589], [40.7128, -74.006], [40.7128, -74.006], [39.9526, -75.1652], [38.9072, -77.0369]], 25],
  ["north-south", [[44.9778, -93.265], [39.0997, -94.5786], [32.7767, -96.797], [29.7604, -95.3698]], 25],
  ["east-west", [[40.7128, -74.006], [41.8781, -87.6298], [39.7392, -104.9903], [37.7749, -122.4194]], 50],
  ["nearly coincident", [[41.8781, -87.6298], [41.8782, -87.6297], [41.87815, -87.6299]], 0.01],
  ["two origins", [[41.8781, -87.6298], [40.7128, -74.006]], 0.01],
];

test("spherical anchors track independent Haversine references", (context) => {
  for (const [name, rawCoordinates, coverageKilometers] of GEOGRAPHIC_CASES) {
    const origins = rawCoordinates.map(([latitude, longitude], index) =>
      point(`origin-${index}`, latitude, longitude),
    );
    const anchors = shortlistMeetingRegionCandidates(origins, [], PARAMETERS).anchors;
    const measurements: string[] = [];

    for (const objective of ["total", "maximum"] as const) {
      const actual = objective === "total" ? anchors.minimumTotal : anchors.minimumMaximum;
      const coordinates = origins.map(({ coordinates: value }) => value);
      const reference = referenceAnchor(coordinates, objective);
      const separation = haversine(actual, reference);
      const referenceValue = objectiveValue(reference, coordinates, objective);
      const degradation = objectiveValue(actual, coordinates, objective) - referenceValue;
      assert.ok(separation <= coverageKilometers, `${name} ${objective} separation: ${separation} km`);
      assert.ok(degradation <= Math.max(0.001, referenceValue * 0.001), `${name} ${objective} degradation: ${degradation} km`);
      measurements.push(`${objective} ${separation.toFixed(3)} km/${((degradation / referenceValue) * 100).toFixed(4)}%`);
    }
    context.diagnostic(`${name} — ${measurements.join("; ")}`);
  }
});

test("symmetric, asymmetric, and coincident anchors have expected shapes", () => {
  const cases = [
    [[point("west", 0, -1), point("east", 0, 1)], [0, 0], [0, 0], 0.00001],
    [[point("west", 0, 0), point("middle", 0, 0.1), point("east", 0, 2)], [0, 0.1], [0, 1], 0.001],
    [[point("one", 41.8781, -87.6298), point("two", 41.8781, -87.6298), point("three", 41.8781, -87.6298)], [41.8781, -87.6298], [41.8781, -87.6298], 0.000001],
  ] as const;
  for (const [origins, total, maximum, tolerance] of cases) {
    const anchors = shortlistMeetingRegionCandidates(origins, [], PARAMETERS).anchors;
    assertCoordinates(anchors.minimumTotal, total, tolerance);
    assertCoordinates(anchors.minimumMaximum, maximum, tolerance);
  }
});

test("local search expands, admits radius ties, and reports sparse supply", () => {
  const candidates = [point("center", 0, 0), point("north", 0.1, 0), point("south", -0.1, 0)];
  const expanded = shortlistMeetingRegionCandidates(symmetricOrigins(), candidates, {
    ...PARAMETERS,
    localSearchRadiiKilometers: [1, 15, 30],
  });
  for (const pool of Object.values(expanded.localPools)) {
    assert.equal(pool.searchedRadiusKilometers, 15);
    assert.deepEqual(pool.candidates.map(({ admittedRadiusKilometers }) => admittedRadiusKilometers), [1, 15, 15]);
  }

  const sparse = shortlistMeetingRegionCandidates(symmetricOrigins(), candidates, {
    ...PARAMETERS,
    localSearchRadiiKilometers: [1, 15],
    localTargetCandidateCount: 5,
  });
  assert.ok(Object.values(sparse.localPools).every((pool) => pool.searchedRadiusKilometers === 15 && pool.candidates.length === 3));
});

test("global pools recover candidates outside local radii and deduplicate overlaps", () => {
  const result = shortlistMeetingRegionCandidates(
    symmetricOrigins(),
    [point("local", 0, 0), point("global-only", 0, 0.05), point("unselected", 0, 1)],
    { localSearchRadiiKilometers: [1], localTargetCandidateCount: 1, globalMinimumTotalCandidateCount: 2, globalMinimumMaximumCandidateCount: 2 },
  );
  assert.deepEqual(result.shortlist.map(({ candidateId }) => candidateId), ["global-only", "local"]);
  assert.deepEqual(result.shortlist[0]?.sources, { globalMinimumTotal: true, globalMinimumMaximum: true });
  assert.deepEqual(result.shortlist[1]?.sources, {
    minimumTotalLocalRadiusKilometers: 1,
    minimumMaximumLocalRadiusKilometers: 1,
    globalMinimumTotal: true,
    globalMinimumMaximum: true,
  });
});

test("global objectives differ, IDs break ties, and input order is irrelevant", () => {
  const origins = [point("west", 0, 0), point("east", 0, 0.4), point("northwest", 0.05, 0.1)];
  const candidates = [point("max", 0, 0.2), point("total", 0.05, 0.1), point("other", -0.2, 0.2)];
  const result = shortlistMeetingRegionCandidates(origins, candidates, { ...PARAMETERS, localSearchRadiiKilometers: [0] });
  assert.deepEqual(result.globalPools, { minimumTotal: ["total"], minimumMaximum: ["max"] });
  assert.deepEqual(
    result,
    shortlistMeetingRegionCandidates([...origins].reverse(), [...candidates].reverse(), { ...PARAMETERS, localSearchRadiiKilometers: [0] }),
  );

  const tie = shortlistMeetingRegionCandidates(
    symmetricOrigins(),
    [point("zulu", 0.1, 0), point("alpha", -0.1, 0)],
    { ...PARAMETERS, localSearchRadiiKilometers: [0] },
  );
  assert.deepEqual(tie.globalPools, { minimumTotal: ["alpha"], minimumMaximum: ["alpha"] });
});

test("the Fairway example uses only its supplied synthetic courses", () => {
  const result = shortlistMeetingRegionCandidates(dispersedFairwayOrigins, syntheticGolfCourses, fairwayShortlistingParameters);
  assert.ok(result.shortlist.length > 0 && result.shortlist.length <= syntheticGolfCourses.length);
});

test("invalid public inputs are rejected", () => {
  const invalidCalls = [
    () => shortlistMeetingRegionCandidates([], [], PARAMETERS),
    () => shortlistMeetingRegionCandidates([point("same", 0, 0), point("same", 0, 1)], [], PARAMETERS),
    () => shortlistMeetingRegionCandidates([point("one", 91, 0), point("two", 0, 0)], [], PARAMETERS),
    () => shortlistMeetingRegionCandidates(symmetricOrigins(), [], { ...PARAMETERS, localSearchRadiiKilometers: [5, 5] }),
    () => shortlistMeetingRegionCandidates(symmetricOrigins(), [], { ...PARAMETERS, globalMinimumTotalCandidateCount: 0 }),
  ];
  invalidCalls.forEach((call) => assert.throws(call));
});

interface ReferenceSample {
  readonly point: Coordinates;
  readonly value: number;
  readonly latitudeStep: number;
  readonly longitudeStep: number;
}

function referenceAnchor(origins: readonly Coordinates[], objective: "total" | "maximum"): Coordinates {
  if (origins.length === 2) return sphericalMidpoint(origins[0]!, origins[1]!);
  let south = Math.min(...origins.map(({ latitude }) => latitude));
  let north = Math.max(...origins.map(({ latitude }) => latitude));
  let west = Math.min(...origins.map(({ longitude }) => longitude));
  let east = Math.max(...origins.map(({ longitude }) => longitude));
  if (south === north) [south, north] = [south - 0.001, north + 0.001];
  if (west === east) [west, east] = [west - 0.001, east + 0.001];

  let seeds = scanGrid(origins, objective, south, north, west, east, 61);
  for (let level = 0; level < 4; level += 1) {
    seeds = seeds.flatMap(({ point: seed, latitudeStep, longitudeStep }) =>
      scanGrid(origins, objective, seed.latitude - latitudeStep, seed.latitude + latitudeStep, seed.longitude - longitudeStep, seed.longitude + longitudeStep, 21),
    ).sort((left, right) => left.value - right.value).slice(0, 6);
  }
  return seeds[0]!.point;
}

function scanGrid(
  origins: readonly Coordinates[], objective: "total" | "maximum",
  south: number, north: number, west: number, east: number, size: number,
): readonly ReferenceSample[] {
  const latitudeStep = (north - south) / (size - 1);
  const longitudeStep = (east - west) / (size - 1);
  const samples: ReferenceSample[] = [];
  for (let latitudeIndex = 0; latitudeIndex < size; latitudeIndex += 1) {
    for (let longitudeIndex = 0; longitudeIndex < size; longitudeIndex += 1) {
      const point = { latitude: south + latitudeIndex * latitudeStep, longitude: west + longitudeIndex * longitudeStep };
      samples.push({ point, value: objectiveValue(point, origins, objective), latitudeStep, longitudeStep });
    }
  }
  return samples.sort((left, right) => left.value - right.value).slice(0, 6);
}

function objectiveValue(pointToScore: Coordinates, origins: readonly Coordinates[], objective: "total" | "maximum"): number {
  const distances = origins.map((origin) => haversine(pointToScore, origin));
  return objective === "total" ? distances.reduce((sum, distance) => sum + distance, 0) : Math.max(...distances);
}

function haversine(first: Coordinates, second: Coordinates): number {
  const radians = (degrees: number) => (degrees * Math.PI) / 180;
  const latitude = radians(second.latitude - first.latitude);
  const longitude = radians(second.longitude - first.longitude);
  const value = Math.sin(latitude / 2) ** 2 + Math.cos(radians(first.latitude)) * Math.cos(radians(second.latitude)) * Math.sin(longitude / 2) ** 2;
  return 2 * 6_371.0088 * Math.asin(Math.sqrt(Math.min(1, value)));
}

function sphericalMidpoint(first: Coordinates, second: Coordinates): Coordinates {
  const radians = (degrees: number) => (degrees * Math.PI) / 180;
  const degrees = (value: number) => (value * 180) / Math.PI;
  const latitude1 = radians(first.latitude);
  const latitude2 = radians(second.latitude);
  const longitudeDelta = radians(second.longitude - first.longitude);
  const x = Math.cos(latitude2) * Math.cos(longitudeDelta);
  const y = Math.cos(latitude2) * Math.sin(longitudeDelta);
  return {
    latitude: degrees(Math.atan2(Math.sin(latitude1) + Math.sin(latitude2), Math.hypot(Math.cos(latitude1) + x, y))),
    longitude: first.longitude + degrees(Math.atan2(y, Math.cos(latitude1) + x)),
  };
}

function symmetricOrigins(): readonly LocatedPoint[] {
  return [point("west", 0, -0.1), point("east", 0, 0.1)];
}

function point(id: string, latitude: number, longitude: number): LocatedPoint {
  return { id, coordinates: { latitude, longitude } };
}

function assertCoordinates(actual: Coordinates, expected: readonly [number, number], tolerance: number): void {
  assert.ok(Math.abs(actual.latitude - expected[0]) <= tolerance);
  assert.ok(Math.abs(actual.longitude - expected[1]) <= tolerance);
}
