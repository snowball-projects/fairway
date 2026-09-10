import { createHash } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import {
  buildCandidateSourceOrders,
  buildScenarioPlan,
  EXPECTED_NATIONAL_CATALOG_SHA256,
  loadCachedScenarioMatrix,
  normalizeCatalog,
  POLICY_CANDIDATE_SOURCES,
  validateScenarioCorpus,
  type BenchmarkCourse,
  type BenchmarkScenario,
  type CandidateSourceOrders,
  type PolicyCandidateSource,
} from "./national-shortlisting-benchmark.ts";
import {
  rankDestinationsForAllModes,
  RANKING_MODES,
  type RankDestinationsResult,
  type RankingMode,
  type TravelTimeMatrix,
} from "../src/core/ranking.ts";

export const EXACT_BUDGETS = [40, 60, 80, 100] as const;
export const PROGRESSIVE_TRANCHE_SIZE = 20;
export const EXPECTED_SCENARIO_SHA256 =
  "189e91154d5f18876e61cec783a85082127fb172e70b2c033ef2f3ab30bce6c1";
export const EXPECTED_BENCHMARK_SUMMARY_SHA256 =
  "70e3c33bd796e3ca9eed98775abcac56eae21ad42f299e46d95caaa77cb6506c";

const CATALOG_PATH = resolve(
  ".local/contiguous-us-osm-rehearsal/contiguous-us-catalog-first.json",
);
const SCENARIO_PATH = resolve("benchmark/national-shortlisting-scenarios.json");
const BENCHMARK_ARTIFACT_ROOT = resolve(
  ".local/national-shortlisting-benchmark",
);
const COMPARISON_ARTIFACT_ROOT = resolve(
  ".local/national-shortlisting-policy-comparison",
);
const SUMMARY_PATH = resolve(COMPARISON_ARTIFACT_ROOT, "comparison-summary.json");

export type PolicyId = "A" | "B" | "C" | "D" | "E";

export interface ShortlistPolicy {
  readonly id: PolicyId;
  readonly name: string;
  readonly rationale: string;
  readonly trancheQuota: Readonly<Record<PolicyCandidateSource, number>>;
  readonly sourceOrder: readonly PolicyCandidateSource[];
  readonly overflowOrder: readonly PolicyCandidateSource[];
}

const ZERO_QUOTA = Object.fromEntries(
  POLICY_CANDIDATE_SOURCES.map((source) => [source, 0]),
) as Record<PolicyCandidateSource, number>;

function trancheQuota(
  values: Partial<Record<PolicyCandidateSource, number>>,
): Readonly<Record<PolicyCandidateSource, number>> {
  return { ...ZERO_QUOTA, ...values };
}

export const SHORTLIST_POLICIES = [
  {
    id: "A",
    name: "exact-budget current design",
    rationale:
      "Equal capacity for the two anchor-local and two global objective sources.",
    trancheQuota: trancheQuota({
      "minimum-total-local": 5,
      "minimum-maximum-local": 5,
      "minimum-total-haversine": 5,
      "minimum-maximum-haversine": 5,
    }),
    sourceOrder: [
      "minimum-total-local",
      "minimum-maximum-local",
      "minimum-total-haversine",
      "minimum-maximum-haversine",
    ],
    overflowOrder: [
      "minimum-total-local",
      "minimum-maximum-local",
      "minimum-total-haversine",
      "minimum-maximum-haversine",
    ],
  },
  {
    id: "B",
    name: "objective-balanced global depth",
    rationale:
      "Reserve most capacity for equally deep minimum-total and minimum-maximum global orders.",
    trancheQuota: trancheQuota({
      "minimum-total-local": 2,
      "minimum-maximum-local": 2,
      "minimum-total-haversine": 8,
      "minimum-maximum-haversine": 8,
    }),
    sourceOrder: [
      "minimum-total-local",
      "minimum-maximum-local",
      "minimum-total-haversine",
      "minimum-maximum-haversine",
    ],
    overflowOrder: [
      "minimum-total-haversine",
      "minimum-maximum-haversine",
      "minimum-total-local",
      "minimum-maximum-local",
    ],
  },
  {
    id: "C",
    name: "origin coverage",
    rationale:
      "Add round-robin origin-nearest capacity while retaining both local and global objectives.",
    trancheQuota: trancheQuota({
      "minimum-total-local": 2,
      "minimum-maximum-local": 2,
      "minimum-total-haversine": 4,
      "minimum-maximum-haversine": 4,
      "origin-nearest-coverage": 8,
    }),
    sourceOrder: [
      "minimum-total-local",
      "minimum-maximum-local",
      "minimum-total-haversine",
      "minimum-maximum-haversine",
      "origin-nearest-coverage",
    ],
    overflowOrder: [
      "origin-nearest-coverage",
      "minimum-total-haversine",
      "minimum-maximum-haversine",
      "minimum-total-local",
      "minimum-maximum-local",
    ],
  },
  {
    id: "D",
    name: "radial coverage",
    rationale:
      "Add deterministic direction-and-ring coverage while retaining both local and global objectives.",
    trancheQuota: trancheQuota({
      "minimum-total-local": 2,
      "minimum-maximum-local": 2,
      "minimum-total-haversine": 4,
      "minimum-maximum-haversine": 4,
      "radial-coverage": 8,
    }),
    sourceOrder: [
      "minimum-total-local",
      "minimum-maximum-local",
      "minimum-total-haversine",
      "minimum-maximum-haversine",
      "radial-coverage",
    ],
    overflowOrder: [
      "radial-coverage",
      "minimum-total-haversine",
      "minimum-maximum-haversine",
      "minimum-total-local",
      "minimum-maximum-local",
    ],
  },
  {
    id: "E",
    name: "combined coverage",
    rationale:
      "Combine both anchors, both global objectives, origin-nearest coverage, and radial coverage.",
    trancheQuota: trancheQuota({
      "minimum-total-local": 1,
      "minimum-maximum-local": 1,
      "minimum-total-haversine": 4,
      "minimum-maximum-haversine": 4,
      "origin-nearest-coverage": 5,
      "radial-coverage": 5,
    }),
    sourceOrder: [...POLICY_CANDIDATE_SOURCES],
    overflowOrder: [
      "origin-nearest-coverage",
      "radial-coverage",
      "minimum-total-haversine",
      "minimum-maximum-haversine",
      "minimum-total-local",
      "minimum-maximum-local",
    ],
  },
] as const satisfies readonly ShortlistPolicy[];

