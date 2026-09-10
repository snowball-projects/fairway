import type {
  DrivingTravelTimeMatrixProvider,
  ExternalRequestReporter,
  LocatedOrigin,
} from "./location-providers.ts";
import type { LocatedCandidateVenue } from "../core/geographic-candidates.ts";
import type { TravelTimeMatrix } from "../core/ranking.ts";
import {
  isRecord,
  ProviderError,
  providerEndpoint,
  requestJson,
  type FetchImplementation,
} from "./provider-http.ts";

interface OpenRouteServiceMatrixOptions {
  readonly baseUrl: string;
  readonly apiKey: string;
  readonly timeoutMilliseconds: number;
  readonly fetchImplementation?: FetchImplementation;
  readonly reportExternalRequest?: ExternalRequestReporter;
}

export class OpenRouteServiceMatrix
  implements DrivingTravelTimeMatrixProvider
{
  readonly #baseUrl: string;
  readonly #apiKey: string;
  readonly #timeoutMilliseconds: number;
  readonly #fetchImplementation: FetchImplementation;
  readonly #reportExternalRequest?: ExternalRequestReporter;

  constructor(options: OpenRouteServiceMatrixOptions) {
    if (options.apiKey.trim().length === 0) {
      throw new ProviderError(
        "openrouteservice",
        "configuration",
        "OPENROUTESERVICE_API_KEY must be set before running the real-location spike.",
      );
    }

    this.#baseUrl = options.baseUrl;
    this.#apiKey = options.apiKey;
    this.#timeoutMilliseconds = options.timeoutMilliseconds;
    this.#fetchImplementation = options.fetchImplementation ?? fetch;
    this.#reportExternalRequest = options.reportExternalRequest;
  }

  async calculateDrivingTravelTimes(
    origins: readonly LocatedOrigin[],
    venues: readonly LocatedCandidateVenue[],
  ): Promise<TravelTimeMatrix> {
    const endpoint = providerEndpoint(
      this.#baseUrl,
      "v2/matrix/driving-car",
    );
    const locations = [...origins, ...venues].map(({ coordinates }) => [
      coordinates.longitude,
      coordinates.latitude,
    ]);

    this.#reportExternalRequest?.({
      provider: "openrouteservice",
      method: "POST",
      endpoint: `${endpoint.origin}${endpoint.pathname}`,
      sharedData: `${origins.length} origin coordinates and ${venues.length} venue coordinates; API key redacted`,
    });

    const response = await requestJson(
      "openrouteservice",
      this.#fetchImplementation,
      endpoint,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          Authorization: this.#apiKey,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          locations,
          sources: origins.map((_, index) => String(index)),
          destinations: venues.map((_, index) =>
            String(origins.length + index),
          ),
          metrics: ["duration"],
          resolve_locations: false,
        }),
      },
      this.#timeoutMilliseconds,
    );

    return normalizeMatrix(response, origins, venues);
  }
}

function normalizeMatrix(
  response: unknown,
  origins: readonly LocatedOrigin[],
  venues: readonly LocatedCandidateVenue[],
): TravelTimeMatrix {
  if (
    !isRecord(response) ||
    !Array.isArray(response.durations) ||
    response.durations.length !== origins.length
  ) {
    throw malformedResponse();
  }

  const travelTimes: Record<string, Record<string, number | null>> =
    Object.fromEntries(venues.map(({ id }) => [id, {}]));

  response.durations.forEach((row, originIndex) => {
    if (!Array.isArray(row) || row.length !== venues.length) {
      throw malformedResponse();
    }

    row.forEach((seconds, venueIndex) => {
      if (
        seconds !== null &&
        (typeof seconds !== "number" ||
          !Number.isFinite(seconds) ||
          seconds < 0)
      ) {
        throw malformedResponse();
      }

      const origin = origins[originIndex]!;
      const venue = venues[venueIndex]!;
      travelTimes[venue.id]![origin.id] =
        seconds === null ? null : seconds / 60;
    });
  });

  return travelTimes;
}

function malformedResponse(): ProviderError {
  return new ProviderError(
    "openrouteservice",
    "malformed-response",
    "openrouteservice returned an unexpected duration-matrix response shape.",
  );
}
