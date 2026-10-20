import {fixture} from './catalog-fixture.mjs';
import {ProgressiveSearch, score} from './model.mjs';
import {mockSearch} from './mock.mjs';
import {canRemoveOrigin} from '../../src/fairway/static/origin-rows.mjs';
const $ = id => document.getElementById(id);
const map = L.map('map', {attributionControl: false}).setView([42.04, -87.94], 10);
const layer = L.layerGroup().addTo(map);
let cancelMock = () => {}, lastMapKey = '', nodes = new Map();
const preparation = () => ({byId: new Map(fixture.facilities.map(f => [f.id, f])), count: fixture.facilities.length});
const state = new ProgressiveSearch({prepare: preparation, notify: render});
const minutes = ms => `${Math.round(ms / 60000)} min`;
function stop() {cancelMock(); cancelMock = () => {};}
function addRow() {
  if (state.texts.length >= 8) return;
  stop(); state.texts.push(''); state.committed.push(null); state.invalidate(); buildOrigins();
}
function buildOrigins() {
  $('origins').replaceChildren();
  state.texts.forEach((text, i) => {
    const label = document.createElement('label'); label.textContent = `Golfer ${i + 1} · latitude, longitude`;
    const input = document.createElement('input'); input.type = 'text'; input.value = text;
    input.id = `origin-${i}`; input.autocomplete = 'off'; input.spellcheck = false;
    input.placeholder = i ? '42.10, -87.75' : '41.90, -88.00';
    input.setAttribute('aria-describedby', 'preparation');
    input.addEventListener('input', () => {stop(); state.edit(i, input.value); input.removeAttribute('aria-invalid');});
    const commit = () => {input.setAttribute('aria-invalid', String(!state.commit(i)));};
    input.addEventListener('blur', commit);
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.isComposing) {e.preventDefault(); commit();}
    });
    label.append(input); $('origins').append(label);
    if (canRemoveOrigin(state.texts.length, i)) {
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = `Remove golfer ${i + 1}`;
      remove.onclick = () => {stop(); state.texts.splice(i, 1); state.committed.splice(i, 1); state.invalidate(); buildOrigins();};
      $('origins').append(remove);
    }
  });
  $('add').disabled = state.texts.length >= 8;
}
function makeCourse(row) {
  const element = document.createElement('article'); element.className = 'course'; element.dataset.id = row.id;
  const title = document.createElement('button'); title.type = 'button'; title.textContent = row.name;
  title.onclick = () => map.setView([row.map_location.latitude, row.map_location.longitude], 12);
  const basis = document.createElement('p'); basis.className = 'note';
  basis.textContent = `${row.state} · ${row.physical_holes} physical holes · existing property point · public layouts unconfirmed`;
  const times = document.createElement('p'); times.className = 'times';
  const result = document.createElement('p'); result.className = 'score';
  element.append(title, basis, times, result);
  element.addEventListener('focusin', () => state.interact(row.id, true));
  element.addEventListener('focusout', e => {
    if (element.contains(e.relatedTarget)) return;
    const next = e.relatedTarget?.closest('.course');
    state.transferFocus(row.id, next?.parentElement === $('results') ? next.dataset.id : null);
  });
  element.addEventListener('mouseenter', () => state.interact(row.id, true, 'pointer'));
  element.addEventListener('mouseleave', () => state.interact(row.id, false, 'pointer'));
  return {element, times, result};
}
function render() {
  if (!state) return;
  $('search').disabled = !state.canStart();
  $('cancel').hidden = !['area', 'shortlist', 'matrix'].includes(state.phase);
  $('preparation').textContent = `Enter or leave each box to confirm complete coordinates. ${state.preparations} local preparation actions; ${state.searches} mock searches. No input is transmitted.`;
  const readiness = !state.key() ? 'Confirm every golfer origin before Search.'
    : state.key() !== state.cacheKey ? 'Group changed. Press Enter in an origin box or leave it to prepare this group.'
    : 'Ready. Catalog IDs are prepared locally.';
  const messages = {entry: readiness, area: 'modo is finding an approximate ideal meeting area…', shortlist: 'Meeting area ready. Finding nearby catalog facilities…', matrix: 'Nearby courses shown. Driving-time matrix batches are arriving…', complete: 'Ranking complete for this bounded candidate set.', cancelled: 'Search cancelled. Confirm origins and search again.', error: state.error};
  $('status').textContent = state.upstreamOutcomeUnknown
    ? 'Upstream outcome unknown. Operator reconciliation required; new searches remain blocked.'
    : state.phase === 'error' && state.errorRetryable
    ? `${state.error} You may explicitly retry this mock search.` : messages[state.phase];
  $('results').setAttribute('aria-busy', String(['area','shortlist','matrix'].includes(state.phase)));
  $('area-stage').dataset.state = state.areas.length ? 'done' : 'pending';
  $('matrix-stage').dataset.state = state.phase === 'complete' ? 'done' : 'pending';
  $('score-stage').dataset.state = state.phase === 'complete' ? 'done' : 'pending';
  $('ranking-note').textContent = state.areaObjective && state.areaObjective !== state.objective
    ? `Reordered same ${state.areaObjective} area candidate set. Search again for an objective-specific area.`
    : state.phase === 'complete' ? 'Final within this shortlist · approximate, traffic-unaware'
    : state.phase === 'error' ? 'No final ranking · routing error'
    : state.phase === 'entry' ? 'Search to compare group drives'
    : state.phase === 'cancelled' ? 'Cancelled · comparison incomplete'
    : 'Provisional until all batches finish';
  // Same-matrix re-sort never pretends to be a fresh objective-specific area search.
  $('search').textContent = state.upstreamOutcomeUnknown ? 'Search blocked'
    : state.phase === 'error' && state.errorRetryable ? 'Retry mock search'
    : state.phase === 'complete' && state.areaObjective !== state.objective ? 'Search new meeting area' : 'Search';
  $('sort-note').textContent = state.sortPending ? 'New order ready. Rows stay in place while a course has focus or pointer interaction.' : '';
  const activeIds = new Set(state.rows.map(r => r.id));
  for (const [id, node] of nodes) if (!activeIds.has(id)) {node.element.remove(); nodes.delete(id);}
  const comparable = state.order.filter(id => {const row = state.rows.find(r => r.id === id); return !row.reason && score(row.times, state.originCount);});
  state.rows.forEach(row => {
    let node = nodes.get(row.id); if (!node) {node = makeCourse(row); nodes.set(row.id, node); $('results').append(node.element);}
    node.times.textContent = row.times.map((t, i) => `Golfer ${i + 1}: ${t === null ? row.reason ? 'Unreachable' : 'Pending' : minutes(t)}`).join(' · ');
    const scores = row.reason ? null : score(row.times, state.originCount);
    node.result.textContent = row.reason ? `Unranked: ${row.reason}.`
      : scores ? `${state.phase === 'complete' ? 'Final' : 'Provisional'} score · longest ${minutes(scores.maximum)} · total ${minutes(scores.combined)}${!state.sortPending ? ` · #${comparable.indexOf(row.id) + 1}` : ' · order waiting'}`
      : state.phase === 'error' ? 'Routing error. No comparable score.' : 'Pending: all golfer times are required for a comparable score.';
  });
  if (!state.interactions.size) state.order.forEach((id, i) => {
    const node = nodes.get(id).element, current = $('results').children[i];
    if (node !== current) $('results').insertBefore(node, current || null);
  });
  const mapKey = JSON.stringify([state.areas, state.rows.map(r => r.id), state.committed, state.phase === 'entry']);
  if (mapKey !== lastMapKey) {
    lastMapKey = mapKey; layer.clearLayers(); const points = [];
    state.committed.forEach((p, i) => {if (p) {L.circleMarker(p, {radius: 6, color: '#3874a1'}).bindTooltip(`Golfer ${i + 1}`).addTo(layer); points.push(p);}});
    state.areas.forEach(a => {
      L.circle(a.center, {radius: a.facility_radius_kilometers * 1000, color: '#ad8243', fillOpacity: .10}).addTo(layer);
      L.circleMarker(a.center, {radius: 9, color: '#ad8243'}).bindTooltip('modo ideal area (mock)', {permanent: true}).addTo(layer); points.push(a.center);
    });
    state.rows.forEach(r => {const p = [r.map_location.latitude, r.map_location.longitude]; points.push(p); L.circleMarker(p, {radius: 5, color: '#235d45'}).bindTooltip(r.name).addTo(layer);});
    if (points.length) map.fitBounds(L.latLngBounds(points).pad(.25), {maxZoom: 11, animate: false});
  }
  $('map-note').textContent = state.areas.length ? 'modo ideal area (synthetic). Amber circle: 25 km facility catchment; separate mock search resolution: 3 km. Green: existing catalog facilities.' : 'Local schematic map. No map tiles, location lookup or network geocoding.';
  $('timings').replaceChildren();
  const labels = {localPreparation:'Local preparation', modo:'modo calculation (mock)', areaVisible:'Area visible since Search', candidatesVisible:'Courses visible since Search', firstBatch:'First batch since Search', courseMatrix:'Course matrix wall time', scoring:'Scoring (mock)', complete:'Complete since Search'};
  Object.entries(state.timings).forEach(([key, value]) => {if (value == null) return; const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = labels[key]; dd.textContent = `${(value / 1000).toFixed(2)} s`; $('timings').append(dt, dd);});
}
$('add').onclick = addRow;
$('cancel').onclick = () => {stop(); state.cancel();};
$('plan').onsubmit = e => {
  e.preventDefault();
  // Search consumes prepared state. Only Enter/blur handlers may prepare it.
  if (!state.canStart()) return;
  stop();
  const request = state.start(); if (request) cancelMock = mockSearch(request, event => state.receive(event), {failure: $('failure').checked});
};
document.querySelectorAll('[name=objective]').forEach(input => input.onchange = () => {
  if (state.phase !== 'complete') stop(); state.objectiveChanged(input.value);
});
buildOrigins(); render();
