import { createHash } from "node:crypto";
import {
  mkdir,
  readFile,
  rename,
  writeFile,
} from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

import {
  shortlistMeetingRegionCandidates,
  type LocatedPoint,
  type MeetingRegionParameters,
} from "../src/core/meeting-region.ts";
import {
  rankDestinationsForAllModes,
  RANKING_MODES,
  type RankDestinationsResult,
  type RankingMode,
  type TravelTimeMatrix,
} from "../src/core/ranking.ts";
import { OpenRouteServiceMatrix } from "../src/providers/openrouteservice-matrix.ts";
import type {
  LocatedOrigin,
} from "../src/providers/location-providers.ts";

export const EXPECTED_NATIONAL_CATALOG_SHA256 =
  "ff0fd7efbb21e8e6edd4e99bc59acd7eb000272346e9ec7db4e961d352c3ad77";
export const SHORTLIST_TARGETS = [20, 30, 40, 60, 80, 100] as const;
export const REFERENCE_CHECKPOINTS = [500, 750, 1_000] as const;
export const ORDINARY_REFERENCE_SIZE = 500;
export const EXPANDED_REFERENCE_SIZE = 1_000;
export const MATRIX_CELL_LIMIT = 3_000;
export const PROVIDER_REQUEST_INTERVAL_MILLISECONDS = 1_600;
export const DEFAULT_PROVIDER_BASE_URL =
  "https://api.heigit.org/openrouteservice";
export const PROVIDER_PROFILE = "driving-car";

const LOCAL_RADII_KILOMETERS = [
  1, 2, 3, 5, 8, 12, 18, 25, 35, 50, 70, 100, 140, 200, 280, 400,
  600, 850, 1_200, 1_700, 2_400, 3_400, 4_800,
] as const;
const EARTH_RADIUS_KILOMETERS = 6_371.0088;
const CACHE_SCHEMA_VERSION = 1;
const SUMMARY_SCHEMA_VERSION = 1;

export interface BenchmarkScenarioInput {
  readonly id: string;
  readonly label: string;
  readonly categories: readonly string[];
  readonly expandedReference?: boolean;
  readonly origins: readonly {
    readonly label: string;
    readonly latitude: number;
    readonly longitude: number;
  }[];
}

export interface BenchmarkScenario {
  readonly id: string;
  readonly label: string;
  readonly categories: readonly string[];
  readonly expandedReference: boolean;
  readonly origins: readonly LocatedOrigin[];
}

interface CatalogCourseInput {
  readonly id: string;
  readonly name: string | null;
  readonly latitude: number;
  readonly longitude: number;
  readonly coordinate: {
    readonly source: string;
    readonly approximate: boolean;
  };
}

export interface BenchmarkCourse extends LocatedPoint {
  readonly name: string;
  readonly sourceName: string | null;
  readonly coordinateSource: string;
  readonly approximateCoordinate: boolean;
}

export interface ProductionShortlistPlan {
  readonly target: number;
  readonly parameters: MeetingRegionParameters;
  readonly candidateIds: readonly string[];
  readonly actualSize: number;
  readonly sourceCounts: {
    readonly minimumTotalLocal: number;
    readonly minimumMaximumLocal: number;
    readonly globalMinimumTotal: number;
    readonly globalMinimumMaximum: number;
  };
  readonly anchors: {
    readonly minimumTotal: { readonly latitude: number; readonly longitude: number };
    readonly minimumMaximum: { readonly latitude: number; readonly longitude: number };
  };
  readonly localSearchedRadii: {
    readonly minimumTotal: number;
    readonly minimumMaximum: number;
  };
}

export interface ScenarioPlan {
  readonly scenario: BenchmarkScenario;
  readonly productionShortlists: readonly ProductionShortlistPlan[];
  readonly referenceCandidateIds: readonly string[];
  readonly requestedReferenceSize: number;
  readonly referenceSourceCounts: Readonly<Record<string, number>>;
  readonly referenceCandidateSourceRanks: Readonly<
    Record<string, Readonly<Record<string, number | null>>>
  >;
  readonly referenceCheckpoints: readonly number[];
}

export const POLICY_CANDIDATE_SOURCES = [
  "minimum-total-local",
  "minimum-maximum-local",
  "minimum-total-haversine",
  "minimum-maximum-haversine",
  "origin-nearest-coverage",
  "radial-coverage",
] as const;

export type PolicyCandidateSource =
  (typeof POLICY_CANDIDATE_SOURCES)[number];

export interface CandidateSourceOrders {
  readonly anchors: {
    readonly minimumTotal: {
      readonly latitude: number;
      readonly longitude: number;
    };
    readonly minimumMaximum: {
      readonly latitude: number;
      readonly longitude: number;
    };
  };
  readonly sources: Readonly<
    Record<PolicyCandidateSource, readonly string[]>
  >;
}

export interface MatrixBatch {
  readonly index: number;
  readonly candidateIds: readonly string[];
  readonly cellCount: number;
}

export interface CacheContext {
  readonly catalogSha256: string;
  readonly scenario: {
    readonly id: string;
    readonly origins: readonly {
      readonly id: string;
      readonly label: string;
      readonly latitude: number;
      readonly longitude: number;
    }[];
  };
  readonly candidates: readonly {
    readonly id: string;
    readonly latitude: number;
    readonly longitude: number;
  }[];
  readonly provider: {
    readonly baseUrl: string;
    readonly profile: string;
    readonly metrics: readonly ["duration"];
    readonly resolveLocations: false;
  };
}

interface MatrixBatchCache {
  readonly schemaVersion: number;
  readonly cacheKey: string;
  readonly context: CacheContext;
  readonly matrix: TravelTimeMatrix;
  readonly providerObservation: {
    readonly latencyMilliseconds: number;
    readonly responseHeaders: Readonly<Record<string, string>>;
    readonly rawResponse: unknown;
  };
}

interface ProviderObservation {
  readonly latencyMilliseconds: number;
  readonly responseHeaders: Readonly<Record<string, string>>;
  readonly rawResponse: unknown;
}

interface RoutingResult {
  readonly matrix: TravelTimeMatrix;
  readonly cacheHits: number;
  readonly providerRequests: number;
  readonly providerObservations: readonly ProviderObservation[];
}

interface CliOptions {
  readonly catalogPath: string;
  readonly scenarioPath: string;
  readonly artifactRoot: string;
  readonly providerBaseUrl: string;
  readonly timeoutMilliseconds: number;
  readonly route: boolean;
  readonly preflight: boolean;
  readonly scenarioIds: readonly string[];
}

interface ScenarioAnalysis {
  readonly scenarioId: string;
  readonly label: string;
  readonly categories: readonly string[];
  readonly originCount: number;
  readonly requestedReferenceSize: number;
  readonly actualReferenceSize: number;
  readonly referenceSourceCounts: Readonly<Record<string, number>>;
  readonly routing: {
    readonly matrixCells: number;
    readonly batches: readonly {
      readonly candidates: number;
      readonly cells: number;
    }[];
    readonly excludedCandidates: number;
    readonly invalidCells: number;
    readonly approximateCandidates: number;
    readonly exactCandidates: number;
    readonly approximateCandidatesWithInvalidCells: number;
    readonly exactCandidatesWithInvalidCells: number;
    readonly invalidCandidateExamples: readonly string[];
  };
  readonly exactNameDuplicateSlots: {
    readonly reference: number;
    readonly byTarget: Readonly<Record<string, number>>;
  };
  readonly objectives: Readonly<
    Record<RankingMode, {
      readonly referenceWinner: RankedCourseSummary | null;
      readonly referenceWinnerDiagnostics: ReferenceWinnerDiagnostics | null;
      readonly production: readonly ObjectiveShortlistAnalysis[];
      readonly stabilization: readonly StabilizationObservation[];
    }>
  >;
}

interface RankedCourseSummary {
  readonly id: string;
  readonly name: string;
  readonly objectiveMinutes: number;
  readonly maximumMinutes: number;
  readonly totalMinutes: number;
  readonly approximateCoordinate: boolean;
}