export interface ExactBudgetShortlist {
  readonly budget: number;
  readonly actualSize: number;
  readonly eligibleCandidateCount: number;
  readonly shortfallReason: string | null;
  readonly candidateIds: readonly string[];
  readonly quota: Readonly<Record<PolicyCandidateSource, number>>;
  readonly quotaUnionSize: number;
  readonly unusedQuotaBySource: Readonly<Record<PolicyCandidateSource, number>>;
  readonly unusedQuota: number;
  readonly duplicateSlotsAvoided: number;
  readonly backfillCount: number;
  readonly sourceContributionCounts: Readonly<
    Record<PolicyCandidateSource, number>
  >;
  readonly backfillSourceCounts: Readonly<
    Record<PolicyCandidateSource, number>
  >;
  readonly candidates: readonly {
    readonly id: string;
    readonly selectionSource: PolicyCandidateSource;
    readonly selectionKind: "quota" | "backfill";
    readonly sourceRanks: Readonly<Record<PolicyCandidateSource, number>>;
  }[];
}

interface SelectedCandidate {
  readonly id: string;
  readonly selectionSource: PolicyCandidateSource;
}

export function quotaForBudget(
  policy: ShortlistPolicy,
  budget: number,
): Readonly<Record<PolicyCandidateSource, number>> {
  if (
    !Number.isInteger(budget) ||
    budget < PROGRESSIVE_TRANCHE_SIZE ||
    budget % PROGRESSIVE_TRANCHE_SIZE !== 0
  ) {
    throw new Error("Budget must be a positive multiple of the 20-candidate tranche.");
  }
  const multiplier = budget / PROGRESSIVE_TRANCHE_SIZE;
  return Object.fromEntries(
    POLICY_CANDIDATE_SOURCES.map((source) => [
      source,
      policy.trancheQuota[source] * multiplier,
    ]),
  ) as Record<PolicyCandidateSource, number>;
}

