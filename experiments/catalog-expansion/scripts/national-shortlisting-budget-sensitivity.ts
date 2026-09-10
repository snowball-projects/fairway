import { createHash } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { isDeepStrictEqual } from "node:util";
import { pathToFileURL } from "node:url";

import {
  buildCandidateSourceOrders,
  buildScenarioPlan,
  EXPECTED_NATIONAL_CATALOG_SHA256,
  loadCachedScenarioMatrix,
  MATRIX_CELL_LIMIT,
  normalizeCatalog,
  planMatrixBatches,
  validateScenarioCorpus,
  type BenchmarkCourse,
  type BenchmarkScenario,
} from "./national-shortlisting-benchmark.ts";
import {
  buildExactBudgetShortlists,
  EXPECTED_BENCHMARK_SUMMARY_SHA256,
  EXPECTED_SCENARIO_SHA256,
  SHORTLIST_POLICIES,
  type ExactBudgetShortlist,
} from "./national-shortlisting-policy-comparison.ts";
import {
  rankDestinationsForAllModes,
  RANKING_MODES,
  type RankDestinationsResult,
  type RankingMode,
  type TravelTimeMatrix,
} from "../src/core/ranking.ts";

export const COMMITTED_BASELINE_BUDGETS = [80, 100] as const;
export const SENSITIVITY_BUDGETS = [120, 160, 200, 300] as const;
export const AUDIT_BUDGETS = [...SENSITIVITY_BUDGETS, 400, 500] as const;
export const ALL_POLICY_E_BUDGETS = [
  ...COMMITTED_BASELINE_BUDGETS,
  ...AUDIT_BUDGETS,
] as const;
export const EXPECTED_POLICY_COMPARISON_SUMMARY_SHA256 =
  "a80742a2dfeb808dfcecbd01451490478b0d03ee65f552da177caa3feae62bc7";

const CATALOG_PATH = resolve(
  ".local/contiguous-us-osm-rehearsal/contiguous-us-catalog-first.json",
);
const SCENARIO_PATH = resolve("benchmark/national-shortlisting-scenarios.json");
const BENCHMARK_ARTIFACT_ROOT = resolve(
  ".local/national-shortlisting-benchmark",
);
const COMPARISON_SUMMARY_PATH = resolve(
  ".local/national-shortlisting-policy-comparison/comparison-summary.json",
);
const ARTIFACT_ROOT = resolve(
  ".local/national-shortlisting-budget-sensitivity",
);
const AUDIT_PATH = resolve(ARTIFACT_ROOT, "evidence-audit.json");
const SENSITIVITY_PATH = resolve(ARTIFACT_ROOT, "sensitivity-summary.json");

interface CoverageEntry {
  readonly budget: number;
  readonly requiredCandidates: number;
  readonly coveredCandidates: number;
  readonly missingCandidates: number;
  readonly complete: boolean;
}

interface MissingEvidenceEntry {
  readonly scenarioId: string;
  readonly firstRequiredBudget: number;
  readonly candidateId: string;
  readonly referenceCandidateCount: number;
  readonly referenceKind: "500-candidate" | "1,000-candidate";
  readonly affectedBudgets: readonly number[];
}

interface ScenarioContext {
  readonly scenario: BenchmarkScenario;
  readonly referenceCandidateIds: readonly string[];
  readonly matrix: TravelTimeMatrix;
  readonly shortlists: readonly ExactBudgetShortlist[];
  readonly coverage: readonly CoverageEntry[];
  readonly missingEvidence: readonly MissingEvidenceEntry[];
}

interface RankingObservation {
  readonly scenarioId: string;
  readonly scenarioLabel: string;
  readonly originCount: number;
  readonly budget: number;
  readonly mode: RankingMode;
  readonly winnerIncluded: boolean;
  readonly regretMinutes: number | null;
  readonly totalRegretPerGolferMinutes: number | null;
  readonly topThreeIncluded: number;
  readonly topThreeFraction: number;
  readonly fullTopThree: boolean;
  readonly topTenIncluded: number;
  readonly topTenFraction: number;
  readonly fullTopTen: boolean;
  readonly referenceWinner: CourseResult | null;
  readonly shortlistWinner: CourseResult | null;
}