interface ReferenceWinnerDiagnostics {
  readonly sourceRanks: Readonly<Record<string, number | null>>;
  readonly largestProductionConfiguration: {
    readonly target: number;
    readonly globalMinimumTotalCount: number;
    readonly globalMinimumMaximumCount: number;
    readonly distanceToMinimumTotalAnchorKilometers: number;
    readonly distanceToMinimumMaximumAnchorKilometers: number;
    readonly minimumTotalLocalRadiusKilometers: number;
    readonly minimumMaximumLocalRadiusKilometers: number;
    readonly insideMinimumTotalLocalPool: boolean;
    readonly insideMinimumMaximumLocalPool: boolean;
  };
  readonly classification:
    | "included-by-production"
    | "outside-local-and-global-pools"
    | "outside-local-pools"
    | "outside-global-pools";
}

interface ObjectiveShortlistAnalysis {
  readonly target: number;
  readonly actualSize: number;
  readonly winnerIncluded: boolean;
  readonly topThreeIncluded: number;
  readonly topThreeFraction: number;
  readonly fullTopThree: boolean;
  readonly topTenIncluded: number;
  readonly topTenFraction: number;
  readonly fullTopTen: boolean;
  readonly regretMinutes: number | null;
  readonly winner: RankedCourseSummary | null;
  readonly excludedCandidates: number;
}

interface StabilizationObservation {
  readonly referenceSize: number;
  readonly winnerId: string | null;
  readonly topThreeIds: readonly string[];
  readonly topTenIds: readonly string[];
  readonly objectiveMinutes: number | null;
  readonly winnerStableFromPrevious: boolean | null;
  readonly topThreeStableFromPrevious: boolean | null;
  readonly topTenOverlapFromPrevious: number | null;
  readonly improvementMinutesFromPrevious: number | null;
}

interface BenchmarkSummary {
  readonly schemaVersion: number;
  readonly inputs: {
    readonly catalogPath: string;
    readonly catalogSha256: string;
    readonly catalogSnapshot: string;
    readonly catalogCourseCount: number;
    readonly scenarioPath: string;
    readonly scenarioSha256: string;
    readonly scenarioCount: number;
  };
  readonly provider: {
    readonly identity: "openrouteservice-compatible";
    readonly baseUrl: string;
    readonly profile: string;
    readonly matrixCellLimit: number;
    readonly requestIntervalMilliseconds: number;
    readonly cacheSchemaVersion: number;
    readonly quotaHeaders: readonly Readonly<Record<string, string>>[];
  };
  readonly evaluation: {
    readonly shortlistTargets: readonly number[];
    readonly ordinaryReferenceSize: number;
    readonly expandedReferenceSize: number;
    readonly expandedScenarioCount: number;
    readonly candidatesRouted: number;
    readonly matrixCells: number;
    readonly providerRequestsRepresented: number;
    readonly providerLatencyMilliseconds: DistributionSummary;
  };
  readonly aggregates: Readonly<Record<RankingMode, readonly AggregateByTarget[]>>;
  readonly scenarios: readonly ScenarioAnalysis[];
}

interface DistributionSummary {
  readonly count: number;
  readonly median: number | null;
  readonly p90: number | null;
  readonly maximum: number | null;
  readonly total: number;
}

interface AggregateByTarget {
  readonly target: number;
  readonly scenarioCount: number;
  readonly actualSize: {
    readonly minimum: number;
    readonly median: number;
    readonly maximum: number;
    readonly mean: number;
  };
  readonly winnerInclusionRate: number;
  readonly fullTopThreeRate: number;
  readonly averageTopThreeFraction: number;
  readonly fullTopTenRate: number;
  readonly averageTopTenFraction: number;
  readonly winnerMissRegretMinutes: DistributionSummary;
  readonly allScenarioRegretMinutes: DistributionSummary;
  readonly worstRegretScenarios: readonly {
    readonly scenarioId: string;
    readonly regretMinutes: number;
  }[];
}

export function productionParametersForTarget(
  target: number,
): MeetingRegionParameters {
  if (!Number.isInteger(target) || target < 1) {
    throw new Error("Shortlist target must be a positive integer.");
  }
  return {
    localSearchRadiiKilometers: LOCAL_RADII_KILOMETERS,
    localTargetCandidateCount: Math.max(1, Math.round(target * 0.3)),
    globalMinimumTotalCandidateCount: Math.max(1, Math.round(target * 0.25)),
    globalMinimumMaximumCandidateCount: Math.max(1, Math.round(target * 0.25)),
  };
}

export function validateScenarioCorpus(
  input: unknown,
): readonly BenchmarkScenario[] {
  if (!isRecord(input) || input.schemaVersion !== 1 || !Array.isArray(input.scenarios)) {
    throw new Error("Scenario fixture must use schema version 1 and contain scenarios.");
  }
  if (input.scenarios.length < 20 || input.scenarios.length > 30) {
    throw new Error("Scenario fixture must contain between 20 and 30 scenarios.");
  }

  const ids = new Set<string>();
  const scenarios = input.scenarios.map((value, scenarioIndex) => {
    if (
      !isRecord(value) ||
      typeof value.id !== "string" ||
      !/^[a-z0-9]+(?:-[a-z0-9]+)*$/u.test(value.id) ||
      ids.has(value.id) ||
      typeof value.label !== "string" ||
      value.label.trim().length === 0 ||
      !Array.isArray(value.categories) ||
      value.categories.length === 0 ||
      value.categories.some((category) => typeof category !== "string") ||
      !Array.isArray(value.origins) ||
      value.origins.length < 2 ||
      value.origins.length > 6
    ) {
      throw new Error(`Scenario ${scenarioIndex + 1} is invalid.`);
    }
    ids.add(value.id);
    const origins = value.origins.map((origin, originIndex) => {
      if (
        !isRecord(origin) ||
        typeof origin.label !== "string" ||
        origin.label.trim().length === 0 ||
        !Number.isFinite(origin.latitude) ||
        Number(origin.latitude) < -90 ||
        Number(origin.latitude) > 90 ||
        !Number.isFinite(origin.longitude) ||
        Number(origin.longitude) < -180 ||
        Number(origin.longitude) > 180
      ) {
        throw new Error(
          `Origin ${originIndex + 1} in scenario "${value.id}" is invalid.`,
        );
      }
      return {
        id: `${value.id}-origin-${originIndex + 1}`,
        label: origin.label,
        coordinates: {
          latitude: Number(origin.latitude),
          longitude: Number(origin.longitude),
        },
      };
    });
    return {
      id: value.id,
      label: value.label,
      categories: [...value.categories] as string[],
      expandedReference: value.expandedReference === true,
      origins,
    };
  });

  const originCounts = new Set(scenarios.map(({ origins }) => origins.length));
  for (let count = 2; count <= 6; count += 1) {
    if (!originCounts.has(count)) {
      throw new Error(`Scenario fixture must include a ${count}-origin group.`);
    }
  }
  return scenarios;
}

export function normalizeCatalog(input: unknown): {
  readonly snapshot: string;
  readonly courses: readonly BenchmarkCourse[];
} {
  if (
    !isRecord(input) ||
    input.schemaVersion !== 1 ||
    !isRecord(input.source) ||
    typeof input.source.snapshot !== "string" ||
    !Array.isArray(input.courses)
  ) {
    throw new Error("National catalog has an unsupported shape.");
  }
  const ids = new Set<string>();
  const courses = input.courses.map((value, index) => {
    if (
      !isRecord(value) ||
      typeof value.id !== "string" ||
      value.id.length === 0 ||
      ids.has(value.id) ||
      (value.name !== null && typeof value.name !== "string") ||
      !Number.isFinite(value.latitude) ||
      !Number.isFinite(value.longitude) ||
      !isRecord(value.coordinate) ||
      typeof value.coordinate.source !== "string" ||
      typeof value.coordinate.approximate !== "boolean"
    ) {
      throw new Error(`Catalog course ${index + 1} is invalid.`);
    }
    ids.add(value.id);
    return {
      id: value.id,
      name:
        typeof value.name === "string" && value.name.trim().length > 0
          ? value.name
          : `Unnamed course (${value.id})`,
      sourceName: value.name as string | null,
      coordinates: {
        latitude: Number(value.latitude),
        longitude: Number(value.longitude),
      },
      coordinateSource: value.coordinate.source,
      approximateCoordinate: value.coordinate.approximate,
    };
  });
  return { snapshot: input.source.snapshot, courses };
}

