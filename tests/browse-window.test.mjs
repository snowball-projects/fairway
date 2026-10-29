import test from 'node:test';
import assert from 'node:assert/strict';
import {CatalogRead,courseMapId,courseMatches} from '../src/fairway/static/catalog-read.mjs';
const identity=r=>r.course_id??r.facility_id;
function model() {
 const facilities=[],courses=[];
 for(let i=0;i<100;i++) {
  const id=`f-${i}`,point={latitude:35+i%12,longitude:-100+i%25};
  facilities.push({facility_id:id,name:i%9?`Facility ${i}`:null,state:i%2?'IL':'WI',physical_holes:i%3?18:9,access:i%4?'public':null,map_location:i%17?point:null});
  if(i%3===0)for(let j=0;j<2+i%4;j++)courses.push({course_id:`c-${i}-${j}`,facility_id:id,name:`${j%2?'Z':'A'} ${i}-${j}`,state:i%2?'IL':'WI',physical_holes:j%2?18:9,access:i%4?'public':null,map_location:{latitude:point.latitude+j*.1,longitude:point.longitude},round_options:[]});
 }
 for(let i=0;i<15;i++)courses.push({course_id:`independent-${i}`,facility_id:null,name:`Independent ${i}`,state:'IL',physical_holes:9,access:'public',map_location:{latitude:40,longitude:-90+i},round_options:[]});
 return new CatalogRead({revision:1,facilities,courses});
}
function fullReference(model,{sort,limit,matches,activeCourse,activeFacility,focusedGroup}) {
 const entries=model.browseEntries[sort].filter(matches);
 const ordered=[...entries].sort((a,b)=>Number(identity(b)===activeCourse)-Number(identity(a)===activeCourse)||Number(b.facility_id===activeFacility)-Number(a.facility_id===activeFacility));
 const shown=new Set([...new Set(ordered.map(courseMapId))].slice(0,limit));
 if(focusedGroup)shown.add(focusedGroup);
 const visible=ordered.filter(r=>shown.has(courseMapId(r))),groups=new Map();
 for(const r of visible){const id=courseMapId(r),group=groups.get(id)||[];group.push(r);groups.set(id,group);}
 return {visible:[...groups.values()].flat(),more:entries.length>visible.length};
}
test('bounded windows match complete-list ordering, filtering, promotions, focus and sibling groups',()=>{
 const m=model(),before=Object.fromEntries(Object.entries(m.browseEntries).map(([sort,records])=>[sort,records.map(identity)]));
 let seed=1931;const next=n=>(seed=(1664525*seed+1013904223)>>>0)%n;
 for(let run=0;run<500;run++) {
  const sort=next(2)?'name':'holes',limit=1+next(12),activeFacility=next(3)?null:`f-${next(100)}`;
  const activeCourse=next(3)?null:m.courses[next(m.courses.length)].course_id;
  const focusedGroup=next(2)?null:courseMapId(m.browseEntries.name[next(m.browseEntries.name.length)]);
  const filters={state:['all','IL','WI'][next(3)],holes:['all','9','18'][next(3)],access:['all','public','unknown'][next(3)]};
  const west=-101+next(20),south=34+next(9),bounds={contains:p=>p[0]>=south&&p[0]<=south+5&&p[1]>=west&&p[1]<=west+12};
  const facility=m.facilityById.get(activeFacility),selectedVisible=facility?.map_location&&bounds.contains([facility.map_location.latitude,facility.map_location.longitude]);
  const matches=r=>courseMatches(r,{...filters,bounds:selectedVisible&&r.course_id&&courseMapId(r)===activeFacility?null:bounds});
  const options={sort,limit,matches,activeCourse,activeFacility,focusedGroup},expected=fullReference(m,options),actual=m.browseWindow(options);
  assert.deepEqual(actual.visible.map(identity),expected.visible.map(identity),`records ${run} ${JSON.stringify({sort,limit,activeFacility,activeCourse,focusedGroup,filters,west,south})}`);assert.equal(actual.more,expected.more,`more ${run}`);
 }
 for(const [sort,records]of Object.entries(m.browseEntries))assert.deepEqual(records.map(identity),before[sort]);
});
test('national window stops after the needed groups without whole-list filtering or copying',()=>{
 const facilities=Array.from({length:10000},(_,i)=>({facility_id:`f-${i}`,name:`Facility ${String(i).padStart(5,'0')}`,physical_holes:18}));
 const m=new CatalogRead({revision:1,facilities,courses:[]});
 for(const operation of ['filter','map','slice','sort'])m.browseEntries.name[operation]=()=>assert.fail(`whole-list ${operation}`);
 let checked=0;const result=m.browseWindow({matches:()=>{checked++;return true;}});
 assert.equal(result.visible.length,60);assert.equal(result.more,true);assert.ok(checked<=125,`checked ${checked}`);
});
test('a held final group is complete without a redundant Show more button',()=>{
 const facilities=Array.from({length:61},(_,i)=>({facility_id:`f-${i}`,name:`Facility ${String(i).padStart(3,'0')}`}));
 const m=new CatalogRead({revision:1,facilities,courses:[]});
 const result=m.browseWindow({focusedGroup:'f-60'});
 assert.equal(result.visible.length,61);assert.equal(result.more,false);
});
