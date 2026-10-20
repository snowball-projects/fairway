import test from 'node:test';
import assert from 'node:assert/strict';
import chicago from './fixtures/sqlite-query/chicago-query.json' with {type:'json'};
import corica from './fixtures/sqlite-query/corica-query.json' with {type:'json'};
import {PreparationPages,preparationCards,preparationRequestKey} from '../src/fairway/static/preparation-dto.mjs';
// Consumer boundary cases built from DB-owned read fixtures. These are not
// API-owner validated preparation replay fixtures and claim no provider work.
const origins=[{id:'one',coordinate:[42,-88]},{id:'two',coordinate:[42.01,-88]}];
const request={origins,objective:'maximum',radius_km:32.18688,access_policy:'nonmember',round_holes:null};
const requestKey=await preparationRequestKey(request);
function page(source,offset=0,limit=1000) {
  const courses=source.courses.map(course=>({course:structuredClone(course),routing_target:structuredClone(source.destinations.find(d=>d.id===course.destination_id) ?? null),
    travel_times_milliseconds:[null,null],origin_statuses:['pending','pending'],status:'pending',maximum_milliseconds:null,combined_milliseconds:null}));
  return {generation:1,snapshot_sequence:1,areas:[],request,request_key:requestKey,catalog_revision:source.revision,courses:courses.slice(offset,offset+limit),total:courses.length,offset,limit,
    has_more:offset+limit<courses.length,prepared_count:0,pending_count:courses.length,ranking_complete:false,blocked:false,error:null};
}
test('paged full read preserves separate shared-target courses and honest null names',()=>{
  const collection=new PreparationPages(1,request,requestKey);collection.accept(page(corica,0,2));assert.equal(collection.completeRead,false);
  collection.accept(page(corica,2,2));assert.equal(collection.completeRead,true);assert.equal(collection.rows().length,3);
  const cards=preparationCards(collection);assert.equal(new Set(cards.map(c=>c.id)).size,3);
  assert.equal(new Set(cards.map(c=>c.routing_target.id)).size,1);assert.ok(cards.every(c=>c.arrival===null && c.maximum_seconds===null));
  const unknown=new PreparationPages(1,request,requestKey);unknown.accept(page(chicago));
  assert.ok(preparationCards(unknown).every(c=>c.course_name===null && c.name===c.facility_name));
  assert.ok(preparationCards(unknown).every(c=>c.nonmember_bookable===null));
});
test('stale generations are ignored; changed revisions and repeated different pages fail',()=>{
  const collection=new PreparationPages(1,request,requestKey),first=page(corica,0,2);assert.equal(collection.accept({...first,generation:2}),false);
  collection.accept(first);assert.throws(()=>collection.accept({...page(corica,2,2),catalog_revision:2}),/revision/);
  const changed=structuredClone(first);changed.courses[0].course.name='Changed';assert.throws(()=>collection.accept(changed),/Changed preparation page/);
});
test('course score requires every origin and exact millisecond values; unknown is never zero',()=>{
  const collection=new PreparationPages(1,request,requestKey),partial=page(chicago);partial.courses[0].travel_times_milliseconds=[0,null];partial.courses[0].origin_statuses=['complete','pending'];
  const bad=structuredClone(partial);bad.courses[0].maximum_milliseconds=0;assert.throws(()=>collection.accept(bad),/Unscored/);
  collection.accept(partial);const card=preparationCards(collection)[0];assert.deepEqual(card.travel_times_seconds,[0,null]);assert.equal(card.maximum_seconds,null);
  const final=page(chicago);final.courses[0]={...final.courses[0],travel_times_milliseconds:[0,2000],origin_statuses:['complete','complete'],status:'complete',maximum_milliseconds:2000,combined_milliseconds:2000};
  final.prepared_count=1;final.pending_count--;
  const finished=new PreparationPages(1,request,requestKey);finished.accept(final);assert.equal(preparationCards(finished)[0].maximum_seconds,2);
});
test('canonical arrival cannot be promoted from a property estimate or mismatched target',()=>{
  const collection=new PreparationPages(1,request,requestKey),bad=page(corica);bad.courses[0].course.arrival=bad.courses[0].course.map_location;
  assert.throws(()=>collection.accept(bad),/canonical/);
  const mismatch=page(chicago);mismatch.courses[0].routing_target={...mismatch.courses[0].routing_target,latitude:0};
  assert.throws(()=>collection.accept(mismatch),/mismatch/);
});
