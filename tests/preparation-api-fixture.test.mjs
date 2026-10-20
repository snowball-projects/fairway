import test from 'node:test';
import assert from 'node:assert/strict';
import fixture from './fixtures/sqlite-preparation-sequence.json' with {type:'json'};
import {PreparationPages,preparationCards,preparationRequestKey} from '../src/fairway/static/preparation-dto.mjs';
test('API-owner fixed sequence binds actual requests and every snapshot without native admission claims',async()=>{
  for(const step of fixture.steps) {
    const requestKey=await preparationRequestKey(step.request);
    for(const frame of step.frames) {
      assert.equal(frame.request_key,requestKey);
      if(frame.type==='planning.snapshot') {
        assert.equal(frame.snapshot.snapshot_sequence,frame.snapshot_sequence);
        const view=new PreparationPages(frame.generation,step.request,requestKey);view.accept(frame.snapshot);
        assert.equal(view.completeRead,true);assert.equal(view.rows().length,4);
      }
      if(frame.type==='operation.terminal') {
        assert.equal(frame.fixture_complete,true);assert.equal(frame.evidence.basis,'literal-fixture-completion');
        assert.equal(frame.evidence.native_admission_released,false);
      }
      if(frame.type==='area.ready')assert.ok(frame.areas.every(area=>area.geometry.type==='Point' && area.qualification && !Object.hasOwn(area,'radius_km')));
    }
  }
});
test('equal pending counts cannot bind mixed preparation snapshots or different origins',()=>{
  const step=fixture.steps[1],snapshot=step.frames.find(f=>f.type==='planning.snapshot').snapshot;
  const first=structuredClone(snapshot);first.limit=2;first.courses=first.courses.slice(0,2);first.has_more=true;
  const last=structuredClone(snapshot);last.offset=2;last.limit=2;last.courses=last.courses.slice(2);last.has_more=false;
  const view=new PreparationPages(snapshot.generation,step.request,snapshot.request_key);view.accept(first);
  assert.throws(()=>view.accept({...last,snapshot_sequence:last.snapshot_sequence+1}),/snapshot sequences/);
  const changed=structuredClone(last);changed.request.origins[0].coordinate=[0,0];
  assert.throws(()=>view.accept(changed),/request mismatch/);view.accept(last);assert.equal(view.completeRead,true);
});
test('shared destinations retain four course outcomes from two unique route targets and canonical nulls',()=>{
  const step=fixture.steps[0],snapshot=step.frames.at(-1).snapshot;
  const view=new PreparationPages(snapshot.generation,step.request,snapshot.request_key);view.accept(snapshot);
  const cards=preparationCards(view);assert.equal(new Set(cards.map(c=>c.id)).size,4);
  assert.equal(new Set(cards.map(c=>c.routing_target.id)).size,2);
  assert.ok(cards.every(c=>c.arrival===null && c.routing_target.scope==='facility_estimate' && c.routing_target.qualification));
  assert.ok(cards.every(c=>c.nonmember_bookable===null && c.booking_availability===null));
  assert.ok(cards.some(c=>c.course_name===null && c.name===c.facility_name));
});
test('actual 100-course DTO stays complete as a pool at24scored76pending then100scored',()=>{
  const partial=fixture.large_pool.partial_24_scored,final=fixture.large_pool.fully_prepared;
  for(const snapshot of [partial,final]) {
    const view=new PreparationPages(snapshot.generation,snapshot.request,snapshot.request_key);view.accept(snapshot);
    assert.equal(view.completeRead,true);assert.equal(view.rows().length,100);
    assert.equal(preparationCards(view).filter(c=>c.maximum_seconds!==null).length,snapshot.prepared_count);
  }
  assert.equal(partial.prepared_count,24);assert.equal(partial.pending_count,76);assert.equal(partial.ranking_complete,false);
  assert.equal(final.prepared_count,100);assert.equal(final.pending_count,0);assert.equal(final.ranking_complete,true);
});

test('complete reads reject forged counts, changed shared target identity and mixed area pages atomically',()=>{
  const snapshot=fixture.steps[0].frames.find(f=>f.type==='planning.snapshot').snapshot;
  const make=()=>new PreparationPages(snapshot.generation,snapshot.request,snapshot.request_key);
  const counts=structuredClone(snapshot);counts.prepared_count=counts.total;counts.pending_count=0;counts.ranking_complete=true;
  const view=make();assert.throws(()=>view.accept(counts),/summary/);assert.equal(view.completeRead,false);assert.equal(view.rows().length,0);
  const alias=structuredClone(snapshot),seen=new Map();
  for(const row of alias.courses){const id=row.routing_target.id;if(seen.has(id)){row.routing_target.latitude+=1;break;}seen.set(id,row);}
  assert.throws(()=>make().accept(alias),/shared routing target/);
  const first=structuredClone(snapshot),last=structuredClone(snapshot);first.limit=2;first.courses=first.courses.slice(0,2);first.has_more=true;
  last.offset=2;last.limit=2;last.courses=last.courses.slice(2);last.has_more=false;
  const paged=make();paged.accept(first);last.areas=[{id:'other',center:[42,-88],geometry:{type:'Point',coordinates:[-88,42]},qualification:'synthetic inconsistent-page case'}];
  assert.throws(()=>paged.accept(last),/area context/);assert.equal(paged.completeRead,false);assert.equal(paged.rows().length,2);
  const repeated=structuredClone(first);repeated.areas=last.areas;assert.throws(()=>paged.accept(repeated),/area context/);
});
