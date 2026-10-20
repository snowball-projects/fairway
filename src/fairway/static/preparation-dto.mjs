// Clean SQLite preparation DTO consumer. No catalog authority or routing work.
const statuses = new Set(['complete', 'pending', 'unreachable', 'arrival_unavailable', 'error']);
const point = value => value && Number.isFinite(value.latitude) && Number.isFinite(value.longitude) && Math.abs(value.latitude) <= 90 && Math.abs(value.longitude) <= 180;
const milliseconds = value => Number.isSafeInteger(value) && value >= 0;
export const canonicalRequest = value => JSON.stringify(value, (key, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.entries(item).sort(([a],[b]) => a.localeCompare(b))) : item);
export async function preparationRequestKey(request) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonicalRequest(request)));
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2,'0')).join('');
}
export class PreparationPages {
  constructor(generation, request, requestKey) {
    if (!Number.isSafeInteger(generation) || !request || !Array.isArray(request.origins) || !requestKey) throw new Error('Missing preparation request binding');
    this.generation = generation;
    this.request = structuredClone(request);this.requestKey = requestKey;
    this.origins = structuredClone(request.origins);
    this.revision = null;
    this.snapshotSequence = null;
    this.pages = new Map();
    this.summary = null;
    this.areas = null;
  }
  accept(snapshot) {
    if (snapshot.generation !== this.generation) return false;
    if (snapshot.request_key !== this.requestKey || canonicalRequest(snapshot.request) !== canonicalRequest(this.request)) throw new Error('Preparation request mismatch');
    if (!Array.isArray(snapshot.areas) || snapshot.areas.some(area => !Array.isArray(area.center) || area.center.length!==2 || !area.center.every(Number.isFinite) || Math.abs(area.center[0])>90 || Math.abs(area.center[1])>180 || area.geometry?.type!=='Point' || !area.qualification || area.geometry.coordinates[0]!==area.center[1] || area.geometry.coordinates[1]!==area.center[0])) throw new Error('Invalid qualified area geometry');
    if (!Number.isSafeInteger(snapshot.snapshot_sequence) || snapshot.snapshot_sequence < 0 ||
        (this.snapshotSequence !== null && snapshot.snapshot_sequence !== this.snapshotSequence)) throw new Error('Mixed preparation snapshot sequences');
    if (!Number.isSafeInteger(snapshot.catalog_revision) || snapshot.catalog_revision < 0 ||
        !Number.isSafeInteger(snapshot.total) || snapshot.total < 0 ||
        !Number.isSafeInteger(snapshot.offset) || snapshot.offset < 0 ||
        !Number.isSafeInteger(snapshot.limit) || snapshot.limit < 1 || snapshot.limit > 1000 ||
        !Array.isArray(snapshot.courses) || snapshot.courses.length > snapshot.limit ||
        snapshot.offset + snapshot.courses.length > snapshot.total || typeof snapshot.has_more !== 'boolean' ||
        snapshot.has_more !== (snapshot.offset + snapshot.limit < snapshot.total)) throw new Error('Invalid preparation page');
    if (this.revision !== null && snapshot.catalog_revision !== this.revision) throw new Error('Mixed catalog revisions');
    const summary = Object.fromEntries(['total', 'prepared_count', 'pending_count', 'ranking_complete', 'blocked', 'error'].map(key => [key, snapshot[key]]));
    if (!Number.isSafeInteger(summary.prepared_count) || summary.prepared_count < 0 || summary.prepared_count > summary.total ||
        !Number.isSafeInteger(summary.pending_count) || summary.pending_count < 0 || summary.pending_count > summary.total ||
        typeof summary.ranking_complete !== 'boolean' || typeof summary.blocked !== 'boolean' ||
        (summary.ranking_complete && (summary.pending_count || summary.blocked || summary.error))) throw new Error('Invalid preparation summary');
    if (this.summary && JSON.stringify(this.summary) !== JSON.stringify(summary)) throw new Error('Mixed preparation snapshots');
    if (this.areas !== null && canonicalRequest(this.areas) !== canonicalRequest(snapshot.areas)) throw new Error('Mixed immutable area context');
    const rows = snapshot.courses.map(row => this.validateRow(row));
    // A page is immutable within one snapshot read. A later matrix event starts
    // a fresh page collection; offset is never a durable course identity.
    if (this.pages.has(snapshot.offset) && JSON.stringify(this.pages.get(snapshot.offset)) !== JSON.stringify(rows)) throw new Error('Changed preparation page');
    const ids = new Set();
    for (const [offset, page] of this.pages) if (offset !== snapshot.offset) for (const row of page) ids.add(row.course.course_id);
    for (const row of rows) {if (ids.has(row.course.course_id)) throw new Error('Duplicate course across pages');ids.add(row.course.course_id);}
    const candidatePages = new Map(this.pages);candidatePages.set(snapshot.offset,rows);
    const targets = new Map();
    for (const page of candidatePages.values()) for (const row of page) if (row.routing_target) {
      const id=row.routing_target.id,identity=canonicalRequest(row.routing_target);
      if (targets.has(id) && targets.get(id)!==identity) throw new Error('Changed shared routing target');
      targets.set(id,identity);
    }
    let next=0,full=true;
    for (const [offset,page] of [...candidatePages].sort((a,b)=>a[0]-b[0])) {if(offset!==next){full=false;break;}next+=page.length;}
    if (full && next===summary.total) {
      const all=[...candidatePages.values()].flat();
      if (all.filter(row=>row.status==='complete').length!==summary.prepared_count || all.filter(row=>row.status==='pending').length!==summary.pending_count ||
          (summary.ranking_complete && (!all.length || all.some(row=>row.status==='pending'||row.status==='error')))) throw new Error('Preparation summary does not match complete rows');
    }
    this.revision = snapshot.catalog_revision;this.snapshotSequence = snapshot.snapshot_sequence;this.summary = summary;
    this.areas = structuredClone(snapshot.areas);this.pages=candidatePages;
    return true;
  }
  validateRow(row) {
    const course = row.course, target = row.routing_target;
    if (!course || typeof course.course_id !== 'string' || !course.course_id.startsWith('c-') ||
        typeof course.facility_id !== 'string' || !course.facility_id.startsWith('f-') ||
        !(course.name === null || typeof course.name === 'string') || !statuses.has(row.status) ||
        !Array.isArray(row.travel_times_milliseconds) || row.travel_times_milliseconds.length !== this.origins.length ||
        !Array.isArray(row.origin_statuses) || row.origin_statuses.length !== this.origins.length) throw new Error('Invalid course outcome');
    if (course.map_location !== null && !point(course.map_location)) throw new Error('Invalid facility map point');
    if (course.arrival !== null && (!point(course.arrival) || !['reviewed_osm_point', 'verified_entrance'].includes(course.arrival.kind) || !course.arrival.reference)) throw new Error('Invalid canonical course arrival');
    if (target !== null && (!point(target) || target.id !== course.destination_id ||
        !['course_arrival', 'facility_estimate'].includes(target.scope))) throw new Error('Invalid routing target');
    if (target?.scope === 'facility_estimate' && (!target.qualification || course.arrival !== null)) throw new Error('Unqualified facility estimate');
    if (target?.scope === 'course_arrival' && (!course.arrival || target.latitude !== course.arrival.latitude || target.longitude !== course.arrival.longitude || target.precision !== course.arrival.kind || target.reference !== course.arrival.reference)) throw new Error('Arrival target mismatch');
    if (target === null && row.status !== 'arrival_unavailable' && row.status !== 'error') throw new Error('Missing routing target');
    row.travel_times_milliseconds.forEach((value, index) => {
      const status = row.origin_statuses[index];
      if (!statuses.has(status) || (status === 'complete' ? !milliseconds(value) : value !== null)) throw new Error('Invalid origin time');
    });
    const complete = this.origins.length > 0 && target !== null && row.origin_statuses.every(value => value === 'complete');
    if (row.status === 'complete' && !complete) throw new Error('Incomplete comparable score');
    if (row.status === 'complete') {
      const values = row.travel_times_milliseconds;
      if (row.maximum_milliseconds !== Math.max(...values) || row.combined_milliseconds !== values.reduce((a,b) => a+b, 0) || !milliseconds(row.combined_milliseconds)) throw new Error('Invalid comparable score');
    } else if (row.maximum_milliseconds !== null || row.combined_milliseconds !== null) throw new Error('Unscored row has a score');
    return structuredClone(row);
  }
  get completeRead() {
    if (!this.summary) return false;
    let next = 0;
    for (const [offset, rows] of [...this.pages].sort((a,b) => a[0]-b[0])) {if (offset !== next) return false;next += rows.length;}
    return next === this.summary.total;
  }
  rows() {return [...this.pages].sort((a,b) => a[0]-b[0]).flatMap(([,rows]) => rows);}
}

