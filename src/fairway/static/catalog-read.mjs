// Native read DTOs only. No static-catalog fallback, migration or authority.
export const STYLES = {regulation:'Regulation',executive:'Executive',par_3:'Par3',pitch_and_putt:'Pitch & Putt',putting:'Grass Putting'};
export const located = facility => facility.map_location && Number.isFinite(facility.map_location.latitude) && Number.isFinite(facility.map_location.longitude) && Math.abs(facility.map_location.latitude)<=90 && Math.abs(facility.map_location.longitude)<=180;
export const mapEligible = facility => Boolean(facility.facility_id && facility.name && located(facility) && ['property_point','reviewed_osm_point','verified_entrance'].includes(facility.map_location.kind));
export const catalogCounts = facilities => ({total:facilities.length,onMap:facilities.filter(mapEligible).length,pending:facilities.filter(f=>!mapEligible(f)).length});
export const cityLabel = facility => facility.address?.city ?? null;
export const accessLabel = value => value==='public'?'Public play':value==='private'?'Private':value==='restricted'?'Restricted':'Access unconfirmed';
export const displayAddress = value => value?.text ?? ([value?.street_line1,value?.street_line2,[value?.city,value?.region,value?.postal_code].filter(x=>x!==null&&x!==undefined).join(', '),value?.country].filter(Boolean).join(', ') || 'Address not recorded');
export function searchCatalog(facilities,states,query) {
  const text=query.trim().toLowerCase();if(!text)return [];
  const found=states.filter(s=>s.id.toLowerCase()===text || s.name.toLowerCase().includes(text)).map(s=>({kind:'state',id:s.id,label:`${s.name} (${s.id})`,state:s}));
  const cities=new Map();
  for(const facility of facilities) {
    const city=cityLabel(facility),label=city?[city,facility.state].filter(Boolean).join(", "):null;
    if(label?.toLowerCase().includes(text)){const group=cities.get(label)||{kind:'city',label,records:[]};group.records.push(facility);cities.set(label,group);}
    if(`${facility.name} ${city||''} ${facility.state||''}`.toLowerCase().includes(text))found.push({kind:'facility',id:facility.facility_id,label:facility.name,subtitle:[city,facility.state].filter(Boolean).join(', '),facility});
  }
  return [...found.filter(r=>r.kind==='state'),...cities.values(),...found.filter(r=>r.kind==='facility')];
}
export class CatalogRead {
  constructor({revision,facilities,courses,destinations=[],qualification=null}) {
    if(!Number.isSafeInteger(revision)||revision<0 || !Array.isArray(facilities)||!Array.isArray(courses)||!Array.isArray(destinations))throw new Error('Invalid native catalog read');
    this.revision=revision;this.facilities=structuredClone(facilities);this.courses=structuredClone(courses);this.destinations=new Map(destinations.map(d=>[d.id,structuredClone(d)]));this.qualification=qualification;
    this.facilityById=new Map();this.courseById=new Map();
    for(const f of this.facilities){if(!f.facility_id?.startsWith('f-')||this.facilityById.has(f.facility_id))throw new Error('Invalid facility identity');this.facilityById.set(f.facility_id,f);}
    for(const c of this.courses){
      if(!c.course_id?.startsWith('c-')||this.courseById.has(c.course_id)||!this.facilityById.has(c.facility_id)||!(c.name===null||typeof c.name==='string') || ![true,false,null].includes(c.nonmember_bookable))throw new Error('Invalid course identity');
      const target=this.destinations.get(c.destination_id);
      if(c.destination_id!==null && (!target || !Number.isFinite(target.latitude)||!Number.isFinite(target.longitude)||Math.abs(target.latitude)>90||Math.abs(target.longitude)>180||!['facility_estimate','course_arrival'].includes(target.scope)))throw new Error('Invalid course destination');
      if(target?.scope==='facility_estimate'&&(!target.qualification||c.arrival!==null))throw new Error('Unqualified facility estimate');
      if(c.arrival!==null && (!c.arrival || !Number.isFinite(c.arrival.latitude)||!Number.isFinite(c.arrival.longitude)||!['reviewed_osm_point','verified_entrance'].includes(c.arrival.kind)||!c.arrival.reference))throw new Error('Invalid canonical arrival');
      if(target?.scope==='course_arrival' && (!c.arrival||c.arrival.latitude!==target.latitude||c.arrival.longitude!==target.longitude||c.arrival.kind!==target.precision||c.arrival.reference!==target.reference))throw new Error('Changed canonical arrival');
      this.courseById.set(c.course_id,c);
    }
  }
  facilityCourses(id) {return this.courses.filter(c=>c.facility_id===id);}
}
export function courseMatches(course,{state='all',access='all',holes='all',roundHoles='all',style='all',facilityIds=null,bounds=null}={}) {
  if(state!=='all' && course.state!==state)return false;
  if(access==='nonmember' ? course.plan_eligible!==true : access==='unknown' ? course.access!==null : access!=='all' && course.access!==access)return false;
  if(holes!=='all' && course.physical_holes!==Number(holes))return false;
  if(roundHoles!=='all' && !(course.round_options||[]).some(r=>r.round_holes===Number(roundHoles)))return false;
  if(style==='putting'&&course.game_kind==='obstacle_minigolf')return false;
  if(style==='unknown' ? Boolean(STYLES[course.style]) : style!=='all' && course.style!==style)return false;
  if(facilityIds && !facilityIds.has(course.facility_id))return false;
  if(bounds && (!course.map_location || !bounds.contains([course.map_location.latitude,course.map_location.longitude])))return false;
  return true;
}
export function sortCourses(courses,sort='name') {
  const value=c=>sort==='holes'?(Number.isFinite(c.physical_holes)?c.physical_holes:null):null;
  const label=c=>c.name ?? c.facility_name;
  return [...courses].sort((a,b)=>{
    if(sort==='name')return label(a).localeCompare(label(b)) || a.course_id.localeCompare(b.course_id);
    const av=value(a),bv=value(b);return av===null?(bv===null?label(a).localeCompare(label(b)):1):bv===null?-1:av-bv||label(a).localeCompare(label(b));
  });
}
export function browseCard(course,destinations) {
  const target=destinations.get(course.destination_id)||null;
  return {id:course.course_id,facility_id:course.facility_id,name:course.name??course.facility_name,course_name:course.name,
    facility_name:course.facility_name,state:course.state,holes:course.physical_holes,round_options:course.round_options||[],tee_sets:course.tee_sets||[],
    style:course.style,game_kind:course.game_kind,identity_status:course.identity_status,access:accessLabel(course.access),
    access_qualification:course.access_qualification,booking_conditions:course.booking_conditions,nonmember_bookable:course.nonmember_bookable,booking_availability:course.booking_availability,
    plan_eligible:course.plan_eligible,planning_basis:course.planning_basis,optional:course.optional,components:course.components||[],source_course:course,
    address:displayAddress(course.address),website:course.website??course.facility_website,
    coordinate:course.map_location?[course.map_location.latitude,course.map_location.longitude]:null,
    routing_target:target,arrival:course.arrival,destination_kind:target?.precision||null,routing_basis:target?.scope==='facility_estimate'?'approximate_facility_point':target?'reviewed_course_arrival':'arrival_unavailable',
    travel_times_seconds:[],maximum_seconds:null,combined_seconds:null,browseOnly:true};
}
