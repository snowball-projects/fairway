import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCandidateSourceOrders,
  POLICY_CANDIDATE_SOURCES,
  type BenchmarkCourse,
  type CandidateSourceOrders,
  type PolicyCandidateSource,
} from "../scripts/national-shortlisting-benchmark.ts";
import {
  buildExactBudgetShortlists,
  EXACT_BUDGETS,
  quotaForBudget,
  SHORTLIST_POLICIES,
} from "../scripts/national-shortlisting-policy-comparison.ts";

test("the five policies have fixed, exact quotas at every declared budget", () => {
  const expectedHundredQuotas = {
    A: [25, 25, 25, 25, 0, 0],
    B: [10, 10, 40, 40, 0, 0],
    C: [10, 10, 20, 20, 40, 0],
    D: [10, 10, 20, 20, 0, 40],
    E: [5, 5, 20, 20, 25, 25],
  } as const;

  assert.deepEqual(
    SHORTLIST_POLICIES.map(({ id }) => id),
    ["A", "B", "C", "D", "E"],
  );
  for (const policy of SHORTLIST_POLICIES) {
    for (const budget of EXACT_BUDGETS) {
      assert.equal(
        Object.values(quotaForBudget(policy, budget)).reduce(
          (sum, value) => sum + value,
          0,
        ),
        budget,
      );
    }
    assert.deepEqual(
      POLICY_CANDIDATE_SOURCES.map(
        (source) => quotaForBudget(policy, 100)[source],
      ),
      expectedHundredQuotas[policy.id],
    );
  }
});

test("exact budgets deduplicate, backfill, and remain nested", () => {
  const ids = Array.from(
    { length: 140 },
    (_, index) => `course-${index.toString().padStart(3, "0")}`,
  );
  const candidateSources = syntheticSourceOrders(
    Object.fromEntries(
      POLICY_CANDIDATE_SOURCES.map((source, sourceIndex) => [
        source,
        [...ids.slice(sourceIndex * 2), ...ids.slice(0, sourceIndex * 2)],
      ]),
    ) as Record<PolicyCandidateSource, readonly string[]>,
  );

  for (const policy of SHORTLIST_POLICIES) {
    const shortlists = buildExactBudgetShortlists(candidateSources, policy);
    assert.deepEqual(
      shortlists.map(({ actualSize }) => actualSize),
      EXACT_BUDGETS,
    );
    for (const shortlist of shortlists) {
      assert.equal(new Set(shortlist.candidateIds).size, shortlist.budget);
      assert.equal(shortlist.shortfallReason, null);
      assert.equal(shortlist.unusedQuota, shortlist.duplicateSlotsAvoided);
      assert.equal(shortlist.backfillCount, shortlist.unusedQuota);
      assert.equal(
        Object.values(shortlist.sourceContributionCounts).reduce(
          (sum, value) => sum + value,
          0,
        ),
        shortlist.budget,
      );
    }
    for (let index = 1; index < shortlists.length; index += 1) {
      const previous = shortlists[index - 1]!;
      const current = new Set(shortlists[index]!.candidateIds);
      assert.ok(previous.candidateIds.every((id) => current.has(id)));
    }
  }
});

test("a legitimate supply shortfall is explicit and never exceeds the budget", () => {
  const candidateSources = syntheticSourceOrders(
    Object.fromEntries(
      POLICY_CANDIDATE_SOURCES.map((source) => [source, ["one", "two", "three"]]),
    ) as Record<PolicyCandidateSource, readonly string[]>,
  );
  const [shortlist] = buildExactBudgetShortlists(
    candidateSources,
    SHORTLIST_POLICIES[4],
    [20],
  );

  assert.equal(shortlist?.actualSize, 3);
  assert.equal(shortlist?.eligibleCandidateCount, 3);
  assert.match(shortlist?.shortfallReason ?? "", /Only 3 eligible/u);
});

test("source construction is independent of origin and catalog input ordering", () => {
  const origins = [
    { id: "west", coordinates: { latitude: 40, longitude: -100 } },
    { id: "east", coordinates: { latitude: 40, longitude: -90 } },
    { id: "south", coordinates: { latitude: 35, longitude: -95 } },
  ];
  const courses = Array.from({ length: 120 }, (_, index) =>
    course(
      `course-${index.toString().padStart(3, "0")}`,
      35 + (index % 12) * 0.5,
      -100 + Math.floor(index / 12),
    ),
  );

  assert.deepEqual(
    buildCandidateSourceOrders(origins, courses),
    buildCandidateSourceOrders([...origins].reverse(), [...courses].reverse()),
  );
});

test("stable candidate IDs break exact geographic source ties", () => {
  const sources = buildCandidateSourceOrders(
    [
      { id: "west", coordinates: { latitude: 0, longitude: -1 } },
      { id: "east", coordinates: { latitude: 0, longitude: 1 } },
    ],
    [course("zulu", 0, 0), course("alpha", 0, 0)],
  );

  for (const source of POLICY_CANDIDATE_SOURCES) {
    assert.deepEqual(sources.sources[source], ["alpha", "zulu"]);
  }
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

function course(
  id: string,
  latitude: number,
  longitude: number,
): BenchmarkCourse {
  return {
    id,
    name: id,
    sourceName: id,
    coordinates: { latitude, longitude },
    coordinateSource: "node",
    approximateCoordinate: false,
  };
}
