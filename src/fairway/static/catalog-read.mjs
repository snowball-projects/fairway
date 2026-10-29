// Native read DTOs only. No static-catalog fallback, migration or authority.
export const STYLES = {regulation:'Regulation',executive:'Executive',par_3:'Par3',pitch_and_putt:'Pitch & Putt',putting:'Grass Putting'};
export const recordLabel = (record,kind='facility') => record.name || record.facility_name || `Unnamed golf ${record.record_kind||kind} · ${(record.facility_id||record.course_id).replace(/^osm\//,'OSM ').replaceAll('/',' ')}`;
export const courseMapId = course => course.facility_id ?? course.course_id ?? course.id;
export const mapRecords = catalog => [...catalog.facilities,...catalog.courses.filter(c=>c.facility_id===null).map(c=>({...c,facility_id:c.course_id,record_kind:'course'}))];
export const located = facility => facility.map_location && Number.isFinite(facility.map_location.latitude) && Number.isFinite(facility.map_location.longitude) && Math.abs(facility.map_location.latitude)<=90 && Math.abs(facility.map_location.longitude)<=180;
export const mapEligible = facility => Boolean(facility.facility_id && located(facility) && ['property_point','reviewed_osm_point','verified_entrance'].includes(facility.map_location.kind));
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
    if(`${recordLabel(facility)} ${facility.facility_id} ${city||''} ${facility.state||''}`.toLowerCase().includes(text))found.push({kind:'facility',id:facility.facility_id,label:recordLabel(facility),subtitle:[city,facility.state].filter(Boolean).join(', '),facility});
  }
  return [...found.filter(r=>r.kind==='state'),...cities.values(),...found.filter(r=>r.kind==='facility')];
}
export class CatalogRead {
  constructor({revision,catalog_release_key,facilities,courses,destinations={},indexes}) {
    this.revision=revision;this.catalogReleaseKey=catalog_release_key;
    const lookup=(rows,identity)=>new Map(Object.entries(rows).map(([id,row])=>{row[identity]=id;return [id,row];}));
    this.facilityById=lookup(facilities,'facility_id');
    this.courseById=lookup(courses,'course_id');
    this.destinations=lookup(destinations,'id');
    this.facilities=[...this.facilityById.values()];this.courses=[...this.courseById.values()];
    const entries=[...this.courses,...this.facilities];
    const records=positions=>positions.map(at=>entries[at]);
    const groups=positions=>new Map(positions.map(([id,items])=>[id,records(items)]));
    this.coursesByFacility=new Map(indexes.coursesByFacility.map(([id,items])=>[id,records(items)]));
    this.browseEntries={};this.browseGroups={};this.browseIndependent={};
    for(const sort of ['name','holes']) {
      const browse=indexes.browse[sort];
      this.browseEntries[sort]=records(browse.entries);
      this.browseGroups[sort]=groups(browse.groups);
      this.browseIndependent[sort]=records(browse.independent);
    }
    this.mapRecords=[...this.facilities,...indexes.mapCourses.map(at=>({...this.courses[at],facility_id:this.courses[at].course_id,record_kind:'course'}))];
    this.mapRecordById=new Map(this.mapRecords.map(r=>[r.facility_id,r]));
  }
  facilityCourses(id) {return this.coursesByFacility.get(id)||[];}
  browseGroup(id,sort) {
    const ordered=this.browseGroups[sort].get(id);
    if(ordered)return ordered;
    const courses=this.coursesByFacility.get(id);
    if(courses?.length)return courses;
    const record=this.facilityById.get(id)||this.courseById.get(id);
    return record?[record]:[];
  }
  browseWindow({sort='name',limit=60,matches=()=>true,activeCourse=null,activeFacility=null,focusedGroup=null}={}) {
    const shown=new Set(),groups=[];
    const recordsFor=id=>this.browseGroup(id,sort).filter(matches);
    const include=(id,records)=>{
      if(shown.has(id)||shown.size>=limit||!records.length)return;
      shown.add(id);groups.push(records);
    };
    const selected=this.courseById.get(activeCourse);
    if(selected&&matches(selected))include(courseMapId(selected),recordsFor(courseMapId(selected)));
    if(activeFacility&&!shown.has(activeFacility)) {
      const records=recordsFor(activeFacility);
      if(records.some(r=>r.facility_id===activeFacility))include(activeFacility,records);
    }
    let more=false;
    // Keep selectedFirst's existing null-facility course priority.
    const all=this.browseEntries[sort],sources=activeFacility===null?[this.browseIndependent[sort],all]:[all];
    scan:for(const records of sources)for(const record of records) {
      if(records===all&&activeFacility===null&&record.facility_id===null)continue;
      const id=courseMapId(record);
      if(shown.has(id)||!matches(record))continue;
      if(shown.size<limit)include(id,recordsFor(id));
      else if(id!==focusedGroup){more=true;break scan;}
    }
    if(focusedGroup&&!shown.has(focusedGroup)) {
      const records=recordsFor(focusedGroup);
      if(records.length)groups.push(records);
    }
    const visible=[];
    for(const records of groups) {
      const at=records.findIndex(record=>record.course_id===activeCourse);
      if(at>0)records.unshift(...records.splice(at,1));
      visible.push(...records);
    }
    return {visible,more};
  }
}
export function courseMatches(course,{state='all',access='all',holes='all',roundHoles='all',style='all',facilityIds=null,bounds=null}={}) {
  if(state!=='all' && course.state!==state)return false;
  if(access==='nonmember' ? course.plan_eligible!==true : access==='unknown' ? course.access!==null : access!=='all' && course.access!==access)return false;
  if(holes!=='all' && course.physical_holes!==Number(holes))return false;
  if(roundHoles!=='all' && !(course.round_options||[]).some(r=>r.round_holes===Number(roundHoles)))return false;
  if(style==='putting'&&course.game_kind==='obstacle_minigolf')return false;
  if(style==='unknown' ? Boolean(STYLES[course.style]) : style!=='all' && course.style!==style)return false;
  if(facilityIds && !facilityIds.has(courseMapId(course)))return false;
  if(bounds && (!course.map_location || !bounds.contains([course.map_location.latitude,course.map_location.longitude])))return false;
  return true;
}
export function browseCard(course,destinations) {
  const target=destinations.get(course.destination_id)||null;
  return {id:course.course_id,facility_id:course.facility_id,name:recordLabel(course,'course'),course_name:course.name,
    facility_name:course.facility_name,state:course.state,holes:course.physical_holes,round_options:course.round_options||[],tee_sets:course.tee_sets||[],
    style:course.style,game_kind:course.game_kind,identity_status:course.identity_status,access:accessLabel(course.access),
    access_qualification:course.access_qualification,booking_conditions:course.booking_conditions,nonmember_bookable:course.nonmember_bookable,booking_availability:course.booking_availability,
    plan_eligible:course.plan_eligible,planning_basis:course.planning_basis,optional:course.optional,components:course.components||[],source_course:course,
    address:displayAddress(course.address),website:course.website??course.facility_website,
    coordinate:course.map_location?[course.map_location.latitude,course.map_location.longitude]:null,
    routing_target:target,arrival:course.arrival,destination_kind:target?.precision||null,routing_basis:target?.scope==='facility_estimate'?'approximate_facility_point':target?'reviewed_course_arrival':'arrival_unavailable',
    travel_times_seconds:[],maximum_seconds:null,combined_seconds:null,browseOnly:true};
}
