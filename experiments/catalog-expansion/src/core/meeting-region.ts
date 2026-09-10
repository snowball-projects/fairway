export interface Coordinates {
  readonly latitude: number;
  readonly longitude: number;
}

export interface LocatedPoint {
  readonly id: string;
  readonly coordinates: Coordinates;
}

export interface MeetingRegionParameters {
  readonly localSearchRadiiKilometers: readonly number[];
  readonly localTargetCandidateCount: number;
  readonly globalMinimumTotalCandidateCount: number;
  readonly globalMinimumMaximumCandidateCount: number;
}

export interface LocalPoolEntry {
  readonly candidateId: string;
  readonly admittedRadiusKilometers: number;
}

export interface LocalPool {
  readonly searchedRadiusKilometers: number;
  readonly candidates: readonly LocalPoolEntry[];
}

export interface ShortlistEntry {
  readonly candidateId: string;
  readonly sources: {
    readonly minimumTotalLocalRadiusKilometers?: number;
    readonly minimumMaximumLocalRadiusKilometers?: number;
    readonly globalMinimumTotal: boolean;
    readonly globalMinimumMaximum: boolean;
  };
}

export interface MeetingRegionResult {
  readonly anchors: {
    readonly minimumTotal: Coordinates;
    readonly minimumMaximum: Coordinates;
  };
  readonly localPools: {
    readonly minimumTotal: LocalPool;
    readonly minimumMaximum: LocalPool;
  };
  readonly globalPools: {
    readonly minimumTotal: readonly string[];
    readonly minimumMaximum: readonly string[];
  };
  readonly shortlist: readonly ShortlistEntry[];
}

interface CandidateScore {
  readonly candidateId: string;
  readonly totalKilometers: number;
  readonly maximumKilometers: number;
}

const EARTH_RADIUS_KILOMETERS = 6_371.0088;
const SEARCH_BEARING_STEP_DEGREES = 5;
const SEARCH_STOP_KILOMETERS = 0.0001;
const SEARCH_ITERATION_LIMIT = 500;
const DISTANCE_TOLERANCE_KILOMETERS = 1e-7;
const OBJECTIVE_TOLERANCE_KILOMETERS = 1e-7;

export function shortlistMeetingRegionCandidates(
  origins: readonly LocatedPoint[],
  candidates: readonly LocatedPoint[],
  parameters: MeetingRegionParameters,
): MeetingRegionResult {
  validateInput(origins, candidates, parameters);

  const orderedOrigins = [...origins].sort(compareLocatedPoints);
  const orderedCandidates = [...candidates].sort((left, right) =>
    compareIds(left.id, right.id),
  );
  const originCoordinates = orderedOrigins.map(({ coordinates }) => coordinates);
  const anchors = {
    minimumTotal: findAnchor(originCoordinates, "total"),
    minimumMaximum: findAnchor(originCoordinates, "maximum"),
  };
  const localPools = {
    minimumTotal: buildLocalPool(
      anchors.minimumTotal,
      orderedCandidates,
      parameters,
    ),
    minimumMaximum: buildLocalPool(
      anchors.minimumMaximum,
      orderedCandidates,
      parameters,
    ),
  };
  const scores = scoreCandidates(originCoordinates, orderedCandidates);
  const globalPools = {
    minimumTotal: globalPool(
      scores,
      "totalKilometers",
      parameters.globalMinimumTotalCandidateCount,
    ),
    minimumMaximum: globalPool(
      scores,
      "maximumKilometers",
      parameters.globalMinimumMaximumCandidateCount,
    ),
  };

  return {
    anchors,
    localPools,
    globalPools,
    shortlist: combinePools(localPools, globalPools),
  };
}

function findAnchor(
  origins: readonly Coordinates[],
  objective: "total" | "maximum",
): Coordinates {
  let anchor = sphericalMean(origins);
  let score = distanceObjective(anchor, origins, objective);
  let stepKilometers = maximumPairDistance(origins) / 2;

  for (
    let iteration = 0;
    iteration < SEARCH_ITERATION_LIMIT &&
    stepKilometers > SEARCH_STOP_KILOMETERS;
    iteration += 1
  ) {
    let nextAnchor = anchor;
    let nextScore = score;

    for (
      let bearing = 0;
      bearing < 360;
      bearing += SEARCH_BEARING_STEP_DEGREES
    ) {
      const candidate = destinationPoint(anchor, bearing, stepKilometers);
      const candidateScore = distanceObjective(candidate, origins, objective);
      if (candidateScore < nextScore - OBJECTIVE_TOLERANCE_KILOMETERS) {
        nextAnchor = candidate;
        nextScore = candidateScore;
      }
    }

    if (nextAnchor === anchor) {
      stepKilometers /= 2;
    } else {
      anchor = nextAnchor;
      score = nextScore;
    }
  }

  return anchor;
}