export function buildExactBudgetShortlists(
  candidateSources: CandidateSourceOrders,
  policy: ShortlistPolicy,
  budgets: readonly number[] = EXACT_BUDGETS,
): readonly ExactBudgetShortlist[] {
  validatePolicy(policy);
  const requestedBudgets = [...new Set(budgets)].sort(
    (left, right) => left - right,
  );
  if (requestedBudgets.length === 0) {
    return [];
  }
  requestedBudgets.forEach((budget) => quotaForBudget(policy, budget));
  const sourceRanks = sourceRankMaps(candidateSources.sources);
  const eligibleIds = new Set(
    policy.sourceOrder.flatMap((source) => candidateSources.sources[source]),
  );
  const selected: SelectedCandidate[] = [];
  const selectedIds = new Set<string>();
  const overflowPositions = Object.fromEntries(
    policy.overflowOrder.map((source) => [source, 0]),
  ) as Partial<Record<PolicyCandidateSource, number>>;
  const snapshots = new Map<number, ExactBudgetShortlist>();
  const maximumBudget = requestedBudgets.at(-1)!;

  for (
    let trancheTarget = PROGRESSIVE_TRANCHE_SIZE;
    trancheTarget <= maximumBudget;
    trancheTarget += PROGRESSIVE_TRANCHE_SIZE
  ) {
    const previousQuota =
      trancheTarget === PROGRESSIVE_TRANCHE_SIZE
        ? ZERO_QUOTA
        : quotaForBudget(policy, trancheTarget - PROGRESSIVE_TRANCHE_SIZE);
    const quota = quotaForBudget(policy, trancheTarget);

    for (const source of policy.sourceOrder) {
      const list = candidateSources.sources[source];
      for (
        let index = previousQuota[source];
        index < Math.min(quota[source], list.length);
        index += 1
      ) {
        addSelected(list[index]!, source, selected, selectedIds);
      }
    }

    while (
      selected.length < trancheTarget &&
      selected.length < eligibleIds.size
    ) {
      let advanced = false;
      for (const source of policy.overflowOrder) {
        const list = candidateSources.sources[source];
        let position = Math.max(overflowPositions[source] ?? 0, quota[source]);
        while (position < list.length && selectedIds.has(list[position]!)) {
          position += 1;
        }
        const id = list[position];
        overflowPositions[source] = position + (id === undefined ? 0 : 1);
        if (id !== undefined) {
          addSelected(id, source, selected, selectedIds);
          advanced = true;
        }
        if (selected.length >= trancheTarget) {
          break;
        }
      }
      if (!advanced) {
        break;
      }
    }

    if (requestedBudgets.includes(trancheTarget)) {
      snapshots.set(
        trancheTarget,
        snapshotShortlist(
          candidateSources,
          policy,
          trancheTarget,
          selected,
          eligibleIds.size,
          sourceRanks,
        ),
      );
    }
  }

  return requestedBudgets.map((budget) => snapshots.get(budget)!);
}

function snapshotShortlist(
  candidateSources: CandidateSourceOrders,
  policy: ShortlistPolicy,
  budget: number,
  selected: readonly SelectedCandidate[],
  eligibleCandidateCount: number,
  sourceRanks: Readonly<
    Record<PolicyCandidateSource, ReadonlyMap<string, number>>
  >,
): ExactBudgetShortlist {
  const quota = quotaForBudget(policy, budget);
  const quotaIds = new Set<string>();
  const unusedQuotaBySource = { ...ZERO_QUOTA };
  for (const source of policy.sourceOrder) {
    for (const id of candidateSources.sources[source].slice(0, quota[source])) {
      if (quotaIds.has(id)) {
        unusedQuotaBySource[source] += 1;
      }
      quotaIds.add(id);
    }
  }
  const current = selected.slice(0, Math.min(budget, selected.length));
  const backfilled = current.filter(({ id }) => !quotaIds.has(id));
  const sourceContributionCounts = { ...ZERO_QUOTA };
  const backfillSourceCounts = { ...ZERO_QUOTA };
  for (const candidate of current) {
    sourceContributionCounts[candidate.selectionSource] += 1;
    if (!quotaIds.has(candidate.id)) {
      backfillSourceCounts[candidate.selectionSource] += 1;
    }
  }
  const duplicateSlotsAvoided = Object.values(unusedQuotaBySource).reduce(
    (sum, value) => sum + value,
    0,
  );
  return {
    budget,
    actualSize: current.length,
    eligibleCandidateCount,
    shortfallReason:
      current.length === budget
        ? null
        : eligibleCandidateCount < budget
          ? `Only ${eligibleCandidateCount} eligible unique candidates exist.`
          : "Candidate sources were exhausted before the declared budget.",
    candidateIds: current.map(({ id }) => id),
    quota,
    quotaUnionSize: quotaIds.size,
    unusedQuotaBySource,
    unusedQuota: duplicateSlotsAvoided,
    duplicateSlotsAvoided,
    backfillCount: backfilled.length,
    sourceContributionCounts,
    backfillSourceCounts,
    candidates: current.map(({ id, selectionSource }) => ({
      id,
      selectionSource,
      selectionKind: quotaIds.has(id) ? "quota" : "backfill",
      sourceRanks: Object.fromEntries(
        POLICY_CANDIDATE_SOURCES.map((source) => [
          source,
          sourceRanks[source].get(id) ?? candidateSources.sources[source].length + 1,
        ]),
      ) as Record<PolicyCandidateSource, number>,
    })),
  };
}

function addSelected(
  id: string,
  source: PolicyCandidateSource,
  selected: SelectedCandidate[],
  selectedIds: Set<string>,
): void {
  if (!selectedIds.has(id)) {
    selected.push({ id, selectionSource: source });
    selectedIds.add(id);
  }
}

function sourceRankMaps(
  sources: CandidateSourceOrders["sources"],
): Readonly<Record<PolicyCandidateSource, ReadonlyMap<string, number>>> {
  return Object.fromEntries(
    POLICY_CANDIDATE_SOURCES.map((source) => {
      const ids = sources[source];
      if (new Set(ids).size !== ids.length) {
        throw new Error(`Candidate source "${source}" contains duplicate IDs.`);
      }
      return [source, new Map(ids.map((id, index) => [id, index + 1]))];
    }),
  ) as Record<PolicyCandidateSource, ReadonlyMap<string, number>>;
}

