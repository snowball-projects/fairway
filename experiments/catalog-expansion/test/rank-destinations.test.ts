import assert from "node:assert/strict";
import test from "node:test";

import {
  RANKING_MODES,
  RankingInputError,
  rankDestinations,
  rankDestinationsForAllModes,
  type RankDestinationsInput,
  type RankingMode,
  type TravelTimeMatrix,
} from "../src/core/ranking.ts";
import {
  exampleCandidateVenues,
  exampleTravelTimes,
  fourTravelerOrigins,
} from "../examples/four-traveler-fixture.ts";

function exampleInput(
  rankingMode: RankingMode,
  maximumTravelTimeMinutes?: number,
): RankDestinationsInput {
  return {
    origins: fourTravelerOrigins,
    candidateVenues: exampleCandidateVenues,
    travelTimes: exampleTravelTimes,
    maximumTravelTimeMinutes,
    rankingMode,
  };
}

const rankingModeCases = [
  {
    name: "Lowest longest drive",
    mode: RANKING_MODES.PROTECT_FARTHEST_TRAVELER,
    expectedVenueIds: [
      "civic-library",
      "central-park",
      "market-hall",
      "riverside-cafe",
      "distant-museum",
    ],
  },
  {
    name: "Lowest total drive",
    mode: RANKING_MODES.LOWEST_TOTAL_TRAVEL,
    expectedVenueIds: [
      "market-hall",
      "civic-library",
      "riverside-cafe",
      "central-park",
      "distant-museum",
    ],
  },
] as const;

for (const rankingModeCase of rankingModeCases) {
  test(`${rankingModeCase.name} applies its primary criterion`, () => {
    const result = rankDestinations(exampleInput(rankingModeCase.mode));

    assert.deepEqual(
      result.rankedVenues.map(({ venue }) => venue.id),
      rankingModeCase.expectedVenueIds,
    );
  });
}

test("all-mode ranking matches every canonical single-mode result", () => {
  const { rankingMode: _rankingMode, ...input } = exampleInput(
    RANKING_MODES.PROTECT_FARTHEST_TRAVELER,
  );
  const results = rankDestinationsForAllModes(input);

  for (const { mode } of rankingModeCases) {
    assert.deepEqual(
      results[mode],
      rankDestinations({ ...input, rankingMode: mode }),
    );
  }
});

const criterionTieCases = [
  {
    name: "Lowest longest drive",
    mode: RANKING_MODES.PROTECT_FARTHEST_TRAVELER,
    travelTimes: {
      "low-spread": { one: 11, two: 14, three: 20 },
      "high-spread": { one: 10, two: 15, three: 20 },
      "high-mean": { one: 15, two: 16, three: 20 },
    },
    expectedVenueIds: ["low-spread", "high-spread", "high-mean"],
  },
  {
    name: "Lowest total drive",
    mode: RANKING_MODES.LOWEST_TOTAL_TRAVEL,
    travelTimes: {
      "low-spread": { one: 11, two: 14, three: 20 },
      "high-spread": { one: 10, two: 15, three: 20 },
      "high-maximum": { one: 12, two: 12, three: 21 },
    },
    expectedVenueIds: ["low-spread", "high-spread", "high-maximum"],
  },
] as const;

for (const criterionTieCase of criterionTieCases) {
  test(`${criterionTieCase.name} applies its secondary and tertiary criteria in order`, () => {
    const venueIds = Object.keys(criterionTieCase.travelTimes);
    const result = rankDestinations({
      origins: [
        { id: "one", label: "One" },
        { id: "two", label: "Two" },
        { id: "three", label: "Three" },
      ],
      candidateVenues: venueIds.map((id) => ({ id, name: id })),
      travelTimes: criterionTieCase.travelTimes,
      rankingMode: criterionTieCase.mode,
    });

    assert.deepEqual(
      result.rankedVenues.map(({ venue }) => venue.id),
      criterionTieCase.expectedVenueIds,
    );
  });
}

test("calculates and exposes all travel-time metrics", () => {
  const result = rankDestinations(
    exampleInput(RANKING_MODES.PROTECT_FARTHEST_TRAVELER),
  );
  const civicLibrary = result.rankedVenues.find(
    ({ venue }) => venue.id === "civic-library",
  );

  assert.deepEqual(civicLibrary?.metrics, {
    maximumTravelTimeMinutes: 24,
    minimumTravelTimeMinutes: 10,
    meanTravelTimeMinutes: 17.25,
    totalTravelTimeMinutes: 69,
    travelTimeSpreadMinutes: 14,
  });
});

test("excludes a venue when any travel time exceeds the maximum", () => {
  const result = rankDestinations(
    exampleInput(RANKING_MODES.PROTECT_FARTHEST_TRAVELER, 35),
  );

  assert.equal(result.rankedVenues.length, 4);
  assert.equal(result.excludedVenues.length, 1);
  assert.equal(result.excludedVenues[0]?.venue.id, "distant-museum");
  assert.deepEqual(result.excludedVenues[0]?.reasons, [
    {
      code: "maximum-travel-time-exceeded",
      originId: "devon",
      travelTimeMinutes: 42,
      maximumTravelTimeMinutes: 35,
    },
  ]);
});