interface CourseResult {
  readonly id: string;
  readonly name: string;
  readonly objectiveMinutes: number;
}

interface CommittedComparisonSummary {
  readonly shortlistDetails: readonly {
    readonly scenarioId: string;
    readonly policyId: string;
    readonly shortlist: ExactBudgetShortlist;
  }[];
}

interface Distribution {
  readonly count: number;
  readonly median: number | null;
  readonly p90: number | null;
  readonly maximum: number | null;
}

export function eligibleBudgetsForScenario(
  scenario: Pick<BenchmarkScenario, "expandedReference">,
  referenceCandidateCount: number,
): readonly number[] {
  return AUDIT_BUDGETS.filter(
    (budget) =>
      budget <= referenceCandidateCount &&
      (budget !== 500 || scenario.expandedReference),
  );
}

export function matrixCellVolume(originCount: number, budget: number): {
  readonly cells: number;
  readonly fitsOneConservativeRequest: boolean;
} {
  if (!Number.isInteger(originCount) || originCount < 2 || originCount > 6) {
    throw new Error("Origin count must be an integer from two through six.");
  }
  if (!Number.isInteger(budget) || budget < 1) {
    throw new Error("Budget must be a positive integer.");
  }
  const cells = originCount * budget;
  return {
    cells,
    fitsOneConservativeRequest: cells <= MATRIX_CELL_LIMIT,
  };
}

export function auditScenarioCoverage(input: {
  readonly scenarioId: string;
  readonly expandedReference: boolean;
  readonly referenceCandidateCount: number;
  readonly maximumCandidateSequence: readonly string[];
  readonly matrixCandidateIds: ReadonlySet<string>;
  readonly budgets: readonly number[];
}): {
  readonly coverage: readonly CoverageEntry[];
  readonly missingEvidence: readonly MissingEvidenceEntry[];
} {
  const budgets = [...new Set(input.budgets)].sort((left, right) => left - right);
  const maximumBudget = budgets.at(-1);
  if (
    maximumBudget === undefined ||
    input.maximumCandidateSequence.length < maximumBudget
  ) {
    throw new Error(`Scenario "${input.scenarioId}" lacks an exact maximum sequence.`);
  }

  const coverage = budgets.map((budget) => {
    const required = input.maximumCandidateSequence.slice(0, budget);
    const coveredCandidates = required.filter((id) =>
      input.matrixCandidateIds.has(id),
    ).length;
    return {
      budget,
      requiredCandidates: required.length,
      coveredCandidates,
      missingCandidates: required.length - coveredCandidates,
      complete: coveredCandidates === required.length,
    };
  });
  const missingEvidence = input.maximumCandidateSequence
    .slice(0, maximumBudget)
    .flatMap((candidateId, index) => {
      if (input.matrixCandidateIds.has(candidateId)) {
        return [];
      }
      const firstRequiredBudget = budgets.find((budget) => index < budget)!;
      return [
        {
          scenarioId: input.scenarioId,
          firstRequiredBudget,
          candidateId,
          referenceCandidateCount: input.referenceCandidateCount,
          referenceKind: input.expandedReference
            ? ("1,000-candidate" as const)
            : ("500-candidate" as const),
          affectedBudgets: budgets.filter(
            (budget) => budget >= firstRequiredBudget,
          ),
        },
      ];
    });

  return { coverage, missingEvidence };
}

export function sortMissingEvidenceManifest(
  entries: readonly MissingEvidenceEntry[],
): readonly MissingEvidenceEntry[] {
  return [...entries].sort(
    (left, right) =>
      compareIds(left.scenarioId, right.scenarioId) ||
      left.firstRequiredBudget - right.firstRequiredBudget ||
      compareIds(left.candidateId, right.candidateId),
  );
}