function validatePolicy(policy: ShortlistPolicy): void {
  const quotaTotal = POLICY_CANDIDATE_SOURCES.reduce(
    (sum, source) => sum + policy.trancheQuota[source],
    0,
  );
  if (quotaTotal !== PROGRESSIVE_TRANCHE_SIZE) {
    throw new Error(
      `Policy ${policy.id} tranche quotas total ${quotaTotal}, not ${PROGRESSIVE_TRANCHE_SIZE}.`,
    );
  }
  const quotaSources = POLICY_CANDIDATE_SOURCES.filter(
    (source) => policy.trancheQuota[source] > 0,
  );
  if (
    new Set(policy.sourceOrder).size !== policy.sourceOrder.length ||
    new Set(policy.overflowOrder).size !== policy.overflowOrder.length ||
    quotaSources.some((source) => !policy.sourceOrder.includes(source)) ||
    policy.sourceOrder.some((source) => policy.trancheQuota[source] === 0) ||
    policy.sourceOrder.some((source) => !policy.overflowOrder.includes(source))
  ) {
    throw new Error(`Policy ${policy.id} has inconsistent source ordering.`);
  }
}

interface ScenarioObjectiveObservation {
  readonly scenarioId: string;
  readonly originCount: number;
  readonly policyId: PolicyId;
  readonly budget: number;
  readonly mode: RankingMode;
  readonly winnerIncluded: boolean;
  readonly topThreeIncluded: number;
  readonly topThreeFraction: number;
  readonly fullTopThree: boolean;
  readonly topTenIncluded: number;
  readonly topTenFraction: number;
  readonly fullTopTen: boolean;
  readonly regretMinutes: number | null;
  readonly totalRegretPerOriginMinutes: number | null;
  readonly referenceWinner: CourseSummary | null;
  readonly shortlistWinner: CourseSummary | null;
  readonly winnerSelectionSource: PolicyCandidateSource | null;
  readonly failure: FailureAnalysis | null;
}

interface CourseSummary {
  readonly id: string;
  readonly name: string;
  readonly objectiveMinutes: number;
}

interface FailureAnalysis {
  readonly cause:
    | "quota-competition"
    | "insufficient-local-anchor-depth"
    | "insufficient-global-objective-depth"
    | "insufficient-origin-relative-depth"
    | "insufficient-radial-depth"
    | "deduplication"
    | "routing-exclusion"
    | "reference-pool-limitation";
  readonly bestSource: PolicyCandidateSource;
  readonly bestSourceRank: number;
  readonly sourceRanks: Readonly<Record<PolicyCandidateSource, number>>;
  readonly quotas: Readonly<Record<PolicyCandidateSource, number>>;
}

interface Distribution {
  readonly count: number;
  readonly median: number | null;
  readonly p90: number | null;
  readonly maximum: number | null;
}