function buildLocalPool(
  anchor: Coordinates,
  candidates: readonly LocatedPoint[],
  parameters: MeetingRegionParameters,
): LocalPool {
  const distances = candidates.map((candidate) => ({
    candidateId: candidate.id,
    kilometers: distanceKilometers(anchor, candidate.coordinates),
  }));
  let searchedRadiusKilometers = parameters.localSearchRadiiKilometers[0]!;

  for (const radius of parameters.localSearchRadiiKilometers) {
    searchedRadiusKilometers = radius;
    if (
      distances.filter(
        ({ kilometers }) =>
          kilometers <= radius + DISTANCE_TOLERANCE_KILOMETERS,
      ).length >= parameters.localTargetCandidateCount
    ) {
      break;
    }
  }

  return {
    searchedRadiusKilometers,
    candidates: distances
      .filter(
        ({ kilometers }) =>
          kilometers <=
          searchedRadiusKilometers + DISTANCE_TOLERANCE_KILOMETERS,
      )
      .map(({ candidateId, kilometers }) => ({
        candidateId,
        admittedRadiusKilometers:
          parameters.localSearchRadiiKilometers.find(
            (radius) =>
              kilometers <= radius + DISTANCE_TOLERANCE_KILOMETERS,
          )!,
      })),
  };
}

function scoreCandidates(
  origins: readonly Coordinates[],
  candidates: readonly LocatedPoint[],
): readonly CandidateScore[] {
  return candidates.map((candidate) => {
    const distances = origins.map((origin) =>
      distanceKilometers(origin, candidate.coordinates),
    );
    return {
      candidateId: candidate.id,
      totalKilometers: distances.reduce((sum, distance) => sum + distance, 0),
      maximumKilometers: Math.max(...distances),
    };
  });
}

function globalPool(
  scores: readonly CandidateScore[],
  objective: "totalKilometers" | "maximumKilometers",
  limit: number,
): readonly string[] {
  const secondary =
    objective === "totalKilometers" ? "maximumKilometers" : "totalKilometers";
  return [...scores]
    .sort(
      (left, right) =>
        left[objective] - right[objective] ||
        left[secondary] - right[secondary] ||
        compareIds(left.candidateId, right.candidateId),
    )
    .slice(0, limit)
    .map(({ candidateId }) => candidateId);
}

function combinePools(
  localPools: MeetingRegionResult["localPools"],
  globalPools: MeetingRegionResult["globalPools"],
): readonly ShortlistEntry[] {
  const sources = new Map<string, ShortlistEntry["sources"]>();
  const getSources = (candidateId: string): ShortlistEntry["sources"] => {
    const existing = sources.get(candidateId);
    if (existing !== undefined) {
      return existing;
    }
    const created = {
      globalMinimumTotal: false,
      globalMinimumMaximum: false,
    };
    sources.set(candidateId, created);
    return created;
  };

  for (const entry of localPools.minimumTotal.candidates) {
    Object.assign(getSources(entry.candidateId), {
      minimumTotalLocalRadiusKilometers: entry.admittedRadiusKilometers,
    });
  }
  for (const entry of localPools.minimumMaximum.candidates) {
    Object.assign(getSources(entry.candidateId), {
      minimumMaximumLocalRadiusKilometers: entry.admittedRadiusKilometers,
    });
  }
  for (const candidateId of globalPools.minimumTotal) {
    Object.assign(getSources(candidateId), { globalMinimumTotal: true });
  }
  for (const candidateId of globalPools.minimumMaximum) {
    Object.assign(getSources(candidateId), { globalMinimumMaximum: true });
  }

  return [...sources]
    .sort(([left], [right]) => compareIds(left, right))
    .map(([candidateId, candidateSources]) => ({
      candidateId,
      sources: candidateSources,
    }));
}

