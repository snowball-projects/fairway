import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import pinned from './fixtures/progressive-catalog-pinned.json' with {type:'json'};
import catalog from './fixtures/plan-a-round-catalog-pinned.json' with {type:'json'};
import {PlanningSession,nearbyFacilities,projectCourses,MAX_PLANNING_COURSES} from '../src/fairway/static/planning-session.mjs';
const origin=(id,index)=>({id,coordinate:[pinned.facilities[index].map_location.latitude,pinned.facilities[index].map_location.longitude]});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(initialCatalog = catalog.facilities) {
  const jobs=[];let active=0,maxActive=0;
  const adapter={policy:{identity:'mock-pinned',radiusKilometers:32.18688},prepare(request,emit,coursePlan) {
    active++;maxActive=Math.max(maxActive,active);
    return new Promise(resolve=>jobs.push({request,emit,coursePlan,finish:outcome=>{active--;resolve(outcome||{admissionReleased:true});}}));
  }};
  const state=new PlanningSession({adapter,catalog:initialCatalog});
  const fill=job=>{const p=job.coursePlan();job.emit({type:'matrix.batch',cells:p.missing.map((c,i)=>({...c,milliseconds:(i+1)*60000}))});};
  return {state,jobs,fill,maxActive:()=>maxActive};
}
test('first committed origin reveals nearby candidates immediately and ranks only completed single-driver times',async()=>{
  const {state,jobs,fill}=fixture();state.update([origin('one',0)]);
  assert.ok(state.candidates.length);assert.ok(state.rows().every(r=>r.maximum===null));
  fill(jobs[0]);assert.ok(state.rows().every(r=>r.maximum!==null));jobs[0].finish();await tick();assert.equal(state.phase,'complete');
  assert.equal(state.update([origin('one',0)]),false);assert.equal(jobs.length,1);
});
test('added origins invalidate group scores, coalesce latest work and reuse only compatible completed cells',async()=>{
  const {state,jobs,fill,maxActive}=fixture();const a=origin('one',0),b=origin('two',1),c=origin('three',2);
  state.update([a]);fill(jobs[0]);state.update([a,b]);assert.ok(state.rows().every(r=>r.maximum===null));
  state.update([a,b,c]);assert.equal(jobs.length,1);assert.equal(state.pending.origins.length,3);
  jobs[0].finish();await tick();assert.equal(jobs.length,2);assert.equal(jobs[1].request.origins.length,3);
  assert.equal(maxActive(),1);assert.ok(jobs[1].coursePlan().missing.length<3*state.candidates.length);
  fill(jobs[1]);jobs[1].finish();await tick();assert.equal(state.phase,'complete');assert.ok(state.reusedCells>0);
});
test('keystroke invalidation never starts work; stale area events never replace the current generation',async()=>{
  const {state,jobs,fill}=fixture();state.update([origin('one',0),origin('two',1)]);
  state.invalidate([origin('two',1)]);const count=jobs.length;
  jobs[0].emit({type:'area.ready',areas:[{id:'old',center:[42,-88]}]});fill(jobs[0]);jobs[0].finish();await tick();
  assert.equal(jobs.length,count);assert.deepEqual(state.areas,[]);assert.equal(state.origins.length,1);
});
test('current origin regions plus latest area are deduplicated/capped; obsolete area regions do not accumulate',async()=>{
  const {state,jobs}=fixture();state.update([origin('one',0),origin('two',1)]);
  jobs[0].emit({type:'area.ready',areas:[{id:'latest',center:[42.04,-87.94]}]});
  assert.equal(new Set(state.candidates.map(f=>f.id)).size,state.candidates.length);assert.ok(state.candidates.length<=24);
  state.update([origin('one',0),origin('two',1),origin('three',2)]);assert.deepEqual(state.areas,[]);
  jobs[0].emit({type:'area.ready',areas:[{id:'obsolete',center:[41,-90]}]});assert.deepEqual(state.areas,[]);
  jobs[0].finish();await tick();jobs[1].emit({type:'area.ready',areas:[{id:'new',center:[42.01,-87.95]}]});assert.equal(state.areas[0].id,'new');
});
test('removal automatically prepares the current group without any textbox ritual',async()=>{
  const {state,jobs,fill}=fixture();const origins=[origin('one',0),origin('two',1),origin('three',2)];
  state.update(origins);fill(jobs[0]);jobs[0].finish();await tick();state.update(origins.slice(0,2));
  assert.equal(jobs.length,2);assert.equal(jobs[1].request.origins.length,2);assert.ok(jobs[1].coursePlan().missing.length<12);
});
test('radius updates target selection coherently and completed matrix values are reused across objective changes',async()=>{
  const {state,jobs,fill}=fixture();const origins=[origin('one',0)];state.update(origins);fill(jobs[0]);jobs[0].finish();await tick();
  const before=state.candidates.length;state.radiusChanged(1);assert.ok(state.candidates.length<=before);assert.ok(state.cache.size<=8*24);
  fill(jobs[1]);jobs[1].finish();await tick();state.update(origins,'combined');assert.equal(jobs[2].request.objective,'combined');assert.equal(jobs[2].coursePlan().missing.length,0);
});
test('unknown upstream outcome blocks pending/new commits and retries regardless of changed inputs',async()=>{
  const {state,jobs}=fixture();state.update([origin('one',0)]);state.update([origin('one',0),origin('two',1)]);
  jobs[0].finish({admissionReleased:false,error:{code:'upstream_outcome_unknown',retryable:false}});await tick();
  assert.equal(state.blocked,true);assert.equal(state.pending,null);assert.equal(state.retry(),false);
  state.update([origin('one',0),origin('two',1),origin('three',2)]);assert.equal(jobs.length,1);assert.equal(state.cache.size,0);
});
test('explicit retryable errors permit one retry with unchanged origins and never trigger automatic retry',async()=>{
  const {state,jobs}=fixture();state.update([origin('one',0)]);jobs[0].finish({admissionReleased:true,error:{code:'mock_retryable',retryable:true}});await tick();
  assert.equal(jobs.length,1);assert.equal(state.retry(),true);assert.equal(jobs.length,2);assert.equal(state.retry(),false);
});
test('missing/unreachable cannot become zero; exact zero is valid; changed matrix identity fails',()=>{
  const {state,jobs}=fixture();state.update([origin('one',0)]);const plan=jobs[0].coursePlan();const f=plan.facilities[0];
  jobs[0].emit({type:'matrix.batch',cells:[{origin_id:'one',facility_id:f.id,milliseconds:0}]});assert.equal(state.rows().find(r=>r.facility.id===f.id).maximum,0);
  assert.throws(()=>jobs[0].emit({type:'matrix.batch',cells:[{origin_id:'foreign',facility_id:f.id,milliseconds:0}]}));
  assert.ok(state.rows().some(r=>r.maximum===null));
  const unavailable=plan.facilities[1];jobs[0].emit({type:'matrix.batch',cells:[{origin_id:'one',facility_id:unavailable.id,reason:'unreachable'}]});
  const row=state.rows().find(r=>r.facility.id===unavailable.id);assert.equal(row.maximum,null);assert.deepEqual(row.times,[null]);assert.deepEqual(row.timeReasons,['unreachable']);
});
test('public scope and 9/18 layout evidence never use physical totals; display retains the whole neighborhood',()=>{
  assert.deepEqual(nearbyFacilities(pinned.facilities,[{center:[42,-88]}],160,[18]),[]);
  const source=projectCourses(catalog.facilities)[0], records=Array.from({length:100},(_,i)=>({...source,id:`public-${i}`}));
  records.push({...source,id:'private',access:'private',public_access:'private',courses:[{holes:18,access:'private'}]});
  const result=nearbyFacilities(records,[{center:[42,-88]}],160,[9,18]);assert.equal(result.length,100);assert.ok(result.every(f=>f.public_access==='public'));
});

