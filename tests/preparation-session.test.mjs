import test from 'node:test';
import assert from 'node:assert/strict';
import fixture from './fixtures/sqlite-preparation-sequence.json' with {type:'json'};
import {preparationRequestKey} from '../src/fairway/static/preparation-dto.mjs';
import {PreparationSession} from '../src/fairway/static/preparation-session.mjs';
import {createPreparationFixtureAdapter} from './fixtures/sqlite-preparation-adapter.mjs';
const origins=fixture.steps[1].request.origins;
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const finish=state=>new Promise((resolve,reject)=>{
  if(state.blocked||(!state.active&&!state.pending))return resolve();
  const original=state.notify,timeout=setTimeout(()=>{state.notify=original;reject(new Error("Fixture completion timed out"));},2000);
  state.notify=s=>{original(s);if(state.blocked||(!state.active&&!state.pending)){clearTimeout(timeout);state.notify=original;resolve();}};
});
test('clean API replay shows four shared-target course outcomes and point area without client scoring',async()=>{
  const adapter=createPreparationFixtureAdapter({sleep:async()=>{}}),state=new PreparationSession({adapter});
  assert.equal(state.update(origins.slice(0,1)),true);await finish(state);
  assert.equal(state.phase,'complete');assert.equal(state.courseCards().length,4);
  assert.equal(new Set(state.courseCards().map(c=>c.routing_target.id)).size,2);
  assert.equal(state.update(origins.slice(0,1)),false);assert.equal(adapter.metrics.operations,1);
  state.update(origins);await finish(state);assert.equal(state.phase,'complete');
  assert.equal(state.areas[0].geometry.type,'Point');assert.equal(adapter.metrics.operations,2);
  assert.equal(adapter.metrics.maxActive,1);assert.equal(adapter.metrics.cells,4);
});
test('fixture scope rejects changed radius without reusing unrelated fixed vectors',async()=>{
  const adapter=createPreparationFixtureAdapter({sleep:async()=>{}}),state=new PreparationSession({adapter});
  state.update(origins.slice(0,1));await finish(state);state.radiusChanged(16.09344);await finish(state);
  assert.equal(state.error.code,'fixture_request_unavailable');assert.equal(state.phase,'error');
  assert.deepEqual(state.courseCards(),[]);assert.equal(adapter.metrics.operations,1);assert.equal(state.active,null);
});
test('one active replay holds across edits; only latest pending generation runs',async()=>{
  const waits=[],adapter=createPreparationFixtureAdapter({sleep:()=>new Promise(resolve=>waits.push(resolve))}),state=new PreparationSession({adapter});
  state.update(origins.slice(0,1));for(let i=0;i<100 && !waits.length;i++)await tick();assert.equal(waits.length,1);
  state.update(origins);state.invalidate(origins.slice(0,1));assert.deepEqual(state.courseCards(),[]);
  state.update(origins);assert.equal(adapter.metrics.operations,1);waits.shift()();for(let i=0;i<100 && adapter.metrics.operations<2;i++)await tick();
  assert.equal(adapter.metrics.operations,2);assert.equal(adapter.metrics.maxActive,1);
  while(waits.length){waits.shift()();await tick();await tick();}await finish(state);
  assert.equal(state.phase,'complete');assert.equal(state.origins.length,2);
});
test('uncertain fixture completion blocks automatic replacement across input edits',async()=>{
  const state=new PreparationSession({adapter:{fixtureOnly:true,replay:async()=>{throw new Error('lost completion');}}});
  state.update(origins.slice(0,1));await finish(state);assert.equal(state.blocked,true);assert.ok(state.active);
  assert.equal(state.update(origins),false);assert.equal(state.error.code,'upstream_outcome_unknown');
});

test('trusted fixture completion with missing result pages exposes an incomplete-read error',async()=>{
  const step=fixture.steps[0],frame=structuredClone(step.frames.find(f=>f.type==='planning.snapshot'));
  frame.snapshot.limit=2;frame.snapshot.courses=frame.snapshot.courses.slice(0,2);frame.snapshot.has_more=true;
  const state=new PreparationSession({adapter:{fixtureOnly:true,replay:async(request,emit)=>{
    emit(frame);return {fixture_complete:true,evidence:{basis:'literal-fixture-completion',native_admission_released:false}};
  }}});state.update(step.request.origins);await finish(state);
  assert.equal(state.error.code,'preparation_read_incomplete');assert.equal(state.phase,'error');assert.equal(state.blocked,false);
  assert.equal(state.active,null);assert.deepEqual(state.courseCards(),[]);
});

test('qualified finite fixture limits keep complete scores, all pending rows and separate area incompleteness',async()=>{
  const source=fixture.large_pool.partial_24_scored;
  const session=new PreparationSession({adapter:{fixtureOnly:true,async replay(request,emit){
    const key=await preparationRequestKey(request),snapshot=structuredClone(source);snapshot.request=request;snapshot.request_key=key;
    const envelope={generation:snapshot.generation,request,request_key:key,catalog_revision:snapshot.catalog_revision,snapshot_sequence:snapshot.snapshot_sequence};
    emit({...envelope,sequence:1,type:'planning.snapshot',snapshot});
    emit({...envelope,sequence:2,type:'preparation.limited',preparation_limited:true,area_search_complete:false});
    return {fixture_complete:true,evidence:{basis:'literal-fixture-completion',native_admission_released:false}};
  }}});
  session.update(source.request.origins);await finish(session);
  assert.equal(session.phase,'partial');assert.equal(session.error,null);assert.equal(session.limited,true);assert.equal(session.areaSearchComplete,false);
  assert.equal(session.courseCards().length,100);assert.equal(session.courseCards().filter(c=>c.maximum_seconds!==null).length,24);
});

test('fatal provider frame revokes all provisional scores and origin times, distinct from nonfatal finite limit',async()=>{
  const source=fixture.steps[0].frames.at(-1).snapshot;
  const session=new PreparationSession({adapter:{fixtureOnly:true,async replay(request,emit){
    const snapshot=structuredClone(source),key=await preparationRequestKey(request);snapshot.request=request;snapshot.request_key=key;
    const binding={generation:snapshot.generation,request,request_key:key,catalog_revision:snapshot.catalog_revision,snapshot_sequence:snapshot.snapshot_sequence};
    emit({...binding,type:'planning.snapshot',sequence:1,snapshot});
    emit({...binding,type:'preparation.error',sequence:2,code:'provider_unavailable'});
    return {fixture_complete:true,evidence:{basis:'literal-fixture-completion',native_admission_released:false}};
  }}});
  session.update(source.request.origins);await finish(session);
  assert.equal(session.phase,'error');assert.equal(session.limited,false);assert.ok(session.courseCards().every(c=>c.maximum_seconds===null&&c.travel_times_seconds.every(t=>t===null)&&c.status==='error'));
});
