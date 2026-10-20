// Page-memory preparation only. Transport/admission belongs to the adapter.
export const MAX_PLANNING_COURSES = 24;
export const MAX_PLANNING_ORIGINS = 8;
// Two admitted windows can introduce 48 unique current-operation targets.
// Keep their vectors intact rather than evicting the first completed window.
export const MAX_RETAINED_CELLS = MAX_PLANNING_ORIGINS * MAX_PLANNING_COURSES * 2;
const pointKey = p => JSON.stringify(p);
const validPoint = p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite) && Math.abs(p[0]) <= 90 && Math.abs(p[1]) <= 180;
export function projectCourses(facilities) {
  const result=[];
  for(const facility of facilities) for(const course of facility.courses || []) {
    if(!['public','private','restricted','unknown'].includes(course.access) || !course.id)continue;
    if(course.arrival && (!['reviewed_osm_point','verified_entrance'].includes(course.arrival.kind) ||
      !validPoint([course.arrival.latitude,course.arrival.longitude]) || typeof course.arrival.reference!=='string' || !course.arrival.reference.trim()))continue;
    const arrival=course.arrival && ['reviewed_osm_point','verified_entrance'].includes(course.arrival.kind)
      ? course.arrival : facility.map_location;
    if(!arrival || !['property_point','reviewed_osm_point','verified_entrance'].includes(arrival.kind) || !validPoint([arrival.latitude,arrival.longitude]))continue;
    result.push({...facility,id:course.id,facility_id:facility.id,facility_name:facility.name,
      name:course.name || 'Unnamed documented course',course_name:course.name,holes:course.holes,
      identity_status:'needs_review',
      access:course.access,public_access:course.access,courses:[course],map_location:arrival,
      arrival:course.arrival || null,
      routing_basis:course.arrival ? 'reviewed_course_arrival' : 'approximate_facility_point',
      estimate_qualification:course.arrival ? null : 'Approximate drive to the existing facility point; course arrival unverified',
      address:Object.hasOwn(course,'address') ? course.address : facility.address,source_facility:facility});
  }
  return result;
}
export function distanceKilometers(a, b) {
  const rad = Math.PI / 180, dlat = (b[0] - a[0]) * rad, dlon = (b[1] - a[1]) * rad;
  const h = Math.sin(dlat / 2) ** 2 + Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dlon / 2) ** 2;
  return 12742.0176 * Math.asin(Math.min(1, Math.sqrt(h)));
}
export function nearbyFacilities(catalog, areas, radius, holes, limit = Infinity, accessScope = ['public']) {
  const eligible = catalog.filter(f => accessScope.includes(f.access) && f.map_location &&
    ['property_point','reviewed_osm_point','verified_entrance'].includes(f.map_location.kind) &&
    (holes.length === 2 || holes.includes(f.holes)));
  // Round-robin nearest neighbors per current region prevents one dense origin
  // from consuming the cap. Put the newest area first, while retaining origins.
  const regions=areas.map(a=>eligible.map(f=>({facility:f,distance:distanceKilometers(a.center,
    [f.map_location.latitude,f.map_location.longitude])})).filter(f=>f.distance<=radius)
    .sort((a,b)=>a.distance-b.distance||a.facility.name.localeCompare(b.facility.name)||a.facility.id.localeCompare(b.facility.id)));
  const selected=[],ids=new Set();
  for(let index=0;index<Math.max(0,...regions.map(r=>r.length));index++) for(const region of regions) {
    const f=region[index]?.facility;if(!f || ids.has(f.id))continue;
    selected.push(f);ids.add(f.id);if(selected.length===limit)return selected;
  }
  return selected;
}
export class PlanningSession {
  constructor({adapter, catalog = [], notify = () => {}}) {
    const p = adapter.policy;
    if (!p || !Number.isFinite(p.radiusKilometers) || p.radiusKilometers <= 0 || p.radiusKilometers > 160 ||
        typeof p.identity !== 'string' || !p.identity) throw new Error('Invalid preparation policy');
    this.adapter=adapter;this.policy=p;this.sourceCatalog=catalog;this.catalog=projectCourses(catalog);this.notify=notify;
    this.generation=0;this.origins=[];this.objective='maximum';this.holes=[9,18];
    this.cache=new Map();this.active=null;this.pending=null;this.key=null;this.phase='entry';
    this.radiusKilometers=p.radiusKilometers;
    this.accessScope=['public'];
    this.areas=[];this.candidates=[];this.error=null;this.blocked=false;
    this.operations=0;this.reusedCells=0;
  }
  cellKey(origin, facility) {
    return JSON.stringify([this.policy.identity,origin.id,origin.coordinate,facility.id,
      [facility.map_location.latitude,facility.map_location.longitude]]);
  }
  invalidate(origins = this.origins) {
    this.generation++;this.pending=null;this.key=null;this.origins=origins.map(o=>({...o,coordinate:[...o.coordinate]}));
    this.phase='entry';this.areas=[];this.candidates=[];this.error=null;
    this.prune();this.notify(this);
  }
  update(origins, objective = this.objective, holes = this.holes) {
    if (origins.length > MAX_PLANNING_ORIGINS || origins.some(o=>!o.id || !validPoint(o.coordinate)) ||
        new Set(origins.map(o=>o.id)).size !== origins.length || !['maximum','combined'].includes(objective) ||
        !holes.length || holes.some(h=>![9,18].includes(h))) throw new Error('Invalid planning input');
    const key=JSON.stringify([this.policy.identity,origins.map(o=>[o.id,o.coordinate]),objective,holes,this.radiusKilometers,this.accessScope]);
    if (key===this.key) return false;
    this.invalidate(origins);this.key=key;this.objective=objective;this.holes=[...holes];
    if (!origins.length || this.blocked) {this.notify(this);return false;}
    this.phase=origins.length===1?'matrix':'area';
    const job={generation:this.generation,key,origins:this.origins.map(o=>({...o})),objective,holes:[...holes],radiusKilometers:this.radiusKilometers,accessScope:[...this.accessScope],areas:[],candidates:[],catalog:this.catalog,submittedFacilities:new Map()};
    this.select(job);this.candidates=job.candidates;this.prune();
    this.pending=job;this.notify(this);this.drain();return true;
  }
  setCatalog(catalog) {
    if (catalog===this.sourceCatalog) return;
    this.sourceCatalog=catalog;this.catalog=projectCourses(catalog);this.cache.clear();const origins=this.origins;
    this.key=null;this.update(origins,this.objective,this.holes);
  }
  select(job) {
    const regions=[...job.areas,...job.origins.map(o=>({id:`origin:${o.id}`,center:o.coordinate}))];
    job.candidates=nearbyFacilities(job.catalog,regions,job.radiusKilometers,job.holes,Infinity,job.accessScope);
  }
  radiusChanged(radius) {
    if(!Number.isFinite(radius)||radius<=0||radius>160)throw new Error('Invalid radius');
    if(radius===this.radiusKilometers)return false;
    this.radiusKilometers=radius;return this.update(this.origins,this.objective,this.holes);
  }
  accessChanged(scope) {
    if(!scope.length || scope.some(value=>!['public','private','restricted','unknown'].includes(value)))throw new Error('Invalid access scope');
    this.accessScope=[...scope];return this.update(this.origins,this.objective,this.holes);
  }
  prune() {
    const origins=new Set(this.origins.map(o=>JSON.stringify([o.id,o.coordinate])));
    const targets=this.candidates.length?new Set(this.candidates.map(f=>JSON.stringify([f.id,[f.map_location.latitude,f.map_location.longitude]]))):null;
    for (const [key,cell] of this.cache) if (!origins.has(JSON.stringify([cell.origin.id,cell.origin.coordinate])) ||
      (targets && !targets.has(JSON.stringify([cell.facility.id,[cell.facility.map_location.latitude,cell.facility.map_location.longitude]])))) this.cache.delete(key);
    const protectedKeys = new Set();
    if (this.active) for (const facility of this.active.submittedFacilities.values()) for (const origin of this.active.origins)
      protectedKeys.add(this.cellKey(origin,facility));
    for (const key of this.cache.keys()) {
      if (this.cache.size <= MAX_RETAINED_CELLS) break;
      if (!protectedKeys.has(key)) this.cache.delete(key);
    }
    if (this.cache.size > MAX_RETAINED_CELLS) throw new Error('Admitted result budget exceeded');
  }
  coursePlan(job) {
    // Do not start dependent work for a stale operation. Already dispatched
    // work still owns the slot until the adapter supplies trusted completion.
    if(job.generation!==this.generation)return {facilities:job.candidates,missing:[],origins:job.origins};
    const missing=[];let reused=0;
    // A bounded routing window is not a display or candidate-pool cap.
    // Further windows need coordinated server admission, not an implicit loop.
    for(const facility of job.candidates.slice(0,MAX_PLANNING_COURSES)) for(const origin of job.origins) {
      const key=this.cellKey(origin,facility);
      if(this.cache.has(key)) reused++;else missing.push({origin_id:origin.id,facility_id:facility.id});
      job.submittedFacilities.set(facility.id,facility);
    }
    if(job.submittedFacilities.size>48)throw new Error('Course target budget exceeded');
    this.reusedCells+=reused;
    return {facilities:job.candidates,missing,origins:job.origins};
  }
  receive(job,event) {
    if(this.active!==job) return;
    if(event.type==='area.ready') {
      if(job.generation!==this.generation)return;
      if(job.areaReceived || job.origins.length<2 || !Array.isArray(event.areas) || !event.areas.length || event.areas.length>8 ||
          event.areas.some(a=>!a.id || !validPoint(a.center))) throw new Error('Invalid area result');
      job.areaReceived=true;
      job.areas=event.areas;this.select(job);
      if(job.generation===this.generation) {
        this.areas=event.areas;this.candidates=job.candidates;this.phase='matrix';this.prune();this.notify(this);
      }
    } else if(event.type==='matrix.batch') {
      if(!Array.isArray(event.cells) || event.cells.length>192) throw new Error('Invalid batch');
      const accepted=[],seen=new Set();
      for(const cell of event.cells) {
        const origin=job.origins.find(o=>o.id===cell.origin_id),facility=job.submittedFacilities.get(cell.facility_id) || job.candidates.find(f=>f.id===cell.facility_id);
        if(!origin || !facility || (cell.reason && !['unreachable','outside-road-coverage'].includes(cell.reason)) ||
          (!cell.reason && (!Number.isSafeInteger(cell.milliseconds) || cell.milliseconds<0))) throw new Error('Invalid matrix identity or duration');
        const key=this.cellKey(origin,facility),existing=this.cache.get(key);
        if(seen.has(key) || (existing && (existing.milliseconds!==cell.milliseconds || existing.reason!==cell.reason))) throw new Error('Changed matrix cell');
        seen.add(key);accepted.push({key,origin,facility,milliseconds:cell.reason?null:cell.milliseconds,reason:cell.reason||null});
      }
      for(const cell of accepted) if(job.catalog===this.catalog && this.origins.some(o=>o.id===cell.origin.id && pointKey(o.coordinate)===pointKey(cell.origin.coordinate))) this.cache.set(cell.key,cell);
      this.prune();if(job.generation===this.generation)this.notify(this);
    }
  }
  async drain() {
    if(this.active || !this.pending || this.blocked)return;
    const job=this.pending;this.pending=null;this.active=job;this.operations++;
    let outcome;
    try {
      outcome=await this.adapter.prepare({generation:job.generation,origins:job.origins,objective:job.objective,holes:job.holes,radiusKilometers:job.radiusKilometers,accessScope:job.accessScope},
        event=>this.receive(job,event),()=>this.coursePlan(job));
    } catch {
      // A rejected/disconnected operation has no trusted release evidence.
      outcome={admissionReleased:false,error:{code:'upstream_outcome_unknown',retryable:false}};
    }
    if(outcome?.admissionReleased!==true || outcome.error?.code==='upstream_outcome_unknown') {
      this.blocked=true;this.pending=null;this.error={code:'upstream_outcome_unknown',retryable:false};
      this.phase='error';this.candidates=[];this.cache.clear();
    } else if(job.generation===this.generation) {
      if(outcome.error) {
        this.error={code:outcome.error.code,retryable:outcome.error.retryable===true};this.phase='error';this.cache.clear();
      } else if(this.rows().some(row=>row.times.some(t=>t===null) && !row.reason && job.submittedFacilities.has(row.facility.id))) {
        this.error={code:'incomplete_matrix',retryable:false};this.phase='error';this.cache.clear();
      } else if(this.rows().some(row=>row.times.some(t=>t===null) && !row.reason)) {
        this.phase='partial';
      } else this.phase='complete';
    }
    // Only the adapter's trusted terminal result can release this local slot.
    this.active=null;this.notify(this);this.drain();
  }
  retry() {
    if(this.blocked || this.active || this.pending || !this.error?.retryable)return false;
    const origins=this.origins;this.key=null;return this.update(origins,this.objective,this.holes);
  }
  rows() {
    const rows=this.candidates.map(facility=>{
      const cells=this.origins.map(o=>this.cache.get(this.cellKey(o,facility)));
      const reason=cells.find(c=>c?.reason)?.reason||null;
      const times=cells.map(c=>c && !c.reason?c.milliseconds:null);
      const complete=this.origins.length>=1 && !reason && times.every(t=>Number.isSafeInteger(t)&&t>=0);
      return {facility,times,timeReasons:cells.map(c=>c?.reason || null),reason,maximum:complete?Math.max(...times):null,combined:complete?times.reduce((a,b)=>a+b,0):null};
    });
    const other=this.objective==='maximum'?'combined':'maximum';
    return rows.sort((a,b)=>a.maximum===null?(b.maximum===null?0:1):b.maximum===null?-1:
      a[this.objective]-b[this.objective]||a[other]-b[other]||a.facility.name.localeCompare(b.facility.name)||a.facility.id.localeCompare(b.facility.id));
  }
}