function sphericalMean(points: readonly Coordinates[]): Coordinates {
  let x = 0;
  let y = 0;
  let z = 0;
  for (const point of points) {
    const latitude = degreesToRadians(point.latitude);
    const longitude = degreesToRadians(point.longitude);
    x += Math.cos(latitude) * Math.cos(longitude);
    y += Math.cos(latitude) * Math.sin(longitude);
    z += Math.sin(latitude);
  }
  return {
    latitude: radiansToDegrees(Math.atan2(z, Math.hypot(x, y))),
    longitude: radiansToDegrees(Math.atan2(y, x)),
  };
}

function maximumPairDistance(points: readonly Coordinates[]): number {
  let maximum = 0;
  for (let first = 0; first < points.length; first += 1) {
    for (let second = first + 1; second < points.length; second += 1) {
      maximum = Math.max(
        maximum,
        distanceKilometers(points[first]!, points[second]!),
      );
    }
  }
  return maximum;
}

function distanceObjective(
  point: Coordinates,
  origins: readonly Coordinates[],
  objective: "total" | "maximum",
): number {
  const distances = origins.map((origin) => distanceKilometers(point, origin));
  return objective === "total"
    ? distances.reduce((sum, distance) => sum + distance, 0)
    : Math.max(...distances);
}

function distanceKilometers(from: Coordinates, to: Coordinates): number {
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

function destinationPoint(
  start: Coordinates,
  bearingDegrees: number,
  distance: number,
): Coordinates {
  const latitude = degreesToRadians(start.latitude);
  const longitude = degreesToRadians(start.longitude);
  const bearing = degreesToRadians(bearingDegrees);
  const angularDistance = distance / EARTH_RADIUS_KILOMETERS;
  const destinationLatitude = Math.asin(
    Math.sin(latitude) * Math.cos(angularDistance) +
      Math.cos(latitude) * Math.sin(angularDistance) * Math.cos(bearing),
  );
  const destinationLongitude =
    longitude +
    Math.atan2(
      Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(latitude),
      Math.cos(angularDistance) -
        Math.sin(latitude) * Math.sin(destinationLatitude),
    );
  return {
    latitude: radiansToDegrees(destinationLatitude),
    longitude: normalizeLongitude(radiansToDegrees(destinationLongitude)),
  };
}

function validateInput(
  origins: readonly LocatedPoint[],
  candidates: readonly LocatedPoint[],
  parameters: MeetingRegionParameters,
): void {
  if (origins.length < 2 || origins.length > 6) {
    throw new Error("Meeting-region shortlisting requires 2 to 6 origins.");
  }
  validatePoints(origins, "Origin");
  validatePoints(candidates, "Candidate");

  let previousRadius = -1;
  if (parameters.localSearchRadiiKilometers.length === 0) {
    throw new Error("At least one local search radius is required.");
  }
  for (const radius of parameters.localSearchRadiiKilometers) {
    if (!Number.isFinite(radius) || radius < 0 || radius <= previousRadius) {
      throw new Error("Local search radii must be increasing non-negative numbers.");
    }
    previousRadius = radius;
  }
  for (const count of [
    parameters.localTargetCandidateCount,
    parameters.globalMinimumTotalCandidateCount,
    parameters.globalMinimumMaximumCandidateCount,
  ]) {
    if (!Number.isInteger(count) || count < 1) {
      throw new Error("Candidate counts must be positive integers.");
    }
  }
}

function validatePoints(points: readonly LocatedPoint[], label: string): void {
  const ids = new Set<string>();
  for (const point of points) {
    const { latitude, longitude } = point.coordinates;
    if (point.id.length === 0 || ids.has(point.id)) {
      throw new Error(`${label} IDs must be non-empty and unique.`);
    }
    if (
      !Number.isFinite(latitude) ||
      latitude < -90 ||
      latitude > 90 ||
      !Number.isFinite(longitude) ||
      longitude < -180 ||
      longitude > 180
    ) {
      throw new Error(`${label} coordinates are invalid.`);
    }
    ids.add(point.id);
  }
}

function compareLocatedPoints(left: LocatedPoint, right: LocatedPoint): number {
  return (
    compareCoordinates(left.coordinates, right.coordinates) ||
    compareIds(left.id, right.id)
  );
}

function compareCoordinates(left: Coordinates, right: Coordinates): number {
  return left.latitude - right.latitude || left.longitude - right.longitude;
}

function normalizeLongitude(longitude: number): number {
  return ((longitude + 180) % 360 + 360) % 360 - 180;
}

function degreesToRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

function radiansToDegrees(radians: number): number {
  return (radians * 180) / Math.PI;
}

function compareIds(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}