async function main(): Promise<void> {
  const [
    catalogBytes,
    scenarioBytes,
    benchmarkSummaryBytes,
    comparisonSummaryBytes,
  ] = await Promise.all([
    readFile(CATALOG_PATH),
    readFile(SCENARIO_PATH),
    readFile(resolve(BENCHMARK_ARTIFACT_ROOT, "benchmark-summary.json")),
    readFile(COMPARISON_SUMMARY_PATH),
  ]);
  const hashes = {
    catalog: sha256(catalogBytes),
    scenarios: sha256(scenarioBytes),
    benchmarkSummary: sha256(benchmarkSummaryBytes),
    policyComparisonSummary: sha256(comparisonSummaryBytes),
  };
  assertExpectedHash(
    "national catalog",
    hashes.catalog,
    EXPECTED_NATIONAL_CATALOG_SHA256,
  );
  assertExpectedHash(
    "scenario fixture",
    hashes.scenarios,
    EXPECTED_SCENARIO_SHA256,
  );
  assertExpectedHash(
    "cached benchmark summary",
    hashes.benchmarkSummary,
    EXPECTED_BENCHMARK_SUMMARY_SHA256,
  );
  assertExpectedHash(
    "committed policy-comparison summary",
    hashes.policyComparisonSummary,
    EXPECTED_POLICY_COMPARISON_SUMMARY_SHA256,
  );

  const catalog = normalizeCatalog(JSON.parse(catalogBytes.toString("utf8")));
  const scenarios = validateScenarioCorpus(
    JSON.parse(scenarioBytes.toString("utf8")),
  );
  const committedComparison = validateCommittedComparison(
    JSON.parse(comparisonSummaryBytes.toString("utf8")),
  );
  const policy = SHORTLIST_POLICIES.find(({ id }) => id === "E");
  if (policy === undefined) {
    throw new Error("Policy E is unavailable.");
  }

  const courseById = new Map(catalog.courses.map((course) => [course.id, course]));
  const contexts: ScenarioContext[] = [];
  let cacheBatchCount = 0;

  for (const scenario of scenarios) {
    const plan = buildScenarioPlan(scenario, catalog.courses);
    const auditBudgets = eligibleBudgetsForScenario(
      scenario,
      plan.referenceCandidateIds.length,
    );
    const requestedBudgets = [...COMMITTED_BASELINE_BUDGETS, ...auditBudgets];
    const candidateSources = buildCandidateSourceOrders(
      scenario.origins.map(({ id, coordinates }) => ({ id, coordinates })),
      catalog.courses,
    );
    const shortlists = buildExactBudgetShortlists(
      candidateSources,
      policy,
      requestedBudgets,
    );
    const maximum = shortlists.at(-1)!;
    assertExactNestedPrefixes(scenario.id, shortlists, maximum);
    assertCommittedBaselineCandidates(
      scenario.id,
      shortlists,
      committedComparison,
    );

    const matrix = await loadCachedScenarioMatrix(plan, courseById, {
      artifactRoot: BENCHMARK_ARTIFACT_ROOT,
      catalogSha256: hashes.catalog,
    });
    cacheBatchCount += planMatrixBatches(
      scenario.origins.length,
      plan.referenceCandidateIds,
    ).length;
    const audit = auditScenarioCoverage({
      scenarioId: scenario.id,
      expandedReference: scenario.expandedReference,
      referenceCandidateCount: plan.referenceCandidateIds.length,
      maximumCandidateSequence: maximum.candidateIds,
      matrixCandidateIds: new Set(Object.keys(matrix)),
      budgets: auditBudgets,
    });
    contexts.push({
      scenario,
      referenceCandidateIds: plan.referenceCandidateIds,
      matrix,
      shortlists,
      ...audit,
    });
  }

  const manifest = sortMissingEvidenceManifest(
    contexts.flatMap(({ missingEvidence }) => missingEvidence),
  ).map((entry) => ({
    ...entry,
    candidateName: requiredCourse(courseById, entry.candidateId).name,
  }));
  const corpusCoverage = summarizeCorpusCoverage(contexts);
  const auditSummary = {
    schemaVersion: 1,
    inputs: {
      catalogPath:
        ".local/contiguous-us-osm-rehearsal/contiguous-us-catalog-first.json",
      catalogSha256: hashes.catalog,
      catalogSnapshot: catalog.snapshot,
      catalogCourseCount: catalog.courses.length,
      scenarioPath: "benchmark/national-shortlisting-scenarios.json",
      scenarioSha256: hashes.scenarios,
      scenarioCount: scenarios.length,
      cachedBenchmarkSummaryPath:
        ".local/national-shortlisting-benchmark/benchmark-summary.json",
      cachedBenchmarkSummarySha256: hashes.benchmarkSummary,
      committedPolicyComparisonSummaryPath:
        ".local/national-shortlisting-policy-comparison/comparison-summary.json",
      committedPolicyComparisonSummarySha256: hashes.policyComparisonSummary,
      cachedMatrixBatchesLoaded: cacheBatchCount,
      publicNetworkRequests: 0,
    },
    evaluation: {
      policyId: policy.id,
      policyName: policy.name,
      auditedBudgets: AUDIT_BUDGETS,
      sensitivityBudgets: SENSITIVITY_BUDGETS,
      ordinaryMaximumBudget: 400,
      expandedReferenceMaximumBudget: 500,
      smallerBudgetsDerivedFromMaximumNestedSequence: true,
      exactDeclaredSizes: contexts.every(({ shortlists }) =>
        shortlists.every(({ budget, actualSize }) => budget === actualSize),
      ),
      cacheOnly: true,
      networkFallback: false,
      committedPolicyEBaselinesMatch: true,
    },
    coverageByBudget: corpusCoverage,
    coverageByScenario: contexts.map(({ scenario, referenceCandidateIds, coverage }) => ({
      scenarioId: scenario.id,
      scenarioLabel: scenario.label,
      originCount: scenario.origins.length,
      referenceCandidateCount: referenceCandidateIds.length,
      referenceKind: scenario.expandedReference
        ? "1,000-candidate"
        : "500-candidate",
      coverage,
    })),
    additionalEvidenceByBudget: corpusCoverage.map((coverage) => ({
      budget: coverage.budget,
      eligibleScenarios: coverage.eligibleScenarios,
      scenariosRequiringEvidence: coverage.incompleteScenarios,
      additionalCandidateColumns: coverage.missingCandidates,
      additionalOriginDestinationCells: contexts.reduce((sum, context) => {
        const scenarioCoverage = context.coverage.find(
          ({ budget }) => budget === coverage.budget,
        );
        return (
          sum +
          (scenarioCoverage?.missingCandidates ?? 0) *
            context.scenario.origins.length
        );
      }, 0),
    })),
    missingEvidence: {
      entries: manifest.length,
      affectedScenarios: new Set(manifest.map(({ scenarioId }) => scenarioId))
        .size,
      manifest,
    },
    sensitivityEligibility: {
      budgets: SENSITIVITY_BUDGETS,
      completeForEveryScenario: SENSITIVITY_BUDGETS.every(
        (budget) => corpusCoverage.find((value) => value.budget === budget)!.complete,
      ),
    },
    referenceInterpretation: referenceInterpretation(),
  };
  await writeJsonAtomically(AUDIT_PATH, auditSummary);

  if (!auditSummary.sensitivityEligibility.completeForEveryScenario) {
    console.log(
      "Evidence audit complete; the all-scenario sensitivity comparison stopped because cached evidence is incomplete at or below K=300.",
    );
    console.log("public network requests: 0");
    console.log(`audit: ${AUDIT_PATH}`);
    return;
  }

  const observations: RankingObservation[] = [];
  const sensitivityShortlists: {
    readonly scenarioId: string;
    readonly shortlist: ExactBudgetShortlist;
  }[] = [];
  for (const context of contexts) {
    const referenceCourses = context.referenceCandidateIds.map((id) =>
      requiredCourse(courseById, id),
    );
    const referenceRankings = rank(
      referenceCourses,
      context.scenario,
      context.matrix,
    );
    for (const budget of SENSITIVITY_BUDGETS) {
      const shortlist = context.shortlists.find((value) => value.budget === budget)!;
      sensitivityShortlists.push({ scenarioId: context.scenario.id, shortlist });
      const shortlistRankings = rank(
        shortlist.candidateIds.map((id) => requiredCourse(courseById, id)),
        context.scenario,
        context.matrix,
      );
      for (const mode of Object.values(RANKING_MODES)) {
        observations.push(
          compareRankings(
            context.scenario,
            shortlist,
            shortlistRankings[mode],
            referenceRankings[mode],
            mode,
          ),
        );
      }
    }
  }

  const aggregates = Object.fromEntries(
    Object.values(RANKING_MODES).map((mode) => [
      mode,
      SENSITIVITY_BUDGETS.map((budget) =>
        aggregateObservations(
          observations.filter(
            (value) => value.mode === mode && value.budget === budget,
          ),
          sensitivityShortlists.filter(
            ({ shortlist }) => shortlist.budget === budget,
          ),
          budget,
          mode,
        ),
      ),
    ]),
  );
  const acceptance = acceptanceSummary(aggregates);
  const sensitivitySummary = {
    schemaVersion: 1,
    inputs: {
      ...auditSummary.inputs,
      evidenceAuditPath:
        ".local/national-shortlisting-budget-sensitivity/evidence-audit.json",
      evidenceAuditSha256: sha256(await readFile(AUDIT_PATH)),
    },
    evaluation: {
      policyId: policy.id,
      budgets: SENSITIVITY_BUDGETS,
      rankingModes: Object.values(RANKING_MODES),
      scenarioCount: scenarios.length,
      cacheOnly: true,
      networkFallback: false,
    },
    operationalVolume: SENSITIVITY_BUDGETS.map((budget) => ({
      budget,
      matrixCellsByOriginCount: Object.fromEntries(
        [2, 3, 4, 5, 6].map((originCount) => [
          originCount,
          matrixCellVolume(originCount, budget),
        ]),
      ),
      corpusMatrixCells: scenarios.reduce(
        (sum, scenario) => sum + scenario.origins.length * budget,
        0,
      ),
    })),
    aggregates,
    acceptance,
    smallestPassingBudget:
      acceptance.find(({ meetsAll }) => meetsAll)?.budget ?? null,
    scenarios: observations,
    referenceInterpretation: referenceInterpretation(),
  };
  await writeJsonAtomically(SENSITIVITY_PATH, sensitivitySummary);
  console.log(
    `Evidence audit and Policy E sensitivity complete: ${scenarios.length} scenarios, budgets ${SENSITIVITY_BUDGETS.join(", ")}.`,
  );
  console.log("public network requests: 0");
  console.log(`audit: ${AUDIT_PATH}`);
  console.log(`sensitivity: ${SENSITIVITY_PATH}`);
}

