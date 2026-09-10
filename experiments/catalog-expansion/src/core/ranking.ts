export interface Origin {
  readonly id: string;
  readonly label: string;
}

export interface CandidateVenue {
  readonly id: string;
  readonly name: string;
}

type TravelTimeRow = Readonly<Partial<Record<string, number | null>>>;

export type TravelTimeMatrix = Readonly<
  Partial<Record<string, TravelTimeRow>>
>;

export const RANKING_MODES = {
  PROTECT_FARTHEST_TRAVELER: "protect-farthest-traveler",
  LOWEST_TOTAL_TRAVEL: "lowest-total-travel",
} as const;

export type RankingMode =
  (typeof RANKING_MODES)[keyof typeof RANKING_MODES];

export interface RankDestinationsInput {
  readonly origins: readonly Origin[];
  readonly candidateVenues: readonly CandidateVenue[];
  readonly travelTimes: TravelTimeMatrix;
  readonly maximumTravelTimeMinutes?: number;
  readonly rankingMode: RankingMode;
}

export type RankDestinationsForAllModesInput = Omit<
  RankDestinationsInput,
  "rankingMode"
>;

export interface TravelTimeMetrics {
  readonly maximumTravelTimeMinutes: number;
  readonly minimumTravelTimeMinutes: number;
  readonly meanTravelTimeMinutes: number;
  readonly totalTravelTimeMinutes: number;
  readonly travelTimeSpreadMinutes: number;
}

export type RankingMetric = keyof TravelTimeMetrics;

export interface RankedVenue {
  readonly rank: number;
  readonly venue: CandidateVenue;
  readonly travelTimes: readonly {
    readonly originId: string;
    readonly minutes: number;
  }[];
  readonly metrics: TravelTimeMetrics;
}

export type VenueExclusionReason =
  | {
      readonly code: "missing-travel-time";
      readonly originId: string;
    }
  | {
      readonly code: "invalid-travel-time";
      readonly originId: string;
    }
  | {
      readonly code: "maximum-travel-time-exceeded";
      readonly originId: string;
      readonly travelTimeMinutes: number;
      readonly maximumTravelTimeMinutes: number;
    };

export interface ExcludedVenue {
  readonly venue: CandidateVenue;
  readonly reasons: readonly VenueExclusionReason[];
}

export interface RankDestinationsResult {
  readonly rankingMode: RankingMode;
  readonly rankingCriteria: readonly RankingMetric[];
  readonly rankedVenues: readonly RankedVenue[];
  readonly excludedVenues: readonly ExcludedVenue[];
}

export type RankDestinationsForAllModesResult = Readonly<
  Record<RankingMode, RankDestinationsResult>
>;

export type RankingInputErrorCode =
  | "invalid-origin-count"
  | "invalid-origin"
  | "duplicate-origin-id"
  | "invalid-candidate-venue"
  | "duplicate-venue-id"
  | "invalid-maximum-travel-time"
  | "unsupported-ranking-mode";

export class RankingInputError extends Error {
  readonly code: RankingInputErrorCode;

  constructor(code: RankingInputErrorCode, message: string) {
    super(message);
    this.name = "RankingInputError";
    this.code = code;
  }
}

const RANKING_CRITERIA = {
  [RANKING_MODES.PROTECT_FARTHEST_TRAVELER]: [
    "maximumTravelTimeMinutes",
    "meanTravelTimeMinutes",
    "travelTimeSpreadMinutes",
  ],
  [RANKING_MODES.LOWEST_TOTAL_TRAVEL]: [
    "totalTravelTimeMinutes",
    "maximumTravelTimeMinutes",
    "travelTimeSpreadMinutes",
  ],
} as const satisfies Readonly<
  Record<RankingMode, readonly RankingMetric[]>
>;

interface EligibleVenue {
  readonly venue: CandidateVenue;
  readonly travelTimes: RankedVenue["travelTimes"];
  readonly metrics: TravelTimeMetrics;
}

export function rankDestinations(
  input: RankDestinationsInput,
): RankDestinationsResult {
  validateInput(input);
  validateRankingMode(input.rankingMode);
  return rankEligibleVenues(
    evaluateVenues(input),
    input.rankingMode,
  );
}

export function rankDestinationsForAllModes(
  input: RankDestinationsForAllModesInput,
): RankDestinationsForAllModesResult {
  validateInput(input);
  const evaluated = evaluateVenues(input);

  return {
    [RANKING_MODES.PROTECT_FARTHEST_TRAVELER]: rankEligibleVenues(
      evaluated,
      RANKING_MODES.PROTECT_FARTHEST_TRAVELER,
    ),
    [RANKING_MODES.LOWEST_TOTAL_TRAVEL]: rankEligibleVenues(
      evaluated,
      RANKING_MODES.LOWEST_TOTAL_TRAVEL,
    ),
  };
}

interface EvaluatedVenues {
  readonly eligibleVenues: readonly EligibleVenue[];
  readonly excludedVenues: readonly ExcludedVenue[];
}

