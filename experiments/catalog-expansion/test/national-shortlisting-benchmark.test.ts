import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  analyzeScenario,
  buildScenarioPlan,
  createMatrixCacheKey,
  mergeTravelTimeMatrices,
  planMatrixBatches,
  productionParametersForTarget,
  validateScenarioCorpus,
  type BenchmarkCourse,
  type BenchmarkScenario,
  type CacheContext,
  type ScenarioPlan,
} from "../scripts/national-shortlisting-benchmark.ts";
import { RANKING_MODES } from "../src/core/ranking.ts";

test("the checked-in scenario corpus is public, bounded, and covers two through six origins", async () => {
  const fixture = JSON.parse(
    await readFile("benchmark/national-shortlisting-scenarios.json", "utf8"),
  );
  const scenarios = validateScenarioCorpus(fixture);

  assert.equal(scenarios.length, 26);
  assert.deepEqual(
    [...new Set(scenarios.map(({ origins }) => origins.length))].sort(),
    [2, 3, 4, 5, 6],
  );
  assert.equal(
    scenarios.filter(({ expandedReference }) => expandedReference).length,
    4,
  );
  assert.ok(
    scenarios.every(
      ({ categories, origins }) =>
        categories.length > 0 &&
        origins.every(({ label }) => /Hall|Center|Building/u.test(label)),
    ),
  );
});

test("production configurations form one interpretable scaled parameter family", () => {
  assert.deepEqual(productionParametersForTarget(20), {
    localSearchRadiiKilometers: [
      1, 2, 3, 5, 8, 12, 18, 25, 35, 50, 70, 100, 140, 200, 280, 400,
      600, 850, 1_200, 1_700, 2_400, 3_400, 4_800,
    ],
    localTargetCandidateCount: 6,
    globalMinimumTotalCandidateCount: 5,
    globalMinimumMaximumCandidateCount: 5,
  });
  assert.deepEqual(productionParametersForTarget(100), {
    ...productionParametersForTarget(20),
    localTargetCandidateCount: 30,
    globalMinimumTotalCandidateCount: 25,
    globalMinimumMaximumCandidateCount: 25,
  });
});

test("the broad reference is deterministic and contains every production shortlist", () => {
  const scenario = simpleScenario();
  const courses = Array.from({ length: 180 }, (_, index) =>
    course(
      `course-${index.toString().padStart(3, "0")}`,
      39 + (index % 18) * 0.05,
      -99 + Math.floor(index / 18) * 0.05,
    ),
  );
  const first = buildScenarioPlan(scenario, courses);
  const second = buildScenarioPlan(scenario, [...courses].reverse());

  assert.deepEqual(first, second);
  const referenceIds = new Set(first.referenceCandidateIds);
  assert.equal(first.referenceCandidateIds.length, courses.length);
  assert.ok(
    first.productionShortlists.every(({ candidateIds }) =>
      candidateIds.every((id) => referenceIds.has(id)),
    ),
  );
  assert.equal(
    Object.values(first.referenceSourceCounts).reduce(
      (sum, count) => sum + count,
      0,
    ),
    courses.length,
  );
});

test("matrix batches obey the cell cap and merge without changing cells", () => {
  const ids = Array.from({ length: 1_000 }, (_, index) => `course-${index}`);
  const batches = planMatrixBatches(6, ids);
  assert.deepEqual(
    batches.map(({ candidateIds, cellCount }) => [candidateIds.length, cellCount]),
    [
      [500, 3_000],
      [500, 3_000],
    ],
  );
  assert.deepEqual(
    mergeTravelTimeMatrices([
      { one: { origin: 1 } },
      { two: { origin: null } },
    ]),
    { one: { origin: 1 }, two: { origin: null } },
  );
  assert.throws(() =>
    mergeTravelTimeMatrices([
      { duplicate: { origin: 1 } },
      { duplicate: { origin: 2 } },
    ]),
  );
});