export function buildScenarioPlan(
  scenario: BenchmarkScenario,
  courses: readonly BenchmarkCourse[],
): ScenarioPlan {
  const locatedOrigins = scenario.origins.map(({ id, coordinates }) => ({
    id,
    coordinates,
  }));
  const productionShortlists = SHORTLIST_TARGETS.map((target) => {
    const parameters = productionParametersForTarget(target);
    const result = shortlistMeetingRegionCandidates(
      locatedOrigins,
      courses,
      parameters,
    );
    return {
      target,
      parameters,
      candidateIds: result.shortlist.map(({ candidateId }) => candidateId),
      actualSize: result.shortlist.length,
      sourceCounts: {
        minimumTotalLocal: result.localPools.minimumTotal.candidates.length,
        minimumMaximumLocal: result.localPools.minimumMaximum.candidates.length,
        globalMinimumTotal: result.globalPools.minimumTotal.length,
        globalMinimumMaximum: result.globalPools.minimumMaximum.length,
      },
      anchors: result.anchors,
      localSearchedRadii: {
        minimumTotal: result.localPools.minimumTotal.searchedRadiusKilometers,
        minimumMaximum: result.localPools.minimumMaximum.searchedRadiusKilometers,
      },
    };
  });
  const requestedReferenceSize = scenario.expandedReference
    ? EXPANDED_REFERENCE_SIZE
    : ORDINARY_REFERENCE_SIZE;
  const reference = buildReferencePool(
    locatedOrigins,
    courses,
    productionShortlists,
    requestedReferenceSize,
  );
  const productionIds = new Set(
    productionShortlists.flatMap(({ candidateIds }) => candidateIds),
  );
  const referenceIds = new Set(reference.candidateIds);
  for (const id of productionIds) {
    if (!referenceIds.has(id)) {
      throw new Error(
        `Reference pool for "${scenario.id}" omitted production candidate "${id}".`,
      );
    }
  }
  return {
    scenario,
    productionShortlists,
    referenceCandidateIds: reference.candidateIds,
    requestedReferenceSize,
    referenceSourceCounts: reference.sourceCounts,
    referenceCandidateSourceRanks: reference.candidateSourceRanks,
    referenceCheckpoints: scenario.expandedReference
      ? REFERENCE_CHECKPOINTS.filter((size) => size <= reference.candidateIds.length)
      : [reference.candidateIds.length],
  };
}

function buildReferencePool(
  origins: readonly LocatedPoint[],
  courses: readonly BenchmarkCourse[],
  productionShortlists: readonly ProductionShortlistPlan[],
  target: number,
): {
  readonly candidateIds: readonly string[];
  readonly sourceCounts: Readonly<Record<string, number>>;
  readonly candidateSourceRanks: Readonly<
    Record<string, Readonly<Record<string, number | null>>>
  >;
} {
  const anchorPools = shortlistMeetingRegionCandidates(origins, courses, {
    localSearchRadiiKilometers: LOCAL_RADII_KILOMETERS,
    localTargetCandidateCount: Math.max(80, Math.round(target * 0.25)),
    globalMinimumTotalCandidateCount: 1,
    globalMinimumMaximumCandidateCount: 1,
  });
  const candidateSources = buildCandidateSourceOrdersFromAnchors(
    origins,
    courses,
    anchorPools.anchors,
  );
  const minimumTotal =
    candidateSources.sources["minimum-total-haversine"];
  const minimumMaximum =
    candidateSources.sources["minimum-maximum-haversine"];
  const originCoverage =
    candidateSources.sources["origin-nearest-coverage"];
  const radialCoverage = candidateSources.sources["radial-coverage"];
  const broadAnchor = unique([
    ...anchorPools.localPools.minimumTotal.candidates.map(({ candidateId }) => candidateId),
    ...anchorPools.localPools.minimumMaximum.candidates.map(({ candidateId }) => candidateId),
  ]);
  const sourceLists = {
    "broad-anchor-local": broadAnchor,
    "minimum-total-haversine": minimumTotal,
    "minimum-maximum-haversine": minimumMaximum,
    "origin-nearest-coverage": originCoverage,
    "radial-coverage": radialCoverage,
  } as const;

  const selected: string[] = [];
  const selectedIds = new Set<string>();
  const sourceCounts: Record<string, number> = {
    "production-shortlist-union": 0,
    ...Object.fromEntries(Object.keys(sourceLists).map((source) => [source, 0])),
  };
  const add = (id: string, source: string): void => {
    if (!selectedIds.has(id)) {
      selected.push(id);
      selectedIds.add(id);
      sourceCounts[source] = (sourceCounts[source] ?? 0) + 1;
    }
  };
  productionShortlists
    .flatMap(({ candidateIds }) => candidateIds)
    .sort(compareIds)
    .forEach((id) => add(id, "production-shortlist-union"));

  const positions = Object.fromEntries(
    Object.keys(sourceLists).map((source) => [source, 0]),
  ) as Record<keyof typeof sourceLists, number>;
  while (selected.length < target && selected.length < courses.length) {
    let advanced = false;
    for (const source of Object.keys(sourceLists) as (keyof typeof sourceLists)[]) {
      const list = sourceLists[source];
      while (
        positions[source] < list.length &&
        selectedIds.has(list[positions[source]]!)
      ) {
        positions[source] += 1;
      }
      const id = list[positions[source]];
      if (id !== undefined) {
        positions[source] += 1;
        add(id, source);
        advanced = true;
      }
      if (selected.length >= target) {
        break;
      }
    }
    if (!advanced) {
      break;
    }
  }

  const sourceRankMaps = Object.fromEntries(
    Object.entries(sourceLists).map(([source, list]) => [
      source,
      new Map(list.map((id, index) => [id, index + 1])),
    ]),
  ) as Readonly<Record<keyof typeof sourceLists, ReadonlyMap<string, number>>>;
  const candidateSourceRanks = Object.fromEntries(
    selected.map((id) => [
      id,
      Object.fromEntries(
        Object.keys(sourceLists).map((source) => [
          source,
          sourceRankMaps[source as keyof typeof sourceLists].get(id) ?? null,
        ]),
      ),
    ]),
  );
  return { candidateIds: selected, sourceCounts, candidateSourceRanks };
}

export function buildCandidateSourceOrders(
  origins: readonly LocatedPoint[],
  courses: readonly BenchmarkCourse[],
): CandidateSourceOrders {
  const orderedOrigins = [...origins].sort(
    (left, right) =>
      left.coordinates.latitude - right.coordinates.latitude ||
      left.coordinates.longitude - right.coordinates.longitude ||
      compareIds(left.id, right.id),
  );
  const anchors = shortlistMeetingRegionCandidates(orderedOrigins, courses, {
    localSearchRadiiKilometers: LOCAL_RADII_KILOMETERS,
    localTargetCandidateCount: 1,
    globalMinimumTotalCandidateCount: 1,
    globalMinimumMaximumCandidateCount: 1,
  }).anchors;
  return buildCandidateSourceOrdersFromAnchors(
    orderedOrigins,
    courses,
    anchors,
  );
}

function buildCandidateSourceOrdersFromAnchors(
  origins: readonly LocatedPoint[],
  courses: readonly BenchmarkCourse[],
  anchors: CandidateSourceOrders["anchors"],
): CandidateSourceOrders {
  const scored = courses.map((course) => {
    const distances = origins.map((origin) =>
      haversineKilometers(origin.coordinates, course.coordinates),
    );
    return {
      id: course.id,
      total: distances.reduce((sum, value) => sum + value, 0),
      maximum: Math.max(...distances),
      nearestOrigin: Math.min(...distances),
      minimumTotalAnchorDistance: haversineKilometers(
        anchors.minimumTotal,
        course.coordinates,
      ),
      anchorDistance: haversineKilometers(
        anchors.minimumMaximum,
        course.coordinates,
      ),
      bearing: initialBearingDegrees(
        anchors.minimumMaximum,
        course.coordinates,
      ),
    };
  });
  const minimumTotalLocal = [...scored]
    .sort((left, right) =>
      left.minimumTotalAnchorDistance - right.minimumTotalAnchorDistance ||
      left.total - right.total ||
      left.maximum - right.maximum ||
      compareIds(left.id, right.id),
    )
    .map(({ id }) => id);
  const minimumMaximumLocal = [...scored]
    .sort((left, right) =>
      left.anchorDistance - right.anchorDistance ||
      left.maximum - right.maximum ||
      left.total - right.total ||
      compareIds(left.id, right.id),
    )
    .map(({ id }) => id);
  const minimumTotal = [...scored]
    .sort((left, right) =>
      left.total - right.total ||
      left.maximum - right.maximum ||
      compareIds(left.id, right.id),
    )
    .map(({ id }) => id);
  const minimumMaximum = [...scored]
    .sort((left, right) =>
      left.maximum - right.maximum ||
      left.total - right.total ||
      compareIds(left.id, right.id),
    )
    .map(({ id }) => id);
  const originCoverage = originCoverageOrder(origins, courses);
  const radialCoverage = radialCoverageOrder(scored, minimumTotal, minimumMaximum);
  return {
    anchors,
    sources: {
      "minimum-total-local": minimumTotalLocal,
      "minimum-maximum-local": minimumMaximumLocal,
      "minimum-total-haversine": minimumTotal,
      "minimum-maximum-haversine": minimumMaximum,
      "origin-nearest-coverage": originCoverage,
      "radial-coverage": radialCoverage,
    },
  };
}