function evaluateVenues(
  input: RankDestinationsForAllModesInput,
): EvaluatedVenues {
  const eligibleVenues: EligibleVenue[] = [];
  const excludedVenues: ExcludedVenue[] = [];

  for (const candidateVenue of input.candidateVenues) {
    const venue = { ...candidateVenue };
    const row = getOwnValue(input.travelTimes, candidateVenue.id);
    const reasons: VenueExclusionReason[] = [];
    const travelTimes: {
      readonly originId: string;
      readonly minutes: number;
    }[] = [];

    for (const origin of input.origins) {
      const receivedValue: unknown =
        row === undefined ? undefined : getOwnValue(row, origin.id);

      if (receivedValue === undefined || receivedValue === null) {
        reasons.push({
          code: "missing-travel-time",
          originId: origin.id,
        });
        continue;
      }

      if (
        typeof receivedValue !== "number" ||
        !Number.isFinite(receivedValue) ||
        receivedValue < 0
      ) {
        reasons.push({
          code: "invalid-travel-time",
          originId: origin.id,
        });
        continue;
      }

      travelTimes.push({ originId: origin.id, minutes: receivedValue });

      if (
        input.maximumTravelTimeMinutes !== undefined &&
        receivedValue > input.maximumTravelTimeMinutes
      ) {
        reasons.push({
          code: "maximum-travel-time-exceeded",
          originId: origin.id,
          travelTimeMinutes: receivedValue,
          maximumTravelTimeMinutes: input.maximumTravelTimeMinutes,
        });
      }
    }

    if (reasons.length > 0) {
      excludedVenues.push({ venue, reasons });
      continue;
    }

    eligibleVenues.push({
      venue,
      travelTimes,
      metrics: calculateMetrics(travelTimes.map(({ minutes }) => minutes)),
    });
  }

  excludedVenues.sort((left, right) =>
    compareIds(left.venue.id, right.venue.id),
  );

  return { eligibleVenues, excludedVenues };
}

function rankEligibleVenues(
  evaluated: EvaluatedVenues,
  rankingMode: RankingMode,
): RankDestinationsResult {
  const rankingCriteria = RANKING_CRITERIA[rankingMode];
  const eligibleVenues = [...evaluated.eligibleVenues];

  eligibleVenues.sort((left, right) => {
    for (const criterion of rankingCriteria) {
      const difference =
        left.metrics[criterion] - right.metrics[criterion];
      if (difference !== 0) {
        return difference;
      }
    }

    return compareIds(left.venue.id, right.venue.id);
  });

  return {
    rankingMode,
    rankingCriteria: [...rankingCriteria],
    rankedVenues: eligibleVenues.map((eligibleVenue, index) => ({
      rank: index + 1,
      ...eligibleVenue,
    })),
    excludedVenues: evaluated.excludedVenues,
  };
}

function calculateMetrics(
  travelTimeMinutes: readonly number[],
): TravelTimeMetrics {
  const totalTravelTimeMinutes = travelTimeMinutes.reduce(
    (total, minutes) => total + minutes,
    0,
  );
  const maximumTravelTimeMinutes = Math.max(...travelTimeMinutes);
  const minimumTravelTimeMinutes = Math.min(...travelTimeMinutes);

  return {
    maximumTravelTimeMinutes,
    minimumTravelTimeMinutes,
    meanTravelTimeMinutes:
      totalTravelTimeMinutes / travelTimeMinutes.length,
    totalTravelTimeMinutes,
    travelTimeSpreadMinutes:
      maximumTravelTimeMinutes - minimumTravelTimeMinutes,
  };
}

function validateInput(input: RankDestinationsForAllModesInput): void {
  if (input.origins.length < 2 || input.origins.length > 6) {
    throw new RankingInputError(
      "invalid-origin-count",
      `Expected between 2 and 6 origins; received ${input.origins.length}.`,
    );
  }

  assertOriginsAreValid(input.origins);
  assertCandidateVenuesAreValid(input.candidateVenues);

  if (
    input.maximumTravelTimeMinutes !== undefined &&
    (!Number.isFinite(input.maximumTravelTimeMinutes) ||
      input.maximumTravelTimeMinutes < 0)
  ) {
    throw new RankingInputError(
      "invalid-maximum-travel-time",
      "Maximum travel time must be a finite, non-negative number.",
    );
  }
}

function validateRankingMode(rankingMode: RankingMode): void {
  if (!Object.hasOwn(RANKING_CRITERIA, rankingMode)) {
    throw new RankingInputError(
      "unsupported-ranking-mode",
      `Unsupported ranking mode "${String(rankingMode)}".`,
    );
  }
}

function assertOriginsAreValid(origins: readonly Origin[]): void {
  const seenOriginIds = new Set<string>();

  for (const origin of origins) {
    if (typeof origin.id !== "string" || origin.id.length === 0) {
      throw new RankingInputError(
        "invalid-origin",
        "Every origin must have a non-empty string ID.",
      );
    }

    if (seenOriginIds.has(origin.id)) {
      throw new RankingInputError(
        "duplicate-origin-id",
        `Origin ID "${origin.id}" is duplicated.`,
      );
    }

    seenOriginIds.add(origin.id);
  }
}

function assertCandidateVenuesAreValid(
  candidateVenues: readonly CandidateVenue[],
): void {
  const seenVenueIds = new Set<string>();

  for (const venue of candidateVenues) {
    if (typeof venue.id !== "string" || venue.id.length === 0) {
      throw new RankingInputError(
        "invalid-candidate-venue",
        "Every candidate venue must have a non-empty string ID.",
      );
    }

    if (seenVenueIds.has(venue.id)) {
      throw new RankingInputError(
        "duplicate-venue-id",
        `Candidate venue ID "${venue.id}" is duplicated.`,
      );
    }

    seenVenueIds.add(venue.id);
  }
}

function getOwnValue<T>(
  record: Readonly<Partial<Record<string, T>>>,
  key: string,
): T | undefined {
  return Object.hasOwn(record, key) ? record[key] : undefined;
}

function compareIds(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}