test('course 25 onward remains visible and pending after a bounded routing window',async()=>{
  const {state,jobs,fill}=fixture();const source=catalog.facilities[0];
  state.setCatalog([{...source,courses:Array.from({length:100},(_,i)=>({...source.courses[0],id:`c-window-${i}`}))}]);
  state.update([{id:'one',coordinate:[source.map_location.latitude,source.map_location.longitude]}]);
  assert.equal(state.candidates.length,100);assert.equal(jobs[0].coursePlan().missing.length,MAX_PLANNING_COURSES);
  fill(jobs[0]);jobs[0].finish();await tick();assert.equal(state.phase,'partial');
  assert.equal(state.rows().length,100);assert.equal(state.rows().filter(r=>r.maximum!==null).length,24);
  assert.equal(state.rows().filter(r=>r.maximum===null).length,76);assert.equal(jobs.length,1);
});

test('course projection preserves actual components, explicit arrivals and unknown names without inventing courses from totals',()=>{
  assert.deepEqual(projectCourses(pinned.facilities),[]);
  const rows=projectCourses(catalog.facilities);assert.ok(rows.every(c=>c.id.startsWith('c-') && c.facility_id.startsWith('f-')));
  const multi=catalog.facilities.at(-1),components=rows.filter(c=>c.facility_id===multi.id);
  assert.ok(components.length>=2);assert.ok(components.every(c=>c.holes===18));assert.equal(new Set(components.map(c=>c.id)).size,components.length);
  assert.ok(rows.some(c=>c.course_name===null && c.name==='Unnamed documented course'));
  assert.ok(rows.filter(c=>c.routing_basis==='reviewed_course_arrival').every(c=>c.arrival?.kind==='reviewed_osm_point'));
  assert.ok(rows.filter(c=>c.routing_basis==='approximate_facility_point').every(c=>c.arrival===null && c.estimate_qualification));
});
test('private and restricted components remain browse identities; planning only includes them by explicit access selection',()=>{
  const f=catalog.facilities[0],c=f.courses[0];
  const source={...f,courses:[c,{...c,id:'c-private-test',name:'Private component',access:'private'},{...c,id:'c-restricted-test',access:'restricted'}]};
  const rows=projectCourses([source]);assert.equal(rows.length,3);
  const areas=[{center:[f.map_location.latitude,f.map_location.longitude]}];
  assert.equal(nearbyFacilities(rows,areas,10,[9,18]).length,1);
  assert.deepEqual(nearbyFacilities(rows,areas,10,[9,18],24,['private']).map(c=>c.id),['c-private-test']);
  assert.equal(nearbyFacilities(rows,areas,10,[9,18],24,['restricted'])[0].access,'restricted');
});
test('catalog replacement prevents an old operation from reusing its source-bound cells',async()=>{
  const {state,jobs}=fixture();state.update([origin('one',0)]);const old=jobs[0].coursePlan(),cell=old.missing[0];
  state.setCatalog(catalog.facilities.map(f=>({...f})));jobs[0].emit({type:'matrix.batch',cells:[{...cell,milliseconds:1000}]});
  assert.equal(state.cache.size,0);jobs[0].finish();await tick();assert.equal(jobs.length,2);
});
test('explicit null address suppresses inheritance and property estimates never become canonical arrivals',()=>{
  const f=catalog.facilities.at(-1),c=f.courses[0];
  const [row]=projectCourses([{...f,courses:[{...c,address:null,arrival:null}]}]);
  assert.equal(row.address,null);assert.equal(row.arrival,null);assert.equal(row.routing_basis,'approximate_facility_point');
  assert.equal(projectCourses([{...f,courses:[{...c,arrival:{latitude:42,longitude:-88,kind:'reviewed_osm_point',reference:''}}]}]).length,0);
});

test('eight-origin second window preserves all completed admitted vectors in the actual LA pool',async()=>{
  const national=JSON.parse(readFileSync(new URL('./fixtures/historical-la-window.json',import.meta.url))).facilities;
  const {state,jobs,fill}=fixture(national);state.update(Array.from({length:8},(_,i)=>({id:`origin-${i}`,coordinate:[34.05,-118.25]})));
  const job=jobs[0],initial=job.coursePlan();assert.equal(initial.missing.length,192);fill(job);
  const first=new Set(state.rows().filter(r=>r.maximum!==null).map(r=>r.facility.id));assert.equal(first.size,24);
  job.emit({type:'area.ready',areas:[{id:'review-mock-area',center:[34.05,-118.45]}]});
  assert.equal(job.coursePlan().missing.length,32);fill(job);job.finish();await tick();
  assert.equal(state.error,null);assert.equal(state.phase,'partial');assert.ok(state.cache.size<=384);
  assert.ok([...first].every(id=>state.rows().find(r=>r.facility.id===id)?.maximum!==null));
  assert.equal(state.rows().filter(r=>r.maximum!==null).length,28);
});
