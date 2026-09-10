import type {
  CandidateVenue,
  Origin,
  TravelTimeMatrix,
} from "../src/core/ranking.ts";

export const fourTravelerOrigins = [
  { id: "alex", label: "Alex" },
  { id: "blair", label: "Blair" },
  { id: "casey", label: "Casey" },
  { id: "devon", label: "Devon" },
] as const satisfies readonly Origin[];

export const exampleCandidateVenues = [
  { id: "civic-library", name: "Civic Library" },
  { id: "riverside-cafe", name: "Riverside Cafe" },
  { id: "central-park", name: "Central Park" },
  { id: "market-hall", name: "Market Hall" },
  { id: "distant-museum", name: "Distant Museum" },
] as const satisfies readonly CandidateVenue[];

export const exampleTravelTimes = {
  "civic-library": { alex: 10, blair: 15, casey: 20, devon: 24 },
  "riverside-cafe": { alex: 10, blair: 18, casey: 26, devon: 34 },
  "central-park": { alex: 24, blair: 24, casey: 25, devon: 25 },
  "market-hall": { alex: 5, blair: 10, casey: 20, devon: 27 },
  "distant-museum": { alex: 15, blair: 22, casey: 28, devon: 42 },
} as const satisfies TravelTimeMatrix;
