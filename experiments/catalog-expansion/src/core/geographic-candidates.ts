import type { CandidateVenue } from "./ranking.ts";

export interface Coordinates {
  readonly longitude: number;
  readonly latitude: number;
}

export interface SearchBounds {
  readonly south: number;
  readonly west: number;
  readonly north: number;
  readonly east: number;
}

export interface LocatedCandidateVenue extends CandidateVenue {
  readonly coordinates: Coordinates;
}

const KILOMETERS_PER_LATITUDE_DEGREE = 111.32;
const EARTH_RADIUS_KILOMETERS = 6_371.0088;

export interface GeographicSearchOptions {
  readonly bufferKilometers: number;
  readonly minimumSpanKilometers: number;
  readonly maximumSpanKilometers: number;
}

interface GeometricCandidate {
  readonly venue: LocatedCandidateVenue;
  readonly maximumDistanceKilometers: number;
  readonly totalDistanceKilometers: number;
  readonly distanceSpreadKilometers: number;
}

type GeometricCriterion =
  | "maximumDistanceKilometers"
  | "totalDistanceKilometers"
  | "distanceSpreadKilometers";

const CRITERIA = [
  "maximumDistanceKilometers",
  "totalDistanceKilometers",
  "distanceSpreadKilometers",
] as const satisfies readonly GeometricCriterion[];

export function deriveSearchBounds(
  origins: readonly Coordinates[],
  options: GeographicSearchOptions,
): SearchBounds {
  if (origins.length === 0) {
    throw new Error("At least one origin coordinate is required.");
  }
  origins.forEach((coordinates, index) =>
    validateCoordinates(coordinates, `Origin ${index + 1}`),
  );
  validateGeographicSearchOptions(options);

  const latitudes = origins.map(({ latitude }) => latitude);
  const longitudes = origins.map(({ longitude }) => longitude);
  const minimumLatitude = Math.min(...latitudes);
  const maximumLatitude = Math.max(...latitudes);
  const minimumLongitude = Math.min(...longitudes);
  const maximumLongitude = Math.max(...longitudes);
  const centerLatitude = (minimumLatitude + maximumLatitude) / 2;
  const centerLongitude = (minimumLongitude + maximumLongitude) / 2;
  const kilometersPerLongitudeDegree =
    KILOMETERS_PER_LATITUDE_DEGREE *
    Math.cos(degreesToRadians(centerLatitude));

  if (kilometersPerLongitudeDegree <= 0) {
    throw new Error("Search bounds cannot be derived at the geographic poles.");
  }

  const latitudeSpanKilometers =
    (maximumLatitude - minimumLatitude) *
    KILOMETERS_PER_LATITUDE_DEGREE;
  const longitudeSpanKilometers =
    (maximumLongitude - minimumLongitude) *
    kilometersPerLongitudeDegree;
  const boundedLatitudeSpan = boundedSpan(
    latitudeSpanKilometers,
    options,
  );
  const boundedLongitudeSpan = boundedSpan(
    longitudeSpanKilometers,
    options,
  );

  const [south, north] = centeredInterval(
    centerLatitude,
    boundedLatitudeSpan / KILOMETERS_PER_LATITUDE_DEGREE,
    -90,
    90,
  );
  const [west, east] = centeredInterval(
    centerLongitude,
    boundedLongitudeSpan / kilometersPerLongitudeDegree,
    -180,
    180,
  );

  return { south, west, north, east };
}

export function originsFitGeographicSearchEnvelope(
  origins: readonly Coordinates[],
  options: GeographicSearchOptions,
): boolean {
  if (origins.length === 0) {
    throw new Error("At least one origin coordinate is required.");
  }
  origins.forEach((coordinates, index) =>
    validateCoordinates(coordinates, `Origin ${index + 1}`),
  );
  validateGeographicSearchOptions(options);

  const latitudes = origins.map(({ latitude }) => latitude);
  const longitudes = origins.map(({ longitude }) => longitude);
  const centerLatitude =
    (Math.min(...latitudes) + Math.max(...latitudes)) / 2;
  const kilometersPerLongitudeDegree =
    KILOMETERS_PER_LATITUDE_DEGREE *
    Math.cos(degreesToRadians(centerLatitude));
  if (kilometersPerLongitudeDegree <= 0) {
    return false;
  }

  const latitudeSpanKilometers =
    (Math.max(...latitudes) - Math.min(...latitudes)) *
    KILOMETERS_PER_LATITUDE_DEGREE;
  const longitudeSpanKilometers =
    (Math.max(...longitudes) - Math.min(...longitudes)) *
    kilometersPerLongitudeDegree;
  const requiredBuffer = options.bufferKilometers * 2;

  return (
    latitudeSpanKilometers + requiredBuffer <=
      options.maximumSpanKilometers &&
    longitudeSpanKilometers + requiredBuffer <=
      options.maximumSpanKilometers
  );
}