test("a travel time equal to the maximum remains eligible", () => {
  const result = rankDestinations(
    exampleInput(RANKING_MODES.PROTECT_FARTHEST_TRAVELER, 42),
  );

  assert.equal(result.rankedVenues.length, 5);
  assert.equal(result.excludedVenues.length, 0);
});

test("uses venue ID as a deterministic final tie-breaker", () => {
  const result = rankDestinations({
    origins: [
      { id: "one", label: "One" },
      { id: "two", label: "Two" },
    ],
    candidateVenues: [
      { id: "zulu", name: "Zulu" },
      { id: "alpha", name: "Alpha" },
    ],
    travelTimes: {
      zulu: { one: 10, two: 20 },
      alpha: { one: 10, two: 20 },
    },
    rankingMode: RANKING_MODES.PROTECT_FARTHEST_TRAVELER,
  });

  assert.deepEqual(
    result.rankedVenues.map(({ venue }) => venue.id),
    ["alpha", "zulu"],
  );
});

test("venues with equal metrics remain distinct and expose equal metrics", () => {
  const result = rankDestinations({
    origins: [
      { id: "one", label: "One" },
      { id: "two", label: "Two" },
    ],
    candidateVenues: [
      { id: "first", name: "First" },
      { id: "second", name: "Second" },
    ],
    travelTimes: {
      first: { one: 12, two: 18 },
      second: { one: 12, two: 18 },
    },
    rankingMode: RANKING_MODES.LOWEST_TOTAL_TRAVEL,
  });

  assert.equal(result.rankedVenues.length, 2);
  assert.deepEqual(
    result.rankedVenues[0]?.metrics,
    result.rankedVenues[1]?.metrics,
  );
  assert.deepEqual(
    result.rankedVenues.map(({ rank }) => rank),
    [1, 2],
  );
});

test("excludes venues with missing or invalid travel times and explains each reason", () => {
  const travelTimes = {
    valid: { one: 10, two: 12 },
    missing: { one: 10 },
    unavailable: { one: 10, two: null },
    negative: { one: 10, two: -1 },
    infinite: { one: 10, two: Number.POSITIVE_INFINITY },
    "wrong-type": { one: 10, two: "twelve" },
  } as unknown as TravelTimeMatrix;

  const result = rankDestinations({
    origins: [
      { id: "one", label: "One" },
      { id: "two", label: "Two" },
    ],
    candidateVenues: [
      { id: "valid", name: "Valid" },
      { id: "missing", name: "Missing" },
      { id: "unavailable", name: "Unavailable" },
      { id: "negative", name: "Negative" },
      { id: "infinite", name: "Infinite" },
      { id: "wrong-type", name: "Wrong type" },
    ],
    travelTimes,
    rankingMode: RANKING_MODES.PROTECT_FARTHEST_TRAVELER,
  });

  assert.deepEqual(
    result.rankedVenues.map(({ venue }) => venue.id),
    ["valid"],
  );
  assert.deepEqual(
    Object.fromEntries(
      result.excludedVenues.map(({ venue, reasons }) => [
        venue.id,
        reasons.map(({ code }) => code),
      ]),
    ),
    {
      infinite: ["invalid-travel-time"],
      missing: ["missing-travel-time"],
      negative: ["invalid-travel-time"],
      unavailable: ["missing-travel-time"],
      "wrong-type": ["invalid-travel-time"],
    },
  );
});

test("rejects fewer than 2 origins", () => {
  assert.throws(
    () =>
      rankDestinations({
        origins: [{ id: "only", label: "Only" }],
        candidateVenues: [],
        travelTimes: {},
        rankingMode: RANKING_MODES.PROTECT_FARTHEST_TRAVELER,
      }),
    (error: unknown) =>
      error instanceof RankingInputError &&
      error.code === "invalid-origin-count",
  );
});

test("rejects more than 6 origins", () => {
  assert.throws(
    () =>
      rankDestinations({
        origins: Array.from({ length: 7 }, (_, index) => ({
          id: `origin-${index}`,
          label: `Origin ${index}`,
        })),
        candidateVenues: [],
        travelTimes: {},
        rankingMode: RANKING_MODES.PROTECT_FARTHEST_TRAVELER,
      }),
    (error: unknown) =>
      error instanceof RankingInputError &&
      error.code === "invalid-origin-count",
  );
});

test("rejects the removed fairest ranking mode", () => {
  assert.throws(
    () =>
      rankDestinations({
        ...exampleInput(RANKING_MODES.PROTECT_FARTHEST_TRAVELER),
        rankingMode: "fairest" as RankingMode,
      }),
    (error: unknown) =>
      error instanceof RankingInputError &&
      error.code === "unsupported-ranking-mode",
  );
});

test("exposes the ordered ranking criteria", () => {
  const result = rankDestinations(
    exampleInput(RANKING_MODES.PROTECT_FARTHEST_TRAVELER),
  );

  assert.deepEqual(result.rankingCriteria, [
    "maximumTravelTimeMinutes",
    "meanTravelTimeMinutes",
    "travelTimeSpreadMinutes",
  ]);
});