function assertExactNestedPrefixes(
  scenarioId: string,
  shortlists: readonly ExactBudgetShortlist[],
  maximum: ExactBudgetShortlist,
): void {
  for (const shortlist of shortlists) {
    if (
      shortlist.actualSize !== shortlist.budget ||
      !isDeepStrictEqual(
        shortlist.candidateIds,
        maximum.candidateIds.slice(0, shortlist.budget),
      )
    ) {
      throw new Error(
        `Policy E shortlist is not an exact nested prefix for "${scenarioId}" at K=${shortlist.budget}.`,
      );
    }
  }
}

function assertCommittedBaselineCandidates(
  scenarioId: string,
  shortlists: readonly ExactBudgetShortlist[],
  committed: CommittedComparisonSummary,
): void {
  for (const budget of COMMITTED_BASELINE_BUDGETS) {
    const current = shortlists.find((shortlist) => shortlist.budget === budget);
    const baseline = committed.shortlistDetails.find(
      (value) =>
        value.scenarioId === scenarioId &&
        value.policyId === "E" &&
        value.shortlist.budget === budget,
    );
    if (
      current === undefined ||
      baseline === undefined ||
      !isDeepStrictEqual(current, baseline.shortlist)
    ) {
      throw new Error(
        `Reconstructed Policy E${budget} shortlist differs from the committed baseline for "${scenarioId}".`,
      );
    }
  }
}