export function shortlistVenuesGeometrically(
  origins: readonly Coordinates[],
  venues: readonly LocatedCandidateVenue[],
  limit: number,
): readonly LocatedCandidateVenue[] {
  if (origins.length === 0) {
    throw new Error("At least one origin coordinate is required.");
  }
  if (!Number.isInteger(limit) || limit < 1) {
    throw new Error("Geometric shortlist limit must be a positive integer.");
  }
  origins.forEach((coordinates, index) =>
    validateCoordinates(coordinates, `Origin ${index + 1}`),
  );

  const seenVenueIds = new Set<string>();
  const candidates = venues.map((venue, index) => {
    validateCoordinates(venue.coordinates, `Venue ${index + 1}`);
    if (seenVenueIds.has(venue.id)) {
      throw new Error(`Venue ID "${venue.id}" is duplicated.`);
    }
    seenVenueIds.add(venue.id);

    const distances = origins.map((origin) =>
      straightLineDistanceKilometers(origin, venue.coordinates),
    );
    const maximumDistanceKilometers = Math.max(...distances);
    const minimumDistanceKilometers = Math.min(...distances);
    const totalDistanceKilometers = distances.reduce(
      (total, distance) => total + distance,
      0,
    );

    return {
      venue,
      maximumDistanceKilometers,
      totalDistanceKilometers,
      distanceSpreadKilometers:
        maximumDistanceKilometers - minimumDistanceKilometers,
    };
  });

  if (candidates.length <= limit) {
    return candidates
      .sort((left, right) => compareIds(left.venue.id, right.venue.id))
      .map(({ venue }) => venue);
  }

  const strongestByCriterion = CRITERIA.map((criterion) =>
    [...candidates]
      .sort((left, right) => compareCandidates(left, right, criterion))
      .slice(0, limit),
  );
  const selected: LocatedCandidateVenue[] = [];
  const selectedIds = new Set<string>();

  for (let rank = 0; selected.length < limit; rank += 1) {
    for (const ordered of strongestByCriterion) {
      const candidate = ordered[rank];
      if (
        candidate !== undefined &&
        !selectedIds.has(candidate.venue.id)
      ) {
        selected.push(candidate.venue);
        selectedIds.add(candidate.venue.id);
        if (selected.length === limit) {
          break;
        }
      }
    }
  }

  return selected;
}

function boundedSpan(
  originSpanKilometers: number,
  options: GeographicSearchOptions,
): number {
  const bufferedSpan =
    originSpanKilometers + options.bufferKilometers * 2;
  return Math.min(
    Math.max(bufferedSpan, options.minimumSpanKilometers),
    options.maximumSpanKilometers,
  );
}

function centeredInterval(
  center: number,
  span: number,
  minimum: number,
  maximum: number,
): readonly [number, number] {
  let lower = center - span / 2;
  let upper = center + span / 2;
  if (lower < minimum) {
    upper += minimum - lower;
    lower = minimum;
  }
  if (upper > maximum) {
    lower -= upper - maximum;
    upper = maximum;
  }
  return [Math.max(lower, minimum), Math.min(upper, maximum)];
}

function compareCandidates(
  left: GeometricCandidate,
  right: GeometricCandidate,
  primaryCriterion: GeometricCriterion,
): number {
  const tieBreakers = CRITERIA.filter(
    (criterion) => criterion !== primaryCriterion,
  );
  for (const criterion of [primaryCriterion, ...tieBreakers]) {
    const difference = left[criterion] - right[criterion];
    if (difference !== 0) {
      return difference;
    }
  }
  return compareIds(left.venue.id, right.venue.id);
}

function straightLineDistanceKilometers(
  from: Coordinates,
  to: Coordinates,
): number {
  const latitudeDifference = degreesToRadians(
    to.latitude - from.latitude,
  );
  const longitudeDifference = degreesToRadians(
    to.longitude - from.longitude,
  );
  const fromLatitude = degreesToRadians(from.latitude);
  const toLatitude = degreesToRadians(to.latitude);
  const haversine =
    Math.sin(latitudeDifference / 2) ** 2 +
    Math.cos(fromLatitude) *
      Math.cos(toLatitude) *
      Math.sin(longitudeDifference / 2) ** 2;
  return (
    2 *
    EARTH_RADIUS_KILOMETERS *
    Math.asin(Math.sqrt(Math.min(1, haversine)))
  );
}

function validateCoordinates(
  coordinates: Coordinates,
  label: string,
): void {
  if (
    !Number.isFinite(coordinates.latitude) ||
    coordinates.latitude < -90 ||
    coordinates.latitude > 90 ||
    !Number.isFinite(coordinates.longitude) ||
    coordinates.longitude < -180 ||
    coordinates.longitude > 180
  ) {
    throw new Error(`${label} has invalid coordinates.`);
  }
}

export function validateGeographicSearchOptions(
  options: GeographicSearchOptions,
): void {
  if (
    !Number.isFinite(options.bufferKilometers) ||
    options.bufferKilometers < 0
  ) {
    throw new Error("Search buffer must be finite and non-negative.");
  }
  if (
    !Number.isFinite(options.minimumSpanKilometers) ||
    options.minimumSpanKilometers <= 0
  ) {
    throw new Error("Minimum search span must be finite and positive.");
  }
  if (
    !Number.isFinite(options.maximumSpanKilometers) ||
    options.maximumSpanKilometers < options.minimumSpanKilometers
  ) {
    throw new Error(
      "Maximum search span must be finite and at least the minimum search span.",
    );
  }
}

function degreesToRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

function compareIds(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}