function originCoverageOrder(
  origins: readonly LocatedPoint[],
  courses: readonly BenchmarkCourse[],
): readonly string[] {
  const lists = origins.map((origin) =>
    courses
      .map((course) => ({
        id: course.id,
        distance: haversineKilometers(origin.coordinates, course.coordinates),
      }))
      .sort(
        (left, right) =>
          left.distance - right.distance || compareIds(left.id, right.id),
      )
      .map(({ id }) => id),
  );
  return roundRobinUnique(lists, courses.length);
}

function radialCoverageOrder(
  scored: readonly {
    readonly id: string;
    readonly total: number;
    readonly maximum: number;
    readonly nearestOrigin: number;
    readonly anchorDistance: number;
    readonly bearing: number;
  }[],
  minimumTotal: readonly string[],
  minimumMaximum: readonly string[],
): readonly string[] {
  const totalRanks = new Map(minimumTotal.map((id, index) => [id, index]));
  const maximumRanks = new Map(minimumMaximum.map((id, index) => [id, index]));
  const buckets = new Map<string, typeof scored extends readonly (infer T)[] ? T[] : never>();
  for (const candidate of scored) {
    const sector = Math.floor(candidate.bearing / 30) % 12;
    const ring = Math.min(
      8,
      Math.floor(Math.log2(candidate.anchorDistance / 25 + 1)),
    );
    const key = `${ring.toString().padStart(2, "0")}-${sector
      .toString()
      .padStart(2, "0")}`;
    const bucket = buckets.get(key) ?? [];
    bucket.push(candidate);
    buckets.set(key, bucket);
  }
  const orderedBuckets = [...buckets]
    .sort(([left], [right]) => compareIds(left, right))
    .map(([, candidates]) =>
      candidates
        .sort((left, right) =>
          Math.min(totalRanks.get(left.id)!, maximumRanks.get(left.id)!) -
            Math.min(totalRanks.get(right.id)!, maximumRanks.get(right.id)!) ||
          left.nearestOrigin - right.nearestOrigin ||
          compareIds(left.id, right.id),
        )
        .map(({ id }) => id),
    );
  return roundRobinUnique(orderedBuckets, scored.length);
}

function roundRobinUnique(
  lists: readonly (readonly string[])[],
  limit: number,
): readonly string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  for (let index = 0; result.length < limit; index += 1) {
    let advanced = false;
    for (const list of lists) {
      const id = list[index];
      if (id !== undefined) {
        advanced = true;
        if (!seen.has(id)) {
          result.push(id);
          seen.add(id);
        }
      }
    }
    if (!advanced) {
      break;
    }
  }
  return result;
}

export function planMatrixBatches(
  originCount: number,
  candidateIds: readonly string[],
  cellLimit = MATRIX_CELL_LIMIT,
): readonly MatrixBatch[] {
  if (!Number.isInteger(originCount) || originCount < 1) {
    throw new Error("Origin count must be a positive integer.");
  }
  const batchSize = Math.floor(cellLimit / originCount);
  if (batchSize < 1) {
    throw new Error("Matrix cell limit is too small for the origin count.");
  }
  const batches: MatrixBatch[] = [];
  for (let offset = 0; offset < candidateIds.length; offset += batchSize) {
    const ids = candidateIds.slice(offset, offset + batchSize);
    batches.push({
      index: batches.length,
      candidateIds: ids,
      cellCount: originCount * ids.length,
    });
  }
  return batches;
}

export function createMatrixCacheKey(context: CacheContext): string {
  return sha256(JSON.stringify(context));
}

export function mergeTravelTimeMatrices(
  matrices: readonly TravelTimeMatrix[],
): TravelTimeMatrix {
  const merged: Record<string, Readonly<Partial<Record<string, number | null>>>> = {};
  for (const matrix of matrices) {
    for (const [venueId, row] of Object.entries(matrix)) {
      if (Object.hasOwn(merged, venueId)) {
        throw new Error(`Matrix venue "${venueId}" was returned more than once.`);
      }
      merged[venueId] = row ?? {};
    }
  }
  return merged;
}

async function obtainScenarioMatrix(
  plan: ScenarioPlan,
  courseById: ReadonlyMap<string, BenchmarkCourse>,
  options: CliOptions,
  catalogSha256: string,
  allowNetwork: boolean,
  totalMissingRequests: { value: number },
  lastNetworkStart: { value: number },
): Promise<RoutingResult> {
  const batches = planMatrixBatches(
    plan.scenario.origins.length,
    plan.referenceCandidateIds,
  );
  const matrices: TravelTimeMatrix[] = [];
  const providerObservations: ProviderObservation[] = [];
  let cacheHits = 0;
  let providerRequests = 0;

  for (const batch of batches) {
    const candidates = batch.candidateIds.map((id) => requiredCourse(courseById, id));
    const context: CacheContext = {
      catalogSha256,
      scenario: {
        id: plan.scenario.id,
        origins: plan.scenario.origins.map(({ id, label, coordinates }) => ({
          id,
          label,
          latitude: coordinates.latitude,
          longitude: coordinates.longitude,
        })),
      },
      candidates: candidates.map(({ id, coordinates }) => ({
        id,
        latitude: coordinates.latitude,
        longitude: coordinates.longitude,
      })),
      provider: {
        baseUrl: options.providerBaseUrl,
        profile: PROVIDER_PROFILE,
        metrics: ["duration"],
        resolveLocations: false,
      },
    };
    const cacheKey = createMatrixCacheKey(context);
    const cachePath = resolve(
      options.artifactRoot,
      "cache",
      plan.scenario.id,
      `${batch.index.toString().padStart(2, "0")}-${cacheKey}.json`,
    );
    const cached = await readBatchCache(cachePath, cacheKey);
    if (cached !== null) {
      matrices.push(cached.matrix);
      providerObservations.push(cached.providerObservation);
      cacheHits += 1;
      continue;
    }
    if (!allowNetwork) {
      throw new Error(
        `Missing cached matrix batch for "${plan.scenario.id}". Run with --route after reviewing preflight.json.`,
      );
    }

    const waitMilliseconds = Math.max(
      0,
      PROVIDER_REQUEST_INTERVAL_MILLISECONDS -
        (performance.now() - lastNetworkStart.value),
    );
    if (lastNetworkStart.value > 0 && waitMilliseconds > 0) {
      await delay(waitMilliseconds);
    }
    lastNetworkStart.value = performance.now();
    let observation: ProviderObservation | undefined;
    const provider = new OpenRouteServiceMatrix({
      baseUrl: options.providerBaseUrl,
      apiKey: process.env.OPENROUTESERVICE_API_KEY ?? "",
      timeoutMilliseconds: options.timeoutMilliseconds,
      fetchImplementation: async (input, init) => {
        const started = performance.now();
        const response = await fetch(input, init);
        const rawText = await response.clone().text();
        observation = {
          latencyMilliseconds: round(performance.now() - started, 3),
          responseHeaders: selectedProviderHeaders(response.headers),
          rawResponse: parseJsonIfPossible(rawText),
        };
        return response;
      },
    });
    const matrix = await provider.calculateDrivingTravelTimes(
      plan.scenario.origins,
      candidates.map((course) => ({
        id: course.id,
        name: course.name,
        coordinates: course.coordinates,
      })),
    );
    if (observation === undefined) {
      throw new Error("Provider request completed without an observation.");
    }
    totalMissingRequests.value -= 1;
    assertQuotaHeadroom(observation.responseHeaders, totalMissingRequests.value);
    const cache: MatrixBatchCache = {
      schemaVersion: CACHE_SCHEMA_VERSION,
      cacheKey,
      context,
      matrix,
      providerObservation: observation,
    };
    await writeJsonAtomically(cachePath, cache);
    matrices.push(matrix);
    providerObservations.push(observation);
    providerRequests += 1;
    console.log(
      `routed ${plan.scenario.id} batch ${batch.index + 1}/${batches.length}: ${batch.candidateIds.length} candidates, ${batch.cellCount} cells`,
    );
  }
  return {
    matrix: mergeTravelTimeMatrices(matrices),
    cacheHits,
    providerRequests,
    providerObservations,
  };
}