async function main(): Promise<void> {
  const started = performance.now();
  const [catalogBytes, scenarioBytes, benchmarkSummaryBytes] = await Promise.all([
    readFile(CATALOG_PATH),
    readFile(SCENARIO_PATH),
    readFile(resolve(BENCHMARK_ARTIFACT_ROOT, "benchmark-summary.json")),
  ]);
  const catalogSha256 = sha256(catalogBytes);
  const scenarioSha256 = sha256(scenarioBytes);
  const benchmarkSummarySha256 = sha256(benchmarkSummaryBytes);
  assertExpectedHash(
    "national catalog",
    catalogSha256,
    EXPECTED_NATIONAL_CATALOG_SHA256,
  );
  assertExpectedHash(
    "scenario fixture",
    scenarioSha256,
    EXPECTED_SCENARIO_SHA256,
  );
  assertExpectedHash(
    "cached benchmark summary",
    benchmarkSummarySha256,
    EXPECTED_BENCHMARK_SUMMARY_SHA256,
  );

  const catalog = normalizeCatalog(JSON.parse(catalogBytes.toString("utf8")));
  const scenarios = validateScenarioCorpus(
    JSON.parse(scenarioBytes.toString("utf8")),
  );
  const courseById = new Map(catalog.courses.map((course) => [course.id, course]));
  const observations: ScenarioObjectiveObservation[] = [];
  const shortlistSnapshots: {
    readonly scenarioId: string;
    readonly policyId: PolicyId;
    readonly shortlist: ExactBudgetShortlist;
  }[] = [];
  const nestedness: {
    readonly scenarioId: string;
    readonly policyId: PolicyId;
    readonly fromBudget: number;
    readonly toBudget: number;
    readonly nested: boolean;
    readonly removedCandidateIds: readonly string[];
  }[] = [];

  for (const scenario of scenarios) {
    const plan = buildScenarioPlan(scenario, catalog.courses);
    const matrix = await loadCachedScenarioMatrix(plan, courseById, {
      artifactRoot: BENCHMARK_ARTIFACT_ROOT,
      catalogSha256,
    });
    const matrixIds = new Set(Object.keys(matrix));
    const candidateSources = buildCandidateSourceOrders(
      scenario.origins.map(({ id, coordinates }) => ({ id, coordinates })),
      catalog.courses,
    );
    const referenceCourses = plan.referenceCandidateIds.map((id) =>
      requiredCourse(courseById, id),
    );
    const referenceRankings = rank(referenceCourses, scenario, matrix);

    for (const policy of SHORTLIST_POLICIES) {
      const shortlists = buildExactBudgetShortlists(candidateSources, policy);
      for (let index = 1; index < shortlists.length; index += 1) {
        const previous = shortlists[index - 1]!;
        const current = shortlists[index]!;
        const currentIds = new Set(current.candidateIds);
        const removedCandidateIds = previous.candidateIds.filter(
          (id) => !currentIds.has(id),
        );
        nestedness.push({
          scenarioId: scenario.id,
          policyId: policy.id,
          fromBudget: previous.budget,
          toBudget: current.budget,
          nested: removedCandidateIds.length === 0,
          removedCandidateIds,
        });
      }
      for (const shortlist of shortlists) {
        shortlistSnapshots.push({
          scenarioId: scenario.id,
          policyId: policy.id,
          shortlist,
        });
        const missingMatrixIds = shortlist.candidateIds.filter(
          (id) => !matrixIds.has(id),
        );
        if (missingMatrixIds.length > 0) {
          throw new Error(
            `Cached reference matrix for "${scenario.id}" lacks policy ${policy.id} budget ${shortlist.budget} columns: ${missingMatrixIds.join(", ")}`,
          );
        }
        const shortlistCourses = shortlist.candidateIds.map((id) =>
          requiredCourse(courseById, id),
        );
        const shortlistRankings = rank(shortlistCourses, scenario, matrix);
        for (const mode of Object.values(RANKING_MODES)) {
          observations.push(
            compareRankings(
              scenario,
              policy,
              shortlist,
              shortlistRankings[mode],
              referenceRankings[mode],
              candidateSources,
              mode,
            ),
          );
        }
      }
    }
  }

  const aggregates = Object.fromEntries(
    Object.values(RANKING_MODES).map((mode) => [
      mode,
      SHORTLIST_POLICIES.flatMap((policy) =>
        EXACT_BUDGETS.map((budget) =>
          aggregateObservations(
            observations.filter(
              (observation) =>
                observation.mode === mode &&
                observation.policyId === policy.id &&
                observation.budget === budget,
            ),
            shortlistSnapshots.filter(
              (snapshot) =>
                snapshot.policyId === policy.id &&
                snapshot.shortlist.budget === budget,
            ),
            policy,
            budget,
            mode,
          ),
        ),
      ),
    ]),
  );
  const operationalExactBudget = shortlistSnapshots.every(
    ({ shortlist }) =>
      shortlist.actualSize <= shortlist.budget &&
      (shortlist.eligibleCandidateCount < shortlist.budget ||
        shortlist.actualSize === shortlist.budget),
  );
  const acceptance = SHORTLIST_POLICIES.flatMap((policy) =>
    EXACT_BUDGETS.map((budget) => {
      const maximum = aggregates[RANKING_MODES.PROTECT_FARTHEST_TRAVELER].find(
        (value) => value.policyId === policy.id && value.budget === budget,
      )!;
      const total = aggregates[RANKING_MODES.LOWEST_TOTAL_TRAVEL].find(
        (value) => value.policyId === policy.id && value.budget === budget,
      )!;
      const gates = {
        maximumWinnerInclusion: maximum.winnerInclusionRate >= 0.95,
        totalWinnerInclusion: total.winnerInclusionRate >= 0.95,
        maximumMissRegret:
          (maximum.winnerMissRegretMinutes.maximum ?? 0) <= 10,
        totalMissRegretPerOrigin:
          (total.winnerMissTotalRegretPerOriginMinutes.maximum ?? 0) <= 5,
        exactBudget: operationalExactBudget,
      };
      return {
        policyId: policy.id,
        budget,
        gates,
        meetsAll: Object.values(gates).every(Boolean),
      };
    }),
  );
  const summary = {
    schemaVersion: 1,
    inputs: {
      catalogPath: ".local/contiguous-us-osm-rehearsal/contiguous-us-catalog-first.json",
      catalogSha256,
      catalogSnapshot: catalog.snapshot,
      catalogCourseCount: catalog.courses.length,
      scenarioPath: "benchmark/national-shortlisting-scenarios.json",
      scenarioSha256,
      scenarioCount: scenarios.length,
      cachedBenchmarkSummaryPath:
        ".local/national-shortlisting-benchmark/benchmark-summary.json",
      cachedBenchmarkSummarySha256: benchmarkSummarySha256,
      cachedMatrixBatches: 29,
      publicNetworkRequests: 0,
    },
    evaluation: {
      budgets: EXACT_BUDGETS,
      progressiveTrancheSize: PROGRESSIVE_TRANCHE_SIZE,
      policyCount: SHORTLIST_POLICIES.length,
      rankingModes: Object.values(RANKING_MODES),
      operationalExactBudget,
    },
    policies: SHORTLIST_POLICIES.map((policy) => ({
      id: policy.id,
      name: policy.name,
      rationale: policy.rationale,
      sourceOrder: policy.sourceOrder,
      overflowOrder: policy.overflowOrder,
      quotaByBudget: Object.fromEntries(
        EXACT_BUDGETS.map((budget) => [budget, quotaForBudget(policy, budget)]),
      ),
    })),
    efficiency: efficiencySummary(scenarios),
    nestedness: {
      allNested: nestedness.every(({ nested }) => nested),
      comparisons: nestedness.length,
      violations: nestedness.filter(({ nested }) => !nested),
      byPolicy: SHORTLIST_POLICIES.map((policy) => ({
        policyId: policy.id,
        comparisons: nestedness.filter(({ policyId }) => policyId === policy.id)
          .length,
        violations: nestedness.filter(
          ({ policyId, nested }) => policyId === policy.id && !nested,
        ).length,
      })),
    },
    aggregates,
    acceptance,
    selectedConfigurations: acceptance.filter(({ meetsAll }) => meetsAll),
    scenarios: observations,
    shortlistDetails: shortlistSnapshots,
  };
  await writeJsonAtomically(SUMMARY_PATH, summary);
  await writeJsonAtomically(
    resolve(COMPARISON_ARTIFACT_ROOT, "last-run-observation.json"),
    {
      elapsedMilliseconds: round(performance.now() - started, 3),
      publicNetworkRequests: 0,
      summarySha256: sha256(await readFile(SUMMARY_PATH)),
    },
  );
  console.log(
    `policy comparison complete: ${scenarios.length} scenarios, ${SHORTLIST_POLICIES.length} policies, 0 public network requests`,
  );
  console.log(`summary: ${SUMMARY_PATH}`);
}

