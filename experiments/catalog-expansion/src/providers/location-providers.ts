import type {
  Origin,
  TravelTimeMatrix,
} from "../core/ranking.ts";
import type {
  Coordinates,
  LocatedCandidateVenue,
} from "../core/geographic-candidates.ts";

export interface OriginAddress {
  readonly label: string;
  readonly address: string;
}

export interface GeocodingCandidate {
  readonly coordinates: Coordinates;
  readonly displayName: string;
}

export type GeocodingResult =
  | {
      readonly status: "found";
      readonly candidate: GeocodingCandidate;
    }
  | {
      readonly status: "not-found";
    }
  | {
      readonly status: "ambiguous";
      readonly candidates: readonly GeocodingCandidate[];
    };

export interface AddressGeocoder {
  geocodeAddress(address: string): Promise<GeocodingResult>;
}

export interface LocatedOrigin extends Origin {
  readonly coordinates: Coordinates;
}

export interface OriginAutocompleteSuggestion {
  readonly id: string;
  readonly label: string;
  readonly coordinates: Coordinates;
}

export interface OriginAutocompleteProvider {
  autocomplete(
    text: string,
  ): Promise<readonly OriginAutocompleteSuggestion[]>;
}

export interface DrivingTravelTimeMatrixProvider {
  calculateDrivingTravelTimes(
    origins: readonly LocatedOrigin[],
    venues: readonly LocatedCandidateVenue[],
  ): Promise<TravelTimeMatrix>;
}

export interface ExternalRequestRecord {
  readonly provider: "nominatim" | "overpass" | "openrouteservice";
  readonly method: "GET" | "POST";
  readonly endpoint: string;
  readonly sharedData: string;
}

export type ExternalRequestReporter = (record: ExternalRequestRecord) => void;