function assertQuotaHeadroom(
  headers: Readonly<Record<string, string>>,
  pendingRequests: number,
): void {
  const value =
    headers["x-ratelimit-remaining"] ?? headers["x-rate-limit-remaining"];
  if (value === undefined) {
    return;
  }
  const remaining = Number(value);
  if (Number.isFinite(remaining) && remaining < pendingRequests) {
    throw new Error(
      `Provider reports ${remaining} matrix requests remaining, below the ${pendingRequests} still required. Cached progress is safe to resume after quota reset.`,
    );
  }
}

async function readBatchCache(
  cachePath: string,
  expectedKey: string,
): Promise<MatrixBatchCache | null> {
  let raw: string;
  try {
    raw = await readFile(cachePath, "utf8");
  } catch (error) {
    if (isNodeError(error) && error.code === "ENOENT") {
      return null;
    }
    throw error;
  }
  const value = JSON.parse(raw) as MatrixBatchCache;
  if (
    value.schemaVersion !== CACHE_SCHEMA_VERSION ||
    value.cacheKey !== expectedKey ||
    !isRecord(value.matrix) ||
    !isRecord(value.providerObservation)
  ) {
    throw new Error(`Incompatible benchmark cache at "${cachePath}".`);
  }
  return value;
}

export async function loadCachedScenarioMatrix(
  plan: ScenarioPlan,
  courseById: ReadonlyMap<string, BenchmarkCourse>,
  options: {
    readonly artifactRoot: string;
    readonly catalogSha256: string;
    readonly providerBaseUrl?: string;
  },
): Promise<TravelTimeMatrix> {
  const matrices: TravelTimeMatrix[] = [];
  for (const batch of planMatrixBatches(
    plan.scenario.origins.length,
    plan.referenceCandidateIds,
  )) {
    const candidates = batch.candidateIds.map((id) =>
      requiredCourse(courseById, id),
    );
    const context: CacheContext = {
      catalogSha256: options.catalogSha256,
      scenario: {
        id: plan.scenario.id,
        origins: plan.scenario.origins.map(({ id, label, coordinates }) => ({
          id,
          label,
          latitude: coordinates.latitude,
          longitude: coordinates.longitude,
        })),
      },
      candidates: candidates.map(({ id, coordinates }) => ({
        id,
        latitude: coordinates.latitude,
        longitude: coordinates.longitude,
      })),
      provider: {
        baseUrl: options.providerBaseUrl ?? DEFAULT_PROVIDER_BASE_URL,
        profile: PROVIDER_PROFILE,
        metrics: ["duration"],
        resolveLocations: false,
      },
    };
    const cacheKey = createMatrixCacheKey(context);
    const cachePath = resolve(
      options.artifactRoot,
      "cache",
      plan.scenario.id,
      `${batch.index.toString().padStart(2, "0")}-${cacheKey}.json`,
    );
    const cached = await readBatchCache(cachePath, cacheKey);
    if (cached === null) {
      throw new Error(
        `Missing cached matrix artifact for "${plan.scenario.id}": ${cachePath}`,
      );
    }
    matrices.push(cached.matrix);
  }
  return mergeTravelTimeMatrices(matrices);
}

export function analyzeScenario(
  plan: ScenarioPlan,
  courseById: ReadonlyMap<string, BenchmarkCourse>,
  matrix: TravelTimeMatrix,
): ScenarioAnalysis {
  const referenceCourses = plan.referenceCandidateIds.map((id) =>
    requiredCourse(courseById, id),
  );
  const referenceRanking = rank(referenceCourses, plan.scenario.origins, matrix);
  const objectives = Object.fromEntries(
    Object.values(RANKING_MODES).map((mode) => {
      const reference = referenceRanking[mode];
      const production = plan.productionShortlists.map((shortlist) => {
        const courses = shortlist.candidateIds.map((id) =>
          requiredCourse(courseById, id),
        );
        const result = rank(courses, plan.scenario.origins, matrix)[mode];
        return compareRanking(shortlist, result, reference, courseById, mode);
      });
      return [
        mode,
        {
          referenceWinner: summarizeWinner(reference, courseById, mode),
          referenceWinnerDiagnostics: diagnoseReferenceWinner(
            reference,
            plan,
            courseById,
          ),
          production,
          stabilization: stabilizationObservations(
            plan,
            referenceCourses,
            matrix,
            courseById,
            mode,
          ),
        },
      ];
    }),
  ) as ScenarioAnalysis["objectives"];
  const invalidIds = new Set(
    referenceRanking[RANKING_MODES.PROTECT_FARTHEST_TRAVELER].excludedVenues.map(
      ({ venue }) => venue.id,
    ),
  );
  const invalidCellCount = referenceCourses.reduce((count, course) => {
    const row = matrix[course.id];
    return (
      count +
      plan.scenario.origins.filter(({ id }) => {
        const value = row?.[id];
        return value === undefined || value === null || !Number.isFinite(value);
      }).length
    );
  }, 0);
  const approximate = referenceCourses.filter(
    ({ approximateCoordinate }) => approximateCoordinate,
  );
  const exact = referenceCourses.filter(
    ({ approximateCoordinate }) => !approximateCoordinate,
  );
  return {
    scenarioId: plan.scenario.id,
    label: plan.scenario.label,
    categories: plan.scenario.categories,
    originCount: plan.scenario.origins.length,
    requestedReferenceSize: plan.requestedReferenceSize,
    actualReferenceSize: referenceCourses.length,
    referenceSourceCounts: plan.referenceSourceCounts,
    routing: {
      matrixCells: plan.scenario.origins.length * referenceCourses.length,
      batches: planMatrixBatches(
        plan.scenario.origins.length,
        plan.referenceCandidateIds,
      ).map(({ candidateIds, cellCount }) => ({
        candidates: candidateIds.length,
        cells: cellCount,
      })),
      excludedCandidates: invalidIds.size,
      invalidCells: invalidCellCount,
      approximateCandidates: approximate.length,
      exactCandidates: exact.length,
      approximateCandidatesWithInvalidCells: approximate.filter(({ id }) =>
        invalidIds.has(id),
      ).length,
      exactCandidatesWithInvalidCells: exact.filter(({ id }) => invalidIds.has(id))
        .length,
      invalidCandidateExamples: referenceCourses
        .filter(({ id }) => invalidIds.has(id))
        .slice(0, 10)
        .map(({ id, name }) => `${name} (${id})`),
    },
    exactNameDuplicateSlots: {
      reference: exactNameDuplicateSlots(referenceCourses),
      byTarget: Object.fromEntries(
        plan.productionShortlists.map(({ target, candidateIds }) => [
          String(target),
          exactNameDuplicateSlots(
            candidateIds.map((id) => requiredCourse(courseById, id)),
          ),
        ]),
      ),
    },
    objectives,
  };
}