function compareRankings(
  scenario: BenchmarkScenario,
  policy: ShortlistPolicy,
  shortlist: ExactBudgetShortlist,
  result: RankDestinationsResult,
  reference: RankDestinationsResult,
  candidateSources: CandidateSourceOrders,
  mode: RankingMode,
): ScenarioObjectiveObservation {
  const selectedIds = new Set(shortlist.candidateIds);
  const selectedById = new Map(
    shortlist.candidates.map((candidate) => [candidate.id, candidate]),
  );
  const referenceTopThree = reference.rankedVenues.slice(0, 3);
  const referenceTopTen = reference.rankedVenues.slice(0, 10);
  const topThreeIncluded = referenceTopThree.filter(({ venue }) =>
    selectedIds.has(venue.id),
  ).length;
  const topTenIncluded = referenceTopTen.filter(({ venue }) =>
    selectedIds.has(venue.id),
  ).length;
  const referenceWinner = reference.rankedVenues[0];
  const shortlistWinner = result.rankedVenues[0];
  const regretMinutes =
    referenceWinner === undefined || shortlistWinner === undefined
      ? null
      : round(
          objectiveMinutes(shortlistWinner, mode) -
            objectiveMinutes(referenceWinner, mode),
          6,
        );
  const winnerIncluded =
    referenceWinner !== undefined && selectedIds.has(referenceWinner.venue.id);
  const winnerCandidate =
    referenceWinner === undefined
      ? undefined
      : selectedById.get(referenceWinner.venue.id);
  return {
    scenarioId: scenario.id,
    originCount: scenario.origins.length,
    policyId: policy.id,
    budget: shortlist.budget,
    mode,
    winnerIncluded,
    topThreeIncluded,
    topThreeFraction: fraction(topThreeIncluded, referenceTopThree.length),
    fullTopThree:
      referenceTopThree.length > 0 && topThreeIncluded === referenceTopThree.length,
    topTenIncluded,
    topTenFraction: fraction(topTenIncluded, referenceTopTen.length),
    fullTopTen:
      referenceTopTen.length > 0 && topTenIncluded === referenceTopTen.length,
    regretMinutes,
    totalRegretPerOriginMinutes:
      mode === RANKING_MODES.LOWEST_TOTAL_TRAVEL && regretMinutes !== null
        ? round(regretMinutes / scenario.origins.length, 6)
        : null,
    referenceWinner: summarizeCourse(referenceWinner, mode),
    shortlistWinner: summarizeCourse(shortlistWinner, mode),
    winnerSelectionSource: winnerCandidate?.selectionSource ?? null,
    failure:
      winnerIncluded || referenceWinner === undefined
        ? null
        : classifyFailure(
            referenceWinner.venue.id,
            shortlist,
            candidateSources,
            policy,
          ),
  };
}