export function preparationCards(collection) {
  return collection.rows().map(row => {
    const c = row.course, target = row.routing_target;
    return {
      id:c.course_id, facility_id:c.facility_id, name:c.name ?? c.facility_name,
      course_name:c.name, facility_name:c.facility_name, state:c.state, holes:c.physical_holes,
      source_course:structuredClone(c),style:c.style,round_options:c.round_options||[],fact_groups:c.fact_groups||[],identity_status:c.identity_status, access:c.access === 'unknown' ? 'Access unconfirmed' : c.access === 'public' ? 'Public play' : c.access === 'private' ? 'Private' : 'Restricted',
      access_qualification:c.access_qualification, planning_basis:c.planning_basis,
      plan_eligible:c.plan_eligible, nonmember_bookable:c.nonmember_bookable, booking_availability:c.booking_availability,
      address:c.address?.text ?? 'Address not documented', website:c.website ?? c.facility_website,
      coordinate:c.map_location ? [c.map_location.latitude,c.map_location.longitude] : null,
      arrival:c.arrival, routing_target:target,
      destination_kind:target?.precision ?? null,
      routing_basis:target?.scope === 'facility_estimate' ? 'approximate_facility_point' : target ? 'reviewed_course_arrival' : 'arrival_unavailable',
      travel_times_seconds:row.travel_times_milliseconds.map(value => value === null ? null : value/1000),
      travel_time_reasons:row.origin_statuses.map(status => status === 'unreachable' ? 'unreachable' : status === 'arrival_unavailable' ? 'arrival_unavailable' : status === 'error' ? 'error' : null),
      maximum_seconds:row.maximum_milliseconds === null ? null : row.maximum_milliseconds/1000,
      combined_seconds:row.combined_milliseconds === null ? null : row.combined_milliseconds/1000,
      reason:row.status === 'complete' || row.status === 'pending' ? null : row.status,
      status:row.status, rank:null,
    };
  });
}