function diagnoseReferenceWinner(
  reference: RankDestinationsResult,
  plan: ScenarioPlan,
  courseById: ReadonlyMap<string, BenchmarkCourse>,
): ReferenceWinnerDiagnostics | null {
  const winner = reference.rankedVenues[0];
  const largest = plan.productionShortlists.at(-1);
  if (winner === undefined || largest === undefined) {
    return null;
  }
  const course = requiredCourse(courseById, winner.venue.id);
  const distanceToMinimumTotalAnchorKilometers = haversineKilometers(
    largest.anchors.minimumTotal,
    course.coordinates,
  );
  const distanceToMinimumMaximumAnchorKilometers = haversineKilometers(
    largest.anchors.minimumMaximum,
    course.coordinates,
  );
  const insideMinimumTotalLocalPool =
    distanceToMinimumTotalAnchorKilometers <=
    largest.localSearchedRadii.minimumTotal + 1e-7;
  const insideMinimumMaximumLocalPool =
    distanceToMinimumMaximumAnchorKilometers <=
    largest.localSearchedRadii.minimumMaximum + 1e-7;
  const ranks = plan.referenceCandidateSourceRanks[winner.venue.id] ?? {};
  const insideGlobalPools =
    (ranks["minimum-total-haversine"] ?? Number.POSITIVE_INFINITY) <=
      largest.parameters.globalMinimumTotalCandidateCount ||
    (ranks["minimum-maximum-haversine"] ?? Number.POSITIVE_INFINITY) <=
      largest.parameters.globalMinimumMaximumCandidateCount;
  const insideLocalPools =
    insideMinimumTotalLocalPool || insideMinimumMaximumLocalPool;
  const included = largest.candidateIds.includes(winner.venue.id);
  return {
    sourceRanks: ranks,
    largestProductionConfiguration: {
      target: largest.target,
      globalMinimumTotalCount:
        largest.parameters.globalMinimumTotalCandidateCount,
      globalMinimumMaximumCount:
        largest.parameters.globalMinimumMaximumCandidateCount,
      distanceToMinimumTotalAnchorKilometers: round(
        distanceToMinimumTotalAnchorKilometers,
        3,
      ),
      distanceToMinimumMaximumAnchorKilometers: round(
        distanceToMinimumMaximumAnchorKilometers,
        3,
      ),
      minimumTotalLocalRadiusKilometers: largest.localSearchedRadii.minimumTotal,
      minimumMaximumLocalRadiusKilometers:
        largest.localSearchedRadii.minimumMaximum,
      insideMinimumTotalLocalPool,
      insideMinimumMaximumLocalPool,
    },
    classification: included
      ? "included-by-production"
      : !insideLocalPools && !insideGlobalPools
        ? "outside-local-and-global-pools"
        : !insideLocalPools
          ? "outside-local-pools"
          : "outside-global-pools",
  };
}

function rank(
  courses: readonly BenchmarkCourse[],
  origins: readonly LocatedOrigin[],
  matrix: TravelTimeMatrix,
) {
  return rankDestinationsForAllModes({
    origins: origins.map(({ id, label }) => ({ id, label })),
    candidateVenues: courses.map(({ id, name }) => ({ id, name })),
    travelTimes: matrix,
  });
}

function compareRanking(
  shortlist: ProductionShortlistPlan,
  result: RankDestinationsResult,
  reference: RankDestinationsResult,
  courseById: ReadonlyMap<string, BenchmarkCourse>,
  mode: RankingMode,
): ObjectiveShortlistAnalysis {
  const selected = new Set(shortlist.candidateIds);
  const referenceTopThree = reference.rankedVenues.slice(0, 3);
  const referenceTopTen = reference.rankedVenues.slice(0, 10);
  const topThreeIncluded = referenceTopThree.filter(({ venue }) =>
    selected.has(venue.id),
  ).length;
  const topTenIncluded = referenceTopTen.filter(({ venue }) =>
    selected.has(venue.id),
  ).length;
  const referenceWinner = reference.rankedVenues[0];
  const shortlistWinner = result.rankedVenues[0];
  const regretMinutes =
    referenceWinner === undefined || shortlistWinner === undefined
      ? null
      : round(
          objectiveMinutes(shortlistWinner.metrics, mode) -
            objectiveMinutes(referenceWinner.metrics, mode),
          6,
        );
  return {
    target: shortlist.target,
    actualSize: shortlist.actualSize,
    winnerIncluded:
      referenceWinner !== undefined && selected.has(referenceWinner.venue.id),
    topThreeIncluded,
    topThreeFraction:
      referenceTopThree.length === 0
        ? 0
        : round(topThreeIncluded / referenceTopThree.length, 6),
    fullTopThree:
      referenceTopThree.length > 0 && topThreeIncluded === referenceTopThree.length,
    topTenIncluded,
    topTenFraction:
      referenceTopTen.length === 0
        ? 0
        : round(topTenIncluded / referenceTopTen.length, 6),
    fullTopTen:
      referenceTopTen.length > 0 && topTenIncluded === referenceTopTen.length,
    regretMinutes,
    winner: summarizeWinner(result, courseById, mode),
    excludedCandidates: result.excludedVenues.length,
  };
}

function stabilizationObservations(
  plan: ScenarioPlan,
  referenceCourses: readonly BenchmarkCourse[],
  matrix: TravelTimeMatrix,
  courseById: ReadonlyMap<string, BenchmarkCourse>,
  mode: RankingMode,
): readonly StabilizationObservation[] {
  let previous: RankDestinationsResult | undefined;
  return plan.referenceCheckpoints.map((referenceSize) => {
    const current = rank(
      referenceCourses.slice(0, referenceSize),
      plan.scenario.origins,
      matrix,
    )[mode];
    const currentWinner = summarizeWinner(current, courseById, mode);
    const previousWinner =
      previous === undefined ? null : summarizeWinner(previous, courseById, mode);
    const currentTopThree = current.rankedVenues
      .slice(0, 3)
      .map(({ venue }) => venue.id);
    const currentTopTen = current.rankedVenues
      .slice(0, 10)
      .map(({ venue }) => venue.id);
    const previousTopThree = previous?.rankedVenues
      .slice(0, 3)
      .map(({ venue }) => venue.id);
    const previousTopTen = previous?.rankedVenues
      .slice(0, 10)
      .map(({ venue }) => venue.id);
    const observation: StabilizationObservation = {
      referenceSize,
      winnerId: currentWinner?.id ?? null,
      topThreeIds: currentTopThree,
      topTenIds: currentTopTen,
      objectiveMinutes: currentWinner?.objectiveMinutes ?? null,
      winnerStableFromPrevious:
        previous === undefined
          ? null
          : currentWinner?.id === previousWinner?.id,
      topThreeStableFromPrevious:
        previousTopThree === undefined
          ? null
          : sameSet(currentTopThree, previousTopThree),
      topTenOverlapFromPrevious:
        previousTopTen === undefined
          ? null
          : currentTopTen.filter((id) => previousTopTen.includes(id)).length,
      improvementMinutesFromPrevious:
        previousWinner === null || currentWinner === null
          ? null
          : round(
              previousWinner.objectiveMinutes - currentWinner.objectiveMinutes,
              6,
            ),
    };
    previous = current;
    return observation;
  });
}

function summarizeWinner(
  result: RankDestinationsResult,
  courseById: ReadonlyMap<string, BenchmarkCourse>,
  mode: RankingMode,
): RankedCourseSummary | null {
  const winner = result.rankedVenues[0];
  if (winner === undefined) {
    return null;
  }
  const course = requiredCourse(courseById, winner.venue.id);
  return {
    id: winner.venue.id,
    name: winner.venue.name,
    objectiveMinutes: round(objectiveMinutes(winner.metrics, mode), 6),
    maximumMinutes: round(winner.metrics.maximumTravelTimeMinutes, 6),
    totalMinutes: round(winner.metrics.totalTravelTimeMinutes, 6),
    approximateCoordinate: course.approximateCoordinate,
  };
}

function aggregate(
  scenarios: readonly ScenarioAnalysis[],
  mode: RankingMode,
): readonly AggregateByTarget[] {
  return SHORTLIST_TARGETS.map((target) => {
    const observations = scenarios.map((scenario) => {
      const value = scenario.objectives[mode].production.find(
        (candidate) => candidate.target === target,
      );
      if (value === undefined) {
        throw new Error(`Missing target ${target} for ${scenario.scenarioId}.`);
      }
      return { scenarioId: scenario.scenarioId, value };
    });
    const actualSizes = observations.map(({ value }) => value.actualSize);
    const regrets = observations
      .map(({ value }) => value.regretMinutes)
      .filter((value): value is number => value !== null);
    const misses = observations
      .filter(({ value }) => !value.winnerIncluded && value.regretMinutes !== null)
      .map(({ scenarioId, value }) => ({
        scenarioId,
        regretMinutes: value.regretMinutes!,
      }));
    return {
      target,
      scenarioCount: observations.length,
      actualSize: {
        minimum: Math.min(...actualSizes),
        median: percentile(actualSizes, 0.5)!,
        maximum: Math.max(...actualSizes),
        mean: round(mean(actualSizes), 3),
      },
      winnerInclusionRate: round(
        observations.filter(({ value }) => value.winnerIncluded).length /
          observations.length,
        6,
      ),
      fullTopThreeRate: round(
        observations.filter(({ value }) => value.fullTopThree).length /
          observations.length,
        6,
      ),
      averageTopThreeFraction: round(
        mean(observations.map(({ value }) => value.topThreeFraction)),
        6,
      ),
      fullTopTenRate: round(
        observations.filter(({ value }) => value.fullTopTen).length /
          observations.length,
        6,
      ),
      averageTopTenFraction: round(
        mean(observations.map(({ value }) => value.topTenFraction)),
        6,
      ),
      winnerMissRegretMinutes: distribution(
        misses.map(({ regretMinutes }) => regretMinutes),
      ),
      allScenarioRegretMinutes: distribution(regrets),
      worstRegretScenarios: misses
        .sort(
          (left, right) =>
            right.regretMinutes - left.regretMinutes ||
            compareIds(left.scenarioId, right.scenarioId),
        )
        .slice(0, 5),
    };
  });
}