function summarizeCorpusCoverage(contexts: readonly ScenarioContext[]) {
  return AUDIT_BUDGETS.map((budget) => {
    const eligible = contexts.flatMap((context) => {
      const coverage = context.coverage.find((value) => value.budget === budget);
      return coverage === undefined ? [] : [coverage];
    });
    return {
      budget,
      eligibleScenarios: eligible.length,
      completeScenarios: eligible.filter(({ complete }) => complete).length,
      incompleteScenarios: eligible.filter(({ complete }) => !complete).length,
      requiredCandidates: eligible.reduce(
        (sum, value) => sum + value.requiredCandidates,
        0,
      ),
      coveredCandidates: eligible.reduce(
        (sum, value) => sum + value.coveredCandidates,
        0,
      ),
      missingCandidates: eligible.reduce(
        (sum, value) => sum + value.missingCandidates,
        0,
      ),
      complete: eligible.length > 0 && eligible.every(({ complete }) => complete),
    };
  });
}

function compareRankings(
  scenario: BenchmarkScenario,
  shortlist: ExactBudgetShortlist,
  result: RankDestinationsResult,
  reference: RankDestinationsResult,
  mode: RankingMode,
): RankingObservation {
  const selectedIds = new Set(shortlist.candidateIds);
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
  return {
    scenarioId: scenario.id,
    scenarioLabel: scenario.label,
    originCount: scenario.origins.length,
    budget: shortlist.budget,
    mode,
    winnerIncluded:
      referenceWinner !== undefined && selectedIds.has(referenceWinner.venue.id),
    regretMinutes,
    totalRegretPerGolferMinutes:
      mode === RANKING_MODES.LOWEST_TOTAL_TRAVEL && regretMinutes !== null
        ? round(regretMinutes / scenario.origins.length, 6)
        : null,
    topThreeIncluded,
    topThreeFraction: fraction(topThreeIncluded, referenceTopThree.length),
    fullTopThree:
      referenceTopThree.length > 0 && topThreeIncluded === referenceTopThree.length,
    topTenIncluded,
    topTenFraction: fraction(topTenIncluded, referenceTopTen.length),
    fullTopTen:
      referenceTopTen.length > 0 && topTenIncluded === referenceTopTen.length,
    referenceWinner: summarizeCourse(referenceWinner, mode),
    shortlistWinner: summarizeCourse(shortlistWinner, mode),
  };
}

