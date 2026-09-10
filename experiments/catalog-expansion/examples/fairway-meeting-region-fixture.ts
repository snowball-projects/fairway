import type {
  LocatedPoint,
  MeetingRegionParameters,
} from "../src/core/meeting-region.ts";

export interface SyntheticGolfCourse extends LocatedPoint {
  readonly name: string;
}

export const dispersedFairwayOrigins: readonly LocatedPoint[] = [
  {
    id: "chicago",
    coordinates: { latitude: 41.8781, longitude: -87.6298 },
  },
  {
    id: "dallas",
    coordinates: { latitude: 32.7767, longitude: -96.797 },
  },
  {
    id: "denver",
    coordinates: { latitude: 39.7392, longitude: -104.9903 },
  },
  {
    id: "nashville",
    coordinates: { latitude: 36.1627, longitude: -86.7816 },
  },
];

// These are intentionally synthetic catalog entries, not discovered courses.
export const syntheticGolfCourses: readonly SyntheticGolfCourse[] = [
  {
    id: "flint-hills-links",
    name: "Flint Hills Links",
    coordinates: { latitude: 38.4039, longitude: -96.1817 },
  },
  {
    id: "heartland-golf-club",
    name: "Heartland Golf Club",
    coordinates: { latitude: 38.8814, longitude: -94.8191 },
  },
  {
    id: "ozark-fairways",
    name: "Ozark Fairways",
    coordinates: { latitude: 37.209, longitude: -93.2923 },
  },
  {
    id: "prairie-crossing-course",
    name: "Prairie Crossing Course",
    coordinates: { latitude: 38.8403, longitude: -97.6114 },
  },
  {
    id: "red-river-golf-club",
    name: "Red River Golf Club",
    coordinates: { latitude: 35.4676, longitude: -97.5164 },
  },
  {
    id: "western-plains-links",
    name: "Western Plains Links",
    coordinates: { latitude: 39.0558, longitude: -101.0524 },
  },
];

export const fairwayShortlistingParameters: MeetingRegionParameters = {
  localSearchRadiiKilometers: [100, 250, 500],
  localTargetCandidateCount: 3,
  globalMinimumTotalCandidateCount: 2,
  globalMinimumMaximumCandidateCount: 2,
};