async function main(): Promise<void> {
  const options = parseCliOptions(process.argv.slice(2));
  const started = performance.now();
  const [catalogBytes, scenarioBytes] = await Promise.all([
    readFile(options.catalogPath),
    readFile(options.scenarioPath),
  ]);
  const catalogSha256 = sha256(catalogBytes);
  if (catalogSha256 !== EXPECTED_NATIONAL_CATALOG_SHA256) {
    throw new Error(
      `Expected national catalog SHA-256 ${EXPECTED_NATIONAL_CATALOG_SHA256}; received ${catalogSha256}.`,
    );
  }
  const catalog = normalizeCatalog(JSON.parse(catalogBytes.toString("utf8")));
  const allScenarios = validateScenarioCorpus(
    JSON.parse(scenarioBytes.toString("utf8")),
  );
  const selectedScenarios =
    options.scenarioIds.length === 0
      ? allScenarios
      : allScenarios.filter(({ id }) => options.scenarioIds.includes(id));
  if (selectedScenarios.length !== (options.scenarioIds.length || allScenarios.length)) {
    throw new Error("One or more requested scenario IDs do not exist.");
  }
  const courseById = new Map(catalog.courses.map((course) => [course.id, course]));
  const plans = selectedScenarios.map((scenario) =>
    buildScenarioPlan(scenario, catalog.courses),
  );
  const planSummary = createPreflightSummary(
    plans,
    catalogSha256,
    catalog.snapshot,
    sha256(scenarioBytes),
    options,
  );
  await writeJsonAtomically(
    resolve(options.artifactRoot, "preflight.json"),
    planSummary,
  );
  console.log(formatPreflight(planSummary));
  if (options.preflight) {
    return;
  }

  const totalMissingRequests = {
    value: await countMissingRequests(plans, courseById, options, catalogSha256),
  };
  if (options.route && totalMissingRequests.value > 500) {
    throw new Error(
      `The run needs ${totalMissingRequests.value} provider requests, above the published 500-request daily quota.`,
    );
  }
  const lastNetworkStart = { value: 0 };
  const scenarioAnalyses: ScenarioAnalysis[] = [];
  const observations: ProviderObservation[] = [];
  let cacheHits = 0;
  let providerRequests = 0;
  for (const plan of plans) {
    const routing = await obtainScenarioMatrix(
      plan,
      courseById,
      options,
      catalogSha256,
      options.route,
      totalMissingRequests,
      lastNetworkStart,
    );
    cacheHits += routing.cacheHits;
    providerRequests += routing.providerRequests;
    observations.push(...routing.providerObservations);
    scenarioAnalyses.push(analyzeScenario(plan, courseById, routing.matrix));
  }

  const summary: BenchmarkSummary = {
    schemaVersion: SUMMARY_SCHEMA_VERSION,
    inputs: {
      catalogPath: options.catalogPath,
      catalogSha256,
      catalogSnapshot: catalog.snapshot,
      catalogCourseCount: catalog.courses.length,
      scenarioPath: options.scenarioPath,
      scenarioSha256: sha256(scenarioBytes),
      scenarioCount: plans.length,
    },
    provider: {
      identity: "openrouteservice-compatible",
      baseUrl: options.providerBaseUrl,
      profile: PROVIDER_PROFILE,
      matrixCellLimit: MATRIX_CELL_LIMIT,
      requestIntervalMilliseconds: PROVIDER_REQUEST_INTERVAL_MILLISECONDS,
      cacheSchemaVersion: CACHE_SCHEMA_VERSION,
      quotaHeaders: observations
        .map(({ responseHeaders }) => responseHeaders)
        .filter((headers) => Object.keys(headers).length > 0),
    },
    evaluation: {
      shortlistTargets: SHORTLIST_TARGETS,
      ordinaryReferenceSize: ORDINARY_REFERENCE_SIZE,
      expandedReferenceSize: EXPANDED_REFERENCE_SIZE,
      expandedScenarioCount: plans.filter(
        ({ scenario }) => scenario.expandedReference,
      ).length,
      candidatesRouted: plans.reduce(
        (sum, { referenceCandidateIds }) => sum + referenceCandidateIds.length,
        0,
      ),
      matrixCells: plans.reduce(
        (sum, plan) =>
          sum + plan.scenario.origins.length * plan.referenceCandidateIds.length,
        0,
      ),
      providerRequestsRepresented: observations.length,
      providerLatencyMilliseconds: distribution(
        observations.map(({ latencyMilliseconds }) => latencyMilliseconds),
      ),
    },
    aggregates: {
      [RANKING_MODES.PROTECT_FARTHEST_TRAVELER]: aggregate(
        scenarioAnalyses,
        RANKING_MODES.PROTECT_FARTHEST_TRAVELER,
      ),
      [RANKING_MODES.LOWEST_TOTAL_TRAVEL]: aggregate(
        scenarioAnalyses,
        RANKING_MODES.LOWEST_TOTAL_TRAVEL,
      ),
    },
    scenarios: scenarioAnalyses,
  };
  await writeJsonAtomically(
    resolve(options.artifactRoot, "benchmark-summary.json"),
    summary,
  );
  const replayMilliseconds = round(performance.now() - started, 3);
  await writeJsonAtomically(
    resolve(options.artifactRoot, "last-replay-observation.json"),
    {
      cacheHits,
      providerRequests,
      elapsedMilliseconds: replayMilliseconds,
    },
  );
  console.log(
    `analysis complete: ${cacheHits} cache hits, ${providerRequests} provider requests, ${replayMilliseconds} ms`,
  );
}

function createPreflightSummary(
  plans: readonly ScenarioPlan[],
  catalogSha256: string,
  catalogSnapshot: string,
  scenarioSha256: string,
  options: CliOptions,
) {
  const scenarios = plans.map((plan) => {
    const batches = planMatrixBatches(
      plan.scenario.origins.length,
      plan.referenceCandidateIds,
    );
    return {
      id: plan.scenario.id,
      label: plan.scenario.label,
      categories: plan.scenario.categories,
      originCount: plan.scenario.origins.length,
      requestedReferenceSize: plan.requestedReferenceSize,
      actualReferenceSize: plan.referenceCandidateIds.length,
      productionActualSizes: Object.fromEntries(
        plan.productionShortlists.map(({ target, actualSize }) => [target, actualSize]),
      ),
      referenceSourceCounts: plan.referenceSourceCounts,
      batches: batches.map(({ candidateIds, cellCount }) => ({
        candidates: candidateIds.length,
        cells: cellCount,
      })),
    };
  });
  return {
    schemaVersion: 1,
    catalog: { sha256: catalogSha256, snapshot: catalogSnapshot },
    scenarioSha256,
    provider: {
      baseUrl: options.providerBaseUrl,
      profile: PROVIDER_PROFILE,
      matrixCellLimit: MATRIX_CELL_LIMIT,
      publishedRequestQuotaPerDay: 500,
      publishedRequestQuotaPerMinute: 40,
      requestIntervalMilliseconds: PROVIDER_REQUEST_INTERVAL_MILLISECONDS,
    },
    totals: {
      scenarios: plans.length,
      candidates: plans.reduce(
        (sum, { referenceCandidateIds }) => sum + referenceCandidateIds.length,
        0,
      ),
      matrixCells: scenarios.reduce(
        (sum, { batches }) =>
          sum + batches.reduce((subtotal, { cells }) => subtotal + cells, 0),
        0,
      ),
      requests: scenarios.reduce((sum, { batches }) => sum + batches.length, 0),
    },
    scenarios,
  };
}