function classifyFailure(
  winnerId: string,
  shortlist: ExactBudgetShortlist,
  candidateSources: CandidateSourceOrders,
  policy: ShortlistPolicy,
): FailureAnalysis {
  const ranks = Object.fromEntries(
    POLICY_CANDIDATE_SOURCES.map((source) => [
      source,
      candidateSources.sources[source].indexOf(winnerId) + 1,
    ]),
  ) as Record<PolicyCandidateSource, number>;
  const rankedSources = policy.sourceOrder
    .map((source) => ({ source, rank: ranks[source] }))
    .filter(({ rank }) => rank > 0)
    .sort(
      (left, right) =>
        left.rank - right.rank || compareIds(left.source, right.source),
    );
  if (rankedSources.length === 0) {
    return {
      cause: "reference-pool-limitation",
      bestSource: "minimum-total-local",
      bestSourceRank: 0,
      sourceRanks: ranks,
      quotas: shortlist.quota,
    };
  }
  const best = rankedSources[0]!;
  const withinSomeQuota = rankedSources.some(
    ({ source, rank }) => rank <= shortlist.quota[source],
  );
  let cause: FailureAnalysis["cause"];
  if (withinSomeQuota) {
    cause = "deduplication";
  } else if (best.rank <= shortlist.budget) {
    cause = "quota-competition";
  } else if (best.source.endsWith("-local")) {
    cause = "insufficient-local-anchor-depth";
  } else if (best.source.endsWith("-haversine")) {
    cause = "insufficient-global-objective-depth";
  } else if (best.source === "origin-nearest-coverage") {
    cause = "insufficient-origin-relative-depth";
  } else {
    cause = "insufficient-radial-depth";
  }
  return {
    cause,
    bestSource: best.source,
    bestSourceRank: best.rank,
    sourceRanks: ranks,
    quotas: shortlist.quota,
  };
}

function aggregateObservations(
  observations: readonly ScenarioObjectiveObservation[],
  snapshots: readonly {
    readonly scenarioId: string;
    readonly policyId: PolicyId;
    readonly shortlist: ExactBudgetShortlist;
  }[],
  policy: ShortlistPolicy,
  budget: number,
  mode: RankingMode,
) {
  if (observations.length === 0 || snapshots.length !== observations.length) {
    throw new Error(`Incomplete aggregate inputs for ${policy.id}/${budget}/${mode}.`);
  }
  const misses = observations.filter(({ winnerIncluded }) => !winnerIncluded);
  const regrets = observations
    .map(({ regretMinutes }) => regretMinutes)
    .filter((value): value is number => value !== null);
  const missRegrets = misses
    .map(({ regretMinutes }) => regretMinutes)
    .filter((value): value is number => value !== null);
  const totalPerOrigin = observations
    .map(({ totalRegretPerOriginMinutes }) => totalRegretPerOriginMinutes)
    .filter((value): value is number => value !== null);
  const missTotalPerOrigin = misses
    .map(({ totalRegretPerOriginMinutes }) => totalRegretPerOriginMinutes)
    .filter((value): value is number => value !== null);
  const actualSizes = snapshots.map(({ shortlist }) => shortlist.actualSize);
  return {
    policyId: policy.id,
    policyName: policy.name,
    budget,
    mode,
    scenarioCount: observations.length,
    winnerInclusionRate: round(
      observations.filter(({ winnerIncluded }) => winnerIncluded).length /
        observations.length,
      6,
    ),
    fullTopThreeRate: round(
      observations.filter(({ fullTopThree }) => fullTopThree).length /
        observations.length,
      6,
    ),
    averageTopThreeFraction: round(
      mean(observations.map(({ topThreeFraction }) => topThreeFraction)),
      6,
    ),
    fullTopTenRate: round(
      observations.filter(({ fullTopTen }) => fullTopTen).length /
        observations.length,
      6,
    ),
    averageTopTenFraction: round(
      mean(observations.map(({ topTenFraction }) => topTenFraction)),
      6,
    ),
    allWinnerRegretMinutes: distribution(regrets),
    winnerMissRegretMinutes: distribution(missRegrets),
    allTotalRegretPerOriginMinutes: distribution(totalPerOrigin),
    winnerMissTotalRegretPerOriginMinutes: distribution(missTotalPerOrigin),
    actualShortlistSize: {
      minimum: Math.min(...actualSizes),
      median: percentile(actualSizes, 0.5),
      maximum: Math.max(...actualSizes),
    },
    sourceContributionCounts: sumSourceCounts(
      snapshots.map(({ shortlist }) => shortlist.sourceContributionCounts),
    ),
    winnerRecoveriesBySource: Object.fromEntries(
      POLICY_CANDIDATE_SOURCES.map((source) => [
        source,
        observations.filter(
          ({ winnerIncluded, winnerSelectionSource }) =>
            winnerIncluded && winnerSelectionSource === source,
        ).length,
      ]),
    ),
    unusedQuotaBySource: sumSourceCounts(
      snapshots.map(({ shortlist }) => shortlist.unusedQuotaBySource),
    ),
    backfillSourceCounts: sumSourceCounts(
      snapshots.map(({ shortlist }) => shortlist.backfillSourceCounts),
    ),
    unusedQuota: distribution(
      snapshots.map(({ shortlist }) => shortlist.unusedQuota),
    ),
    backfillCount: distribution(
      snapshots.map(({ shortlist }) => shortlist.backfillCount),
    ),
    duplicateSlotsAvoided: distribution(
      snapshots.map(({ shortlist }) => shortlist.duplicateSlotsAvoided),
    ),
    failures: misses.map(({ scenarioId, referenceWinner, shortlistWinner, regretMinutes, totalRegretPerOriginMinutes, failure }) => ({
      scenarioId,
      referenceWinner,
      shortlistWinner,
      regretMinutes,
      totalRegretPerOriginMinutes,
      ...failure,
    })),
  };
}

