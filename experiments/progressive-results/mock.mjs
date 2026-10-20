import {fixture} from './catalog-fixture.mjs';
export const profile = [
  [1800000, 3000000], [2700000, 2700000], [2400000, 2760000],
  [1980000, 3300000], [2520000, 2880000], [null, 1920000],
];
// Destination/row slices model batches, not a router emitting cells one by one.
export function mockSearch(request, deliver, {failure = false, schedule = setTimeout, unschedule = clearTimeout} = {}) {
  const event = (sequence, type, data = {}) => ({generation: request.generation, sequence, type, ...data});
  const times = i => Array.from({length: request.origins.length}, (_, n) =>
    n < 2 ? profile[i][n] : profile[i][0] === null ? null : profile[i][0] + n * 60000);
  const ids = fixture.facilities.map(f => f.id);
  const events = [
    [1800, event(1, 'area.ready', {duration_ms: 1800, areas: [{id: 'mock-area', center: [42.04, -87.94], facility_radius_kilometers: 25, resolution_kilometers: 3}]})],
    [1900, event(2, 'candidates.ready', {facilities: fixture.facilities})],
    [4200, event(3, 'matrix.batch', {destinations: ids.slice(0, 2).map((id, i) => ({id, times: times(i)}))})],
    [5700, event(4, 'matrix.batch', {destinations: ids.slice(2).map((id, j) => ({id, times: times(j + 2).map((t, n) => n ? null : t)}))})],
    [7200, failure ? event(5, 'search.error', {error: {code: 'mock_routing_unavailable', retryable: true}}) : event(5, 'matrix.batch', {destinations: ids.slice(2).map((id, j) => ({id, times: times(j + 2), reason: j === 3 ? 'unreachable' : null}))})],
    ...(!failure ? [[7300, event(6, 'search.complete', {scoring_ms: 2})]] : []),
  ];
  const handles = events.map(([delay, payload]) => schedule(() => deliver(payload), delay));
  return () => handles.forEach(unschedule);
}