async function countMissingRequests(
  plans: readonly ScenarioPlan[],
  courseById: ReadonlyMap<string, BenchmarkCourse>,
  options: CliOptions,
  catalogSha256: string,
): Promise<number> {
  let missing = 0;
  for (const plan of plans) {
    for (const batch of planMatrixBatches(
      plan.scenario.origins.length,
      plan.referenceCandidateIds,
    )) {
      const candidates = batch.candidateIds.map((id) => requiredCourse(courseById, id));
      const context: CacheContext = {
        catalogSha256,
        scenario: {
          id: plan.scenario.id,
          origins: plan.scenario.origins.map(({ id, label, coordinates }) => ({
            id,
            label,
            latitude: coordinates.latitude,
            longitude: coordinates.longitude,
          })),
        },
        candidates: candidates.map(({ id, coordinates }) => ({
          id,
          latitude: coordinates.latitude,
          longitude: coordinates.longitude,
        })),
        provider: {
          baseUrl: options.providerBaseUrl,
          profile: PROVIDER_PROFILE,
          metrics: ["duration"],
          resolveLocations: false,
        },
      };
      const key = createMatrixCacheKey(context);
      const path = resolve(
        options.artifactRoot,
        "cache",
        plan.scenario.id,
        `${batch.index.toString().padStart(2, "0")}-${key}.json`,
      );
      if ((await readBatchCache(path, key)) === null) {
        missing += 1;
      }
    }
  }
  return missing;
}

function parseCliOptions(arguments_: readonly string[]): CliOptions {
  const { values } = parseArgs({
    args: [...arguments_],
    strict: true,
    options: {
      catalog: { type: "string" },
      scenarios: { type: "string" },
      artifacts: { type: "string" },
      "provider-base-url": { type: "string" },
      "timeout-ms": { type: "string" },
      scenario: { type: "string", multiple: true },
      route: { type: "boolean" },
      preflight: { type: "boolean" },
    },
  });
  if (values.route === true && values.preflight === true) {
    throw new Error("Use either --route or --preflight, not both.");
  }
  const timeoutMilliseconds = Number(values["timeout-ms"] ?? 180_000);
  if (!Number.isFinite(timeoutMilliseconds) || timeoutMilliseconds <= 0) {
    throw new Error("--timeout-ms must be a finite positive number.");
  }
  return {
    catalogPath: resolve(
      values.catalog ??
        ".local/contiguous-us-osm-rehearsal/contiguous-us-catalog-first.json",
    ),
    scenarioPath: resolve(
      values.scenarios ?? "benchmark/national-shortlisting-scenarios.json",
    ),
    artifactRoot: resolve(
      values.artifacts ?? ".local/national-shortlisting-benchmark",
    ),
    providerBaseUrl:
      values["provider-base-url"] ??
      process.env.MIDPOINT_OPENROUTESERVICE_BASE_URL ??
      DEFAULT_PROVIDER_BASE_URL,
    timeoutMilliseconds,
    route: values.route ?? false,
    preflight: values.preflight ?? false,
    scenarioIds: values.scenario ?? [],
  };
}

function formatPreflight(summary: ReturnType<typeof createPreflightSummary>): string {
  return [
    "National shortlisting benchmark preflight",
    `Catalog SHA-256: ${summary.catalog.sha256}`,
    `Scenarios: ${summary.totals.scenarios}`,
    `Reference candidates: ${summary.totals.candidates}`,
    `Matrix cells: ${summary.totals.matrixCells}`,
    `Provider requests: ${summary.totals.requests}`,
    `Provider: ${summary.provider.baseUrl} (${summary.provider.profile})`,
    "All route caches and outputs remain under ignored .local/.",
  ].join("\n");
}

function exactNameDuplicateSlots(courses: readonly BenchmarkCourse[]): number {
  const counts = new Map<string, number>();
  for (const { sourceName } of courses) {
    if (sourceName === null) {
      continue;
    }
    const normalized = sourceName.trim().toLocaleLowerCase("en-US").replace(/\s+/gu, " ");
    counts.set(normalized, (counts.get(normalized) ?? 0) + 1);
  }
  return [...counts.values()].reduce(
    (total, count) => total + Math.max(0, count - 1),
    0,
  );
}

function objectiveMinutes(
  metrics: {
    readonly maximumTravelTimeMinutes: number;
    readonly totalTravelTimeMinutes: number;
  },
  mode: RankingMode,
): number {
  return mode === RANKING_MODES.PROTECT_FARTHEST_TRAVELER
    ? metrics.maximumTravelTimeMinutes
    : metrics.totalTravelTimeMinutes;
}

function distribution(values: readonly number[]): DistributionSummary {
  return {
    count: values.length,
    median: percentile(values, 0.5),
    p90: percentile(values, 0.9),
    maximum: values.length === 0 ? null : round(Math.max(...values), 6),
    total: round(values.reduce((sum, value) => sum + value, 0), 6),
  };
}

function percentile(values: readonly number[], fraction: number): number | null {
  if (values.length === 0) {
    return null;
  }
  const sorted = [...values].sort((left, right) => left - right);
  return round(sorted[Math.max(0, Math.ceil(fraction * sorted.length) - 1)]!, 6);
}

function mean(values: readonly number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function sameSet(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value) => right.includes(value));
}

function unique(values: readonly string[]): readonly string[] {
  return [...new Set(values)];
}

function requiredCourse(
  courseById: ReadonlyMap<string, BenchmarkCourse>,
  id: string,
): BenchmarkCourse {
  const course = courseById.get(id);
  if (course === undefined) {
    throw new Error(`Unknown catalog course "${id}".`);
  }
  return course;
}

function haversineKilometers(
  from: { readonly latitude: number; readonly longitude: number },
  to: { readonly latitude: number; readonly longitude: number },
): number {
  const latitudeDifference = degreesToRadians(to.latitude - from.latitude);
  const longitudeDifference = degreesToRadians(to.longitude - from.longitude);
  const value =
    Math.sin(latitudeDifference / 2) ** 2 +
    Math.cos(degreesToRadians(from.latitude)) *
      Math.cos(degreesToRadians(to.latitude)) *
      Math.sin(longitudeDifference / 2) ** 2;
  return (
    2 *
    EARTH_RADIUS_KILOMETERS *
    Math.asin(Math.sqrt(Math.min(1, value)))
  );
}

function initialBearingDegrees(
  from: { readonly latitude: number; readonly longitude: number },
  to: { readonly latitude: number; readonly longitude: number },
): number {
  const fromLatitude = degreesToRadians(from.latitude);
  const toLatitude = degreesToRadians(to.latitude);
  const longitudeDifference = degreesToRadians(to.longitude - from.longitude);
  const y = Math.sin(longitudeDifference) * Math.cos(toLatitude);
  const x =
    Math.cos(fromLatitude) * Math.sin(toLatitude) -
    Math.sin(fromLatitude) *
      Math.cos(toLatitude) *
      Math.cos(longitudeDifference);
  return (((Math.atan2(y, x) * 180) / Math.PI + 360) % 360);
}

function degreesToRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

function selectedProviderHeaders(headers: Headers): Readonly<Record<string, string>> {
  const selected: Record<string, string> = {};
  for (const name of [
    "date",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-rate-limit-limit",
    "x-rate-limit-remaining",
    "x-rate-limit-reset",
  ]) {
    const value = headers.get(name);
    if (value !== null) {
      selected[name] = value;
    }
  }
  return selected;
}

function parseJsonIfPossible(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

async function writeJsonAtomically(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const temporaryPath = `${path}.${process.pid}.tmp`;
  await writeFile(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(temporaryPath, path);
}

function sha256(value: string | Uint8Array): string {
  return createHash("sha256").update(value).digest("hex");
}

function round(value: number, digits: number): number {
  const scale = 10 ** digits;
  return Math.round((value + Number.EPSILON) * scale) / scale;
}

function compareIds(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNodeError(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && "code" in error;
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((accept) => setTimeout(accept, milliseconds));
}

const mainPath = process.argv[1] === undefined ? undefined : resolve(process.argv[1]);
if (mainPath !== undefined && import.meta.url === pathToFileURL(mainPath).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