test("cache keys bind catalog, scenario, candidates, endpoint, mode, and parameters", () => {
  const context: CacheContext = {
    catalogSha256: "catalog-a",
    scenario: {
      id: "scenario",
      origins: [
        {
          id: "origin",
          label: "Public Hall",
          latitude: 40,
          longitude: -90,
        },
      ],
    },
    candidates: [{ id: "course", latitude: 40.1, longitude: -90.1 }],
    provider: {
      baseUrl: "https://routing.example",
      profile: "driving-car",
      metrics: ["duration"],
      resolveLocations: false,
    },
  };
  const baseline = createMatrixCacheKey(context);
  assert.equal(baseline, createMatrixCacheKey(context));
  assert.notEqual(
    baseline,
    createMatrixCacheKey({ ...context, catalogSha256: "catalog-b" }),
  );
  assert.notEqual(
    baseline,
    createMatrixCacheKey({
      ...context,
      provider: { ...context.provider, baseUrl: "https://other.example" },
    }),
  );
});

test("analysis reuses canonical ranking semantics for both objectives and existing exclusions", () => {
  const scenario = simpleScenario();
  const courses = [
    course("total-winner", 40, -90, "Same Name", false),
    course("maximum-winner", 40.1, -90.1, "Same Name", true),
    course("unreachable", 40.2, -90.2, "Other", true),
  ];
  const plan: ScenarioPlan = {
    scenario,
    requestedReferenceSize: 3,
    referenceCandidateIds: courses.map(({ id }) => id),
    referenceSourceCounts: { synthetic: 3 },
    referenceCandidateSourceRanks: {
      "total-winner": {},
      "maximum-winner": {},
      unreachable: {},
    },
    referenceCheckpoints: [3],
    productionShortlists: [
      {
        target: 20,
        parameters: productionParametersForTarget(20),
        candidateIds: ["total-winner"],
        actualSize: 1,
        sourceCounts: {
          minimumTotalLocal: 1,
          minimumMaximumLocal: 1,
          globalMinimumTotal: 1,
          globalMinimumMaximum: 1,
        },
        anchors: {
          minimumTotal: { latitude: 40, longitude: -95 },
          minimumMaximum: { latitude: 40, longitude: -95 },
        },
        localSearchedRadii: { minimumTotal: 1, minimumMaximum: 1 },
      },
    ],
  };
  const matrix = {
    "total-winner": {
      "simple-origin-1": 10,
      "simple-origin-2": 100,
    },
    "maximum-winner": {
      "simple-origin-1": 60,
      "simple-origin-2": 60,
    },
    unreachable: {
      "simple-origin-1": null,
      "simple-origin-2": 20,
    },
  };
  const analysis = analyzeScenario(
    plan,
    new Map(courses.map((value) => [value.id, value])),
    matrix,
  );

  const maximum =
    analysis.objectives[RANKING_MODES.PROTECT_FARTHEST_TRAVELER].production[0]!;
  const total =
    analysis.objectives[RANKING_MODES.LOWEST_TOTAL_TRAVEL].production[0]!;
  assert.equal(maximum.winnerIncluded, false);
  assert.equal(maximum.regretMinutes, 40);
  assert.equal(total.winnerIncluded, true);
  assert.equal(total.regretMinutes, 0);
  assert.equal(analysis.routing.excludedCandidates, 1);
  assert.equal(analysis.routing.invalidCells, 1);
  assert.equal(analysis.exactNameDuplicateSlots.reference, 1);
});

function simpleScenario(): BenchmarkScenario {
  return {
    id: "simple",
    label: "Simple public group",
    categories: ["test"],
    expandedReference: false,
    origins: [
      {
        id: "simple-origin-1",
        label: "West Public Hall",
        coordinates: { latitude: 40, longitude: -100 },
      },
      {
        id: "simple-origin-2",
        label: "East Public Hall",
        coordinates: { latitude: 40, longitude: -90 },
      },
    ],
  };
}

function course(
  id: string,
  latitude: number,
  longitude: number,
  name = id,
  approximateCoordinate = true,
): BenchmarkCourse {
  return {
    id,
    name,
    sourceName: name,
    coordinates: { latitude, longitude },
    coordinateSource: approximateCoordinate ? "center" : "node",
    approximateCoordinate,
  };
}