function aggregateObservations(
  observations: readonly RankingObservation[],
  snapshots: readonly {
    readonly scenarioId: string;
    readonly shortlist: ExactBudgetShortlist;
  }[],
  budget: number,
  mode: RankingMode,
) {
  if (observations.length === 0 || observations.length !== snapshots.length) {
    throw new Error(`Incomplete aggregate inputs for E/${budget}/${mode}.`);
  }
  const misses = observations.filter(({ winnerIncluded }) => !winnerIncluded);
  const regrets = observations.flatMap(({ regretMinutes }) =>
    regretMinutes === null ? [] : [regretMinutes],
  );
  const missRegrets = misses.flatMap(({ regretMinutes }) =>
    regretMinutes === null ? [] : [regretMinutes],
  );
  const perGolferRegrets = observations.flatMap(
    ({ totalRegretPerGolferMinutes }) =>
      totalRegretPerGolferMinutes === null ? [] : [totalRegretPerGolferMinutes],
  );
  const actualSizes = snapshots.map(({ shortlist }) => shortlist.actualSize);
  const exact = snapshots.every(
    ({ shortlist }) => shortlist.actualSize === shortlist.budget,
  );
  const regret = distribution(regrets);
  const totalPerGolfer = distribution(perGolferRegrets);
  return {
    policyId: "E",
    budget,
    mode,
    scenarioCount: observations.length,
    exactShortlistSize: {
      minimum: Math.min(...actualSizes),
      median: percentile(actualSizes, 0.5),
      maximum: Math.max(...actualSizes),
      allExact: exact,
    },
    referenceWinnerInclusion: {
      included: observations.length - misses.length,
      missed: misses.length,
      rate: round((observations.length - misses.length) / observations.length, 6),
    },
    winnerRegretMinutes: regret,
    winnerMissRegretMinutes: distribution(missRegrets),
    worstMaximumDriveRegretMinutes:
      mode === RANKING_MODES.PROTECT_FARTHEST_TRAVELER
        ? regret.maximum
        : null,
    totalDriveRegretMinutes:
      mode === RANKING_MODES.LOWEST_TOTAL_TRAVEL ? regret : null,
    totalDriveRegretPerGolferMinutes:
      mode === RANKING_MODES.LOWEST_TOTAL_TRAVEL ? totalPerGolfer : null,
    materialRegretMisses: misses.filter((value) =>
      mode === RANKING_MODES.PROTECT_FARTHEST_TRAVELER
        ? (value.regretMinutes ?? 0) > 10
        : (value.totalRegretPerGolferMinutes ?? 0) > 5,
    ).length,
    topResultCoverage: {
      fullTopThreeRate: fraction(
        observations.filter(({ fullTopThree }) => fullTopThree).length,
        observations.length,
      ),
      averageTopThreeFraction: round(
        mean(observations.map(({ topThreeFraction }) => topThreeFraction)),
        6,
      ),
      fullTopTenRate: fraction(
        observations.filter(({ fullTopTen }) => fullTopTen).length,
        observations.length,
      ),
      averageTopTenFraction: round(
        mean(observations.map(({ topTenFraction }) => topTenFraction)),
        6,
      ),
    },
  };
}