function efficiencySummary(scenarios: readonly BenchmarkScenario[]) {
  const groupSizes = [...new Set(scenarios.map(({ origins }) => origins.length))]
    .sort((left, right) => left - right);
  let previousTotal: number | null = null;
  return EXACT_BUDGETS.map((budget) => {
    const totalCells = scenarios.reduce(
      (sum, { origins }) => sum + origins.length * budget,
      0,
    );
    const value = {
      budget,
      byGroupSize: Object.fromEntries(
        groupSizes.map((originCount) => [
          originCount,
          {
            scenarioCount: scenarios.filter(
              ({ origins }) => origins.length === originCount,
            ).length,
            cellsPerScenario: originCount * budget,
            totalCells:
              scenarios.filter(({ origins }) => origins.length === originCount)
                .length *
              originCount *
              budget,
          },
        ]),
      ),
      totalCells,
      relativeIncreaseFromPrevious:
        previousTotal === null
          ? null
          : round((totalCells - previousTotal) / previousTotal, 6),
    };
    previousTotal = totalCells;
    return value;
  });
}

function rank(
  courses: readonly BenchmarkCourse[],
  scenario: BenchmarkScenario,
  matrix: TravelTimeMatrix,
) {
  return rankDestinationsForAllModes({
    origins: scenario.origins.map(({ id, label }) => ({ id, label })),
    candidateVenues: courses.map(({ id, name }) => ({ id, name })),
    travelTimes: matrix,
  });
}

function summarizeCourse(
  value: RankDestinationsResult["rankedVenues"][number] | undefined,
  mode: RankingMode,
): CourseSummary | null {
  return value === undefined
    ? null
    : {
        id: value.venue.id,
        name: value.venue.name,
        objectiveMinutes: round(objectiveMinutes(value, mode), 6),
      };
}

function objectiveMinutes(
  value: RankDestinationsResult["rankedVenues"][number],
  mode: RankingMode,
): number {
  return mode === RANKING_MODES.PROTECT_FARTHEST_TRAVELER
    ? value.metrics.maximumTravelTimeMinutes
    : value.metrics.totalTravelTimeMinutes;
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

function sumSourceCounts(
  counts: readonly Readonly<Record<PolicyCandidateSource, number>>[],
): Readonly<Record<PolicyCandidateSource, number>> {
  return Object.fromEntries(
    POLICY_CANDIDATE_SOURCES.map((source) => [
      source,
      counts.reduce((sum, value) => sum + value[source], 0),
    ]),
  ) as Record<PolicyCandidateSource, number>;
}

function distribution(values: readonly number[]): Distribution {
  return {
    count: values.length,
    median: percentile(values, 0.5),
    p90: percentile(values, 0.9),
    maximum: values.length === 0 ? null : round(Math.max(...values), 6),
  };
}

function percentile(values: readonly number[], fractionValue: number): number | null {
  if (values.length === 0) {
    return null;
  }
  const sorted = [...values].sort((left, right) => left - right);
  return round(
    sorted[Math.max(0, Math.ceil(fractionValue * sorted.length) - 1)]!,
    6,
  );
}

function mean(values: readonly number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function fraction(numerator: number, denominator: number): number {
  return denominator === 0 ? 0 : round(numerator / denominator, 6);
}

function round(value: number, digits: number): number {
  const scale = 10 ** digits;
  return Math.round((value + Number.EPSILON) * scale) / scale;
}

function compareIds(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function assertExpectedHash(
  label: string,
  actual: string,
  expected: string,
): void {
  if (actual !== expected) {
    throw new Error(`Expected ${label} SHA-256 ${expected}; received ${actual}.`);
  }
}

function sha256(value: string | Uint8Array): string {
  return createHash("sha256").update(value).digest("hex");
}

async function writeJsonAtomically(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const temporaryPath = `${path}.${process.pid}.tmp`;
  await writeFile(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(temporaryPath, path);
}

const mainPath = process.argv[1] === undefined ? undefined : resolve(process.argv[1]);
if (mainPath !== undefined && import.meta.url === pathToFileURL(mainPath).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
