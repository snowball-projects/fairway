import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  POLICY_CANDIDATE_SOURCES,
  type CandidateSourceOrders,
  type PolicyCandidateSource,
} from "../scripts/national-shortlisting-benchmark.ts";
import {
  buildExactBudgetShortlists,
  quotaForBudget,
  SHORTLIST_POLICIES,
} from "../scripts/national-shortlisting-policy-comparison.ts";
import {
  ALL_POLICY_E_BUDGETS,
  AUDIT_BUDGETS,
  auditScenarioCoverage,
  eligibleBudgetsForScenario,
  matrixCellVolume,
  sortMissingEvidenceManifest,
} from "../scripts/national-shortlisting-budget-sensitivity.ts";

test("Policy E keeps its fixed allocation at every tested budget through 500", () => {
  const policy = SHORTLIST_POLICIES.find(({ id }) => id === "E")!;
  for (const budget of ALL_POLICY_E_BUDGETS) {
    const quota = quotaForBudget(policy, budget);
    assert.deepEqual(
      POLICY_CANDIDATE_SOURCES.map((source) => quota[source]),
      [budget / 20, budget / 20, budget / 5, budget / 5, budget / 4, budget / 4],
    );
    assert.equal(
      Object.values(quota).reduce((sum, value) => sum + value, 0),
      budget,
    );
  }
});

test("larger Policy E budgets are exact, deduplicated, backfilled, and nested prefixes", () => {
  const ids = Array.from(
    { length: 620 },
    (_, index) => `course-${index.toString().padStart(3, "0")}`,
  );
  const sources = syntheticSourceOrders(
    Object.fromEntries(
      POLICY_CANDIDATE_SOURCES.map((source, sourceIndex) => [
        source,
        [...ids.slice(sourceIndex * 7), ...ids.slice(0, sourceIndex * 7)],
      ]),
    ) as Record<PolicyCandidateSource, readonly string[]>,
  );
  const policy = SHORTLIST_POLICIES.find(({ id }) => id === "E")!;
  const shortlists = buildExactBudgetShortlists(
    sources,
    policy,
    ALL_POLICY_E_BUDGETS,
  );
  const maximum = shortlists.at(-1)!;

  assert.deepEqual(
    shortlists.map(({ actualSize }) => actualSize),
    ALL_POLICY_E_BUDGETS,
  );
  for (const shortlist of shortlists) {
    assert.equal(new Set(shortlist.candidateIds).size, shortlist.budget);
    assert.equal(shortlist.shortfallReason, null);
    assert.equal(shortlist.backfillCount, shortlist.duplicateSlotsAvoided);
    assert.deepEqual(
      shortlist.candidateIds,
      maximum.candidateIds.slice(0, shortlist.budget),
    );
  }
});

test("coverage audit detects missing columns and their first affected budgets", () => {
  const maximumCandidateSequence = Array.from(
    { length: 400 },
    (_, index) => `course-${index.toString().padStart(3, "0")}`,
  );
  const matrixCandidateIds = new Set(maximumCandidateSequence);
  matrixCandidateIds.delete("course-145");
  matrixCandidateIds.delete("course-399");

  const audit = auditScenarioCoverage({
    scenarioId: "ordinary",
    expandedReference: false,
    referenceCandidateCount: 500,
    maximumCandidateSequence,
    matrixCandidateIds,
    budgets: [120, 160, 200, 300, 400],
  });

  assert.deepEqual(
    audit.coverage.map(({ budget, missingCandidates, complete }) => ({
      budget,
      missingCandidates,
      complete,
    })),
    [
      { budget: 120, missingCandidates: 0, complete: true },
      { budget: 160, missingCandidates: 1, complete: false },
      { budget: 200, missingCandidates: 1, complete: false },
      { budget: 300, missingCandidates: 1, complete: false },
      { budget: 400, missingCandidates: 2, complete: false },
    ],
  );
  assert.deepEqual(audit.missingEvidence, [
    {
      scenarioId: "ordinary",
      firstRequiredBudget: 160,
      candidateId: "course-145",
      referenceCandidateCount: 500,
      referenceKind: "500-candidate",
      affectedBudgets: [160, 200, 300, 400],
    },
    {
      scenarioId: "ordinary",
      firstRequiredBudget: 400,
      candidateId: "course-399",
      referenceCandidateCount: 500,
      referenceKind: "500-candidate",
      affectedBudgets: [400],
    },
  ]);
});

test("missing-evidence manifest ordering is deterministic", () => {
  const shared = {
    referenceCandidateCount: 500,
    referenceKind: "500-candidate" as const,
    affectedBudgets: [400],
  };
  const input = [
    { scenarioId: "zeta", firstRequiredBudget: 400, candidateId: "b", ...shared },
    { scenarioId: "alpha", firstRequiredBudget: 400, candidateId: "c", ...shared },
    { scenarioId: "alpha", firstRequiredBudget: 300, candidateId: "z", ...shared },
    { scenarioId: "alpha", firstRequiredBudget: 400, candidateId: "a", ...shared },
  ];

  assert.deepEqual(
    sortMissingEvidenceManifest(input).map(
      ({ scenarioId, firstRequiredBudget, candidateId }) =>
        `${scenarioId}/${firstRequiredBudget}/${candidateId}`,
    ),
    ["alpha/300/z", "alpha/400/a", "alpha/400/c", "zeta/400/b"],
  );
  assert.deepEqual(input.map(({ candidateId }) => candidateId), ["b", "c", "z", "a"]);
});

test("500 is eligible only for expanded 1,000-candidate references", () => {
  assert.deepEqual(
    eligibleBudgetsForScenario({ expandedReference: false }, 500),
    [120, 160, 200, 300, 400],
  );
  assert.deepEqual(
    eligibleBudgetsForScenario({ expandedReference: true }, 1_000),
    AUDIT_BUDGETS,
  );
});

test("matrix-cell calculations cover two through six origins", () => {
  for (const budget of AUDIT_BUDGETS) {
    for (let originCount = 2; originCount <= 6; originCount += 1) {
      const volume = matrixCellVolume(originCount, budget);
      assert.equal(volume.cells, originCount * budget);
      assert.equal(volume.fitsOneConservativeRequest, true);
    }
  }
  assert.deepEqual(matrixCellVolume(6, 400), {
    cells: 2_400,
    fitsOneConservativeRequest: true,
  });
  assert.deepEqual(matrixCellVolume(6, 500), {
    cells: 3_000,
    fitsOneConservativeRequest: true,
  });
});

test("the companion runner exposes no routing or public-network fallback", async () => {
  const source = await readFile(
    "scripts/national-shortlisting-budget-sensitivity.ts",
    "utf8",
  );
  assert.doesNotMatch(source, /\bfetch\s*\(/u);
  assert.doesNotMatch(source, /OpenRouteService|--route|apiKey/u);
  assert.match(source, /loadCachedScenarioMatrix/u);
  assert.match(source, /networkFallback:\s*false/u);
});

function syntheticSourceOrders(
  sources: Readonly<Record<PolicyCandidateSource, readonly string[]>>,
): CandidateSourceOrders {
  return {
    anchors: {
      minimumTotal: { latitude: 0, longitude: 0 },
      minimumMaximum: { latitude: 0, longitude: 0 },
    },
    sources,
  };
}