function acceptanceSummary(
  aggregates: Readonly<
    Record<string, readonly ReturnType<typeof aggregateObservations>[]>
  >,
) {
  return SENSITIVITY_BUDGETS.map((budget) => {
    const maximum = aggregates[RANKING_MODES.PROTECT_FARTHEST_TRAVELER]!.find(
      (value) => value.budget === budget,
    )!;
    const total = aggregates[RANKING_MODES.LOWEST_TOTAL_TRAVEL]!.find(
      (value) => value.budget === budget,
    )!;
    const gates = {
      maximumWinnerInclusion:
        maximum.referenceWinnerInclusion.rate >= 0.95,
      totalWinnerInclusion: total.referenceWinnerInclusion.rate >= 0.95,
      maximumDriveRegret:
        (maximum.worstMaximumDriveRegretMinutes ?? 0) <= 10,
      totalDriveRegretPerGolfer:
        (total.totalDriveRegretPerGolferMinutes?.maximum ?? 0) <= 5,
      exactDeclaredShortlistSize:
        maximum.exactShortlistSize.allExact && total.exactShortlistSize.allExact,
    };
    return {
      budget,
      gates,
      meetsAll: Object.values(gates).every(Boolean),
    };
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
): CourseResult | null {
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

function validateCommittedComparison(value: unknown): CommittedComparisonSummary {
  if (!isRecord(value) || !Array.isArray(value.shortlistDetails)) {
    throw new Error("Committed policy-comparison summary has an unsupported shape.");
  }
  return value as unknown as CommittedComparisonSummary;
}

function referenceInterpretation() {
  return {
    routedReferenceUniverse:
      "Each result is relative to a fixed candidate set with cached journey evidence, not proof of the globally optimal national course.",
    ordinaryReference:
      "A 500-candidate routed reference supports Policy E comparisons only below K=500 and is not independent evidence for a K=500 shortlist.",
    expandedReference:
      "K=500 is evaluated only for the four scenarios with 1,000-candidate routed references.",
    productionCeiling:
      "Routed-reference stabilization is not a production evaluation ceiling.",
  };
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
