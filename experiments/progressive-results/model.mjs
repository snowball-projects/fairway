// Local-only lifecycle. This module has no transport, storage or geocoder.
export function parseOrigin(text) {
  if (!/^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$/.test(text)) return null;
  const point = text.split(',').map(Number);
  return point.every(Number.isFinite) && point[0] >= 24.396308 &&
    point[0] <= 49.384358 && point[1] >= -124.848974 && point[1] <= -66.885444
    ? point : null;
}
export function score(times, count) {
  if (times.length !== count || times.some(t => !Number.isSafeInteger(t) || t < 0)) return null;
  const combined = times.reduce((a, b) => a + b, 0);
  return Number.isSafeInteger(combined) ? {maximum: Math.max(...times), combined} : null;
}
export function sortedIds(rows, objective, count) {
  const other = objective === 'maximum' ? 'combined' : 'maximum';
  return [...rows].sort((a, b) => {
    const sa = score(a.times, count), sb = score(b.times, count);
    if (sa && sb) return sa[objective] - sb[objective] || sa[other] - sb[other] ||
      (a.name < b.name ? -1 : a.name > b.name ? 1 : 0) ||
      (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    return sa ? -1 : sb ? 1 : 0;
  }).map(row => row.id);
}
export class ProgressiveSearch {
  constructor({prepare, notify = () => {}, now = () => performance.now()}) {
    this.prepare = prepare; this.notify = notify; this.now = now;
    this.generation = 0; this.preparations = 0; this.searches = 0;
    this.upstreamOutcomeUnknown = false;
    this.texts = ['', '']; this.committed = [null, null];
    this.cacheKey = null; this.prepared = null; this.objective = 'maximum';
    this.reset();
  }
  reset() {
    this.phase = 'entry'; this.rows = []; this.order = []; this.areas = [];
    this.timings = {}; this.sequence = 0; this.searchKey = null; this.areaObjective = null;
    this.interactions = new Set(); this.sortPending = false; this.error = null;
    this.errorCode = null; this.errorRetryable = false;
  }
  invalidate() {
    this.generation++; this.reset(); this.notify();
  }
  edit(index, text) {
    if (this.texts[index] === text) return;
    this.texts[index] = text;
    this.committed[index] = null;
    // Invalidate immediately; no timer, preparation or request on input.
    this.invalidate();
  }
  commit(index) {
    const point = parseOrigin(this.texts[index]);
    if (!point) { this.committed[index] = null; this.notify(); return false; }
    this.committed[index] = point;
    const key = this.key();
    if (key && key !== this.cacheKey) {
      const start = this.now();
      this.prepared = this.prepare(this.committed.map(p => [...p]));
      this.preparationDuration = this.now() - start;
      this.timings.localPreparation = this.preparationDuration;
      this.cacheKey = key; this.preparations++;
    }
    this.notify(); return true;
  }
  key() {
    if (this.texts.length < 2 || this.texts.length > 8) return null;
    const points = this.texts.map(parseOrigin);
    if (points.some((p, i) => !p || JSON.stringify(p) !== JSON.stringify(this.committed[i]))) return null;
    return JSON.stringify(points);
  }
  canStart() {
    const key = this.key();
    if (!key || key !== this.cacheKey || this.upstreamOutcomeUnknown ||
        ['area', 'shortlist', 'matrix'].includes(this.phase)) return false;
    if (this.phase === 'error') return this.errorRetryable;
    if (this.phase === 'complete') return this.areaObjective !== this.objective;
    return this.phase === 'entry' || this.phase === 'cancelled';
  }
  start() {
    if (!this.canStart()) return null;
    const key = this.key();
    const localPreparation = this.preparationDuration;
    this.invalidate(); this.phase = 'area'; this.searchKey = key;
    this.areaObjective = this.objective; this.originCount = this.committed.length;
    this.started = this.now(); this.timings.localPreparation = localPreparation;
    this.searches++; this.notify();
    return {generation: this.generation, origins: this.committed.map(p => [...p]), objective: this.objective, holes: [9, 18]};
  }
  receive(event) {
    if (event.generation !== this.generation || !this.searchKey ||
        ['complete', 'error', 'cancelled'].includes(this.phase)) return false;
    if (!Number.isInteger(event.sequence) || event.sequence <= this.sequence) return false;
    this.sequence = event.sequence;
    const elapsed = this.now() - this.started;
    if (event.type === 'area.ready' && this.phase === 'area') {
      this.areas = event.areas; this.timings.areaVisible = elapsed;
      this.timings.modo = event.duration_ms; this.phase = 'shortlist';
    } else if (event.type === 'candidates.ready' && this.phase === 'shortlist') {
      if (!event.facilities.length || event.facilities.length > 24 ||
          new Set(event.facilities.map(f => f.id)).size !== event.facilities.length) return this.fail('Invalid candidate identities.');
      this.rows = event.facilities.map(f => ({...f, times: Array(this.originCount).fill(null), reason: null}));
      this.order = this.rows.map(r => r.id); this.phase = 'matrix';
      this.timings.candidatesVisible = elapsed; this.matrixStarted = this.now();
    } else if (event.type === 'matrix.batch' && this.phase === 'matrix') {
      // Validate the entire batch before accepting any cells.
      const seen = new Set();
      for (const result of event.destinations) {
        if (seen.has(result.id) || !this.rows.some(r => r.id === result.id) ||
            result.times.length !== this.originCount || result.times.some(t => t !== null && (!Number.isSafeInteger(t) || t < 0)) ||
            (result.reason && !['unreachable', 'outside-road-coverage'].includes(result.reason))) return this.fail('Invalid matrix batch.');
        seen.add(result.id);
      }
      for (const result of event.destinations) {
        const row = this.rows.find(r => r.id === result.id);
        if (row.reason || row.times.some((t, i) => t !== null && t !== result.times[i])) return this.fail('Matrix identity changed.');
        row.times = [...result.times]; row.reason = result.reason || null;
      }
      this.timings.firstBatch ??= elapsed;
      this.reorder();
    } else if (event.type === 'search.complete' && this.phase === 'matrix') {
      if (this.rows.some(r => !r.reason && !score(r.times, this.originCount))) return this.fail('Incomplete matrix; no final ranking.');
      if (!this.rows.some(r => !r.reason)) return this.fail('No facility reachable by every golfer.');
      this.phase = 'complete'; this.timings.courseMatrix = this.now() - this.matrixStarted;
      this.timings.scoring = event.scoring_ms; this.timings.complete = elapsed; this.reorder();
    } else if (event.type === 'search.error') {
      const error = event.error;
      return this.fail(error?.code === 'upstream_outcome_unknown'
        ? 'Upstream outcome unknown. Operator reconciliation required; new searches remain blocked.'
        : 'Routing unavailable. No final ranking.', {
        code: typeof error?.code === 'string' ? error.code : 'routing_error',
        retryable: error?.retryable === true,
      });
    } else return false;
    this.notify(); return true;
  }
  fail(message, {code = 'contract_error', retryable = false} = {}) {
    this.phase = 'error'; this.error = message; this.errorCode = code;
    if (code === 'upstream_outcome_unknown') this.upstreamOutcomeUnknown = true;
    this.errorRetryable = retryable === true && !this.upstreamOutcomeUnknown;
    // Keep context/times visible, revoke every comparable score on provider error.
    this.rows.forEach(row => { row.times = Array(this.originCount).fill(null); });
    this.notify(); return false;
  }
  reorder() {
    const desired = sortedIds(this.rows.filter(r => !r.reason), this.objective, this.originCount)
      .concat(this.rows.filter(r => r.reason).map(r => r.id));
    this.sortPending = JSON.stringify(desired) !== JSON.stringify(this.order);
    if (!this.interactions.size) { this.order = desired; this.sortPending = false; }
  }
  interact(id, active, kind = 'focus') {
    const key = `${kind}:${id}`;
    if (active) this.interactions.add(key); else this.interactions.delete(key);
    this.reorder(); this.notify();
  }
  transferFocus(from, to) {
    // Hold the destination before releasing the source during native focusout.
    // No intermediate empty focus set may reorder the next keyboard target.
    if (to) this.interactions.add(`focus:${to}`);
    this.interactions.delete(`focus:${from}`);
    this.reorder(); this.notify();
  }
  objectiveChanged(objective) {
    this.objective = objective;
    if (this.phase === 'complete') this.reorder();
    else if (this.searchKey) this.invalidate();
    this.notify();
  }
  cancel() { this.generation++; this.phase = 'cancelled'; this.searchKey = null; this.notify(); }
}
