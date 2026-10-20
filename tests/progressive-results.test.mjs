import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {ProgressiveSearch, parseOrigin, score, sortedIds} from '../experiments/progressive-results/model.mjs';
import {fixture} from '../experiments/progressive-results/catalog-fixture.mjs';
import {mockSearch} from '../experiments/progressive-results/mock.mjs';
function setup() {
  let clock = 0, preparations = 0;
  const model = new ProgressiveSearch({prepare: () => {preparations++; return fixture;}, now: () => clock});
  const commit = () => {model.edit(0, '41.90, -88.00'); model.commit(0); model.edit(1, '42.10, -87.75'); model.commit(1);};
  const begin = () => {commit(); const request = model.start(); const events = [];
    mockSearch(request, e => model.receive(e), {schedule: (fn, ms) => {events.push({fn, ms}); return events.length;}, unschedule: () => {}});
    return {request, events, step: i => {clock = events[i].ms; events[i].fn();}};
  };
  return {model, begin, commit, preparations: () => preparations};
}
test('typing performs no preparation; only complete committed group prepares; Enter then blur deduplicates', () => {
  const {model, preparations} = setup();
  for (const text of ['4','41','41.90,','41.90, -88.00']) model.edit(0, text);
  assert.equal(preparations(), 0); model.commit(0); assert.equal(preparations(), 0);
  model.edit(1, '42.10, -87.75'); model.commit(1); model.commit(1);
  assert.equal(preparations(), 1); assert.ok(model.start()); assert.equal(model.start(), null);
});
test('invalid, uncommitted or extra incomplete golfers cannot start; normalization deduplicates unchanged inputs', () => {
  const {model, commit, preparations} = setup(); commit();
  model.edit(1, '42.1, -87.750'); model.commit(1); assert.equal(preparations(), 1);
  model.edit(1, '42.1, -87.7'); assert.equal(model.start(), null);
  model.texts.push(''); model.committed.push(null); assert.equal(model.start(), null);
  for (const value of ['','41,','41,NaN','Infinity, -88','60,-88','41,-180','41,-88 junk']) assert.equal(parseOrigin(value), null);
});
test('area and catalog appear before times; partial origin vectors never get scores; complete matrix ranks both objectives', () => {
  const {model, begin} = setup(); const {step} = begin();
  step(0); assert.equal(model.areas.length, 1); assert.equal(model.rows.length, 0);
  step(1); assert.equal(model.rows.length, 6); assert.ok(model.rows.every(r => score(r.times, 2) === null));
  step(2); assert.ok(score(model.rows[0].times, 2)); assert.equal(model.phase, 'matrix');
  step(3); assert.equal(model.rows[2].times[1], null); assert.equal(score(model.rows[2].times, 2), null);
  step(4); step(5); assert.equal(model.phase, 'complete'); assert.equal(model.timings.complete, 7300);
  assert.equal(model.timings.modo, 1800); assert.equal(model.timings.courseMatrix, 5400);
  assert.equal(model.order[0], fixture.facilities[1].id);
  model.objectiveChanged('combined'); assert.equal(model.order[0], fixture.facilities[0].id);
  assert.equal(model.areaObjective, 'maximum'); assert.equal(model.searches, 1);
  assert.equal(model.rows[5].reason, 'unreachable'); assert.equal(score(model.rows[5].times, 2), null);
});
test('edits, cancellation and objective replacement reject all late generation events', () => {
  for (const action of [m => m.edit(0,'41.95,-88'), m => m.cancel(), m => m.objectiveChanged('combined')]) {
    const {model, begin} = setup(); const {step, request} = begin(); step(0); action(model);
    for (let i = 1; i < 6; i++) step(i);
    assert.equal(model.rows.length, 0); assert.notEqual(model.phase, 'complete');
    assert.equal(model.receive({generation: request.generation, sequence: 100, type:'search.error'}), false);
  }
});
test('focus and pointer freeze the whole list until both interactions end, while time values update', () => {
  const {model, begin} = setup(); const {step} = begin(); step(0); step(1);
  const initial = [...model.order], id = initial[0];
  model.interact(id, true); model.interact(id, true, 'pointer');
  for (let i = 2; i < 6; i++) step(i);
  assert.deepEqual(model.order, initial); assert.equal(model.sortPending, true); assert.ok(score(model.rows[2].times, 2));
  model.interact(id, false); assert.deepEqual(model.order, initial);
  model.interact(id, false, 'pointer'); assert.notDeepEqual(model.order, initial); assert.equal(model.sortPending, false);
});
test('missing/negative/nonfinite values are never zero scores; zero routes remain valid; tie breaks deterministic', () => {
  for (const times of [[null, 4], [undefined,4], [NaN,4],[-1,4],[Infinity,4],[1.1,4],[4]]) assert.equal(score(times,2),null);
  assert.deepEqual(score([0,4],2),{maximum:4,combined:4});
  const rows = [{id:'b',name:'Same',times:[2,2]},{id:'a',name:'Same',times:[2,2]}];
  assert.deepEqual(sortedIds(rows,'maximum',2),['a','b']);
});
test('provider outage revokes partial scores; unfinished matrix and bad identity/values cannot finalize', () => {
  for (const payload of [{type:'search.error'}, {type:'search.complete',scoring_ms:1},
    {type:'matrix.batch',destinations:[{id:'unknown',times:[1,2]}]},
    {type:'matrix.batch',destinations:[{id:fixture.facilities[0].id,times:[1,-2]}]}]) {
    const {model,begin} = setup(); const {step,request} = begin(); step(0);step(1);step(2);
    model.receive({generation:request.generation,sequence:4,...payload});
    assert.equal(model.phase,'error'); assert.ok(model.rows.every(r => score(r.times,2)===null));
  }
});
test('duplicate batch ignored; changed established times rejected; more than 24 candidates rejected', () => {
  const {model,begin} = setup(); const {step,request} = begin(); step(0);step(1);step(2);
  assert.equal(model.receive({generation:request.generation,sequence:3,type:'search.error'}),false);
  model.receive({generation:request.generation,sequence:4,type:'matrix.batch',destinations:[{id:fixture.facilities[0].id,times:[1,2]}]});
  assert.equal(model.phase,'error');
  const second = setup(); const start = second.begin();start.step(0);
  second.model.receive({generation:start.request.generation,sequence:2,type:'candidates.ready',facilities:Array(25).fill(fixture.facilities[0])});
  assert.equal(second.model.phase,'error');
});
test('mock cancellation clears every scheduled batch; failure scenario never emits complete; 8-origin workload remains bounded', () => {
  const scheduled = [], cleared = [];
  const cancel = mockSearch({generation:1,origins:Array(8).fill([41,-88])},()=>{}, {failure:true,
    schedule:(fn,ms)=>{scheduled.push([fn,ms]);return ms;}, unschedule:id=>cleared.push(id)});
  cancel(); assert.equal(scheduled.length,5);assert.deepEqual(cleared,scheduled.map(x=>x[1]));
  const events=[]; mockSearch({generation:1,origins:Array(8).fill([41,-88])},e=>events.push(e),{schedule:fn=>{fn();return 1;},unschedule:()=>{}});
  assert.equal(Math.max(...events.filter(e=>e.destinations).flatMap(e=>e.destinations.map(r=>r.times.length))),8);
});
test('sampled catalog facts exactly match pinned existing source and retain source identity', () => {
  const pinned=JSON.parse(readFileSync(new URL('./fixtures/progressive-catalog-pinned.json',import.meta.url)));
  assert.equal(pinned.source_commit,fixture.source_commit);
  assert.equal(pinned.catalog_sha256,fixture.catalog_sha256);
  assert.deepEqual(pinned.facilities,fixture.facilities);
  const catalogPath=new URL('../data/catalog.json',import.meta.url);
  if (existsSync(catalogPath)) {
    const raw=readFileSync(catalogPath);
    assert.equal(createHash('sha256').update(raw).digest('hex'),fixture.catalog_sha256);
    const catalog=JSON.parse(raw);fixture.facilities.forEach(f=>assert.deepEqual(catalog.facilities.find(x=>x.id===f.id),f));
  }
});
test('explicit retryable mock failure enables exactly one new unchanged-input search; stale events stay rejected', () => {
  const {model,begin,preparations} = setup(); const {step,request} = begin();
  step(0);step(1);step(2);
  model.receive({generation:request.generation,sequence:4,type:'search.error',error:{code:'mock_routing_unavailable',retryable:true}});
  assert.equal(model.canStart(),true); assert.equal(model.searches,1);
  assert.ok(model.rows.every(r=>score(r.times,2)===null));
  const retry=model.start(); assert.ok(retry);assert.notEqual(retry.generation,request.generation);
  assert.deepEqual(retry.origins,request.origins);assert.equal(model.searches,2);assert.equal(preparations(),1);
  assert.equal(model.canStart(),false);assert.equal(model.start(),null);
  assert.equal(model.receive({generation:request.generation,sequence:10,type:'search.complete'}),false);
});
test('unknown upstream outcome stays blocked across edits, commits, objectives and cancellation, even if tagged retryable', () => {
  for (const retryable of [false,true]) {
    const {model,begin} = setup();const {request}=begin();
    model.receive({generation:request.generation,sequence:1,type:'search.error',error:{code:'upstream_outcome_unknown',retryable}});
    assert.equal(model.errorRetryable,false);assert.equal(model.canStart(),false);assert.equal(model.start(),null);
    model.edit(0,'41.95, -88');model.commit(0);model.objectiveChanged('combined');model.cancel();
    assert.equal(model.upstreamOutcomeUnknown,true);assert.equal(model.canStart(),false);assert.equal(model.start(),null);
    assert.equal(model.searches,1);
  }
});
test('unspecified/nonretryable errors disable Search; completed objective changes truthfully allow a new area search', () => {
  const {model,begin} = setup();const {step,request}=begin();
  model.receive({generation:request.generation,sequence:1,type:'search.error'});
  assert.equal(model.canStart(),false);assert.equal(model.start(),null);
  const second=setup();const run=second.begin();run.events.forEach((_,i)=>run.step(i));
  assert.equal(second.model.canStart(),false);assert.equal(second.model.start(),null);
  second.model.objectiveChanged('combined');assert.equal(second.model.canStart(),true);
  assert.equal(second.model.start().objective,'combined');assert.equal(second.model.start(),null);
});
test('removing a committed golfer invalidates preparation; submit cannot prepare until an explicit recommit', () => {
  const {model,commit,preparations}=setup();commit();
  model.texts.push('');model.committed.push(null);model.invalidate();
  model.edit(2,'42.05, -87.90');model.commit(2);
  assert.equal(preparations(),2);assert.equal(model.canStart(),true);
  model.texts.splice(2,1);model.committed.splice(2,1);model.invalidate();
  assert.ok(model.key());assert.notEqual(model.key(),model.cacheKey);
  assert.equal(model.canStart(),false);assert.equal(model.start(),null);
  assert.equal(preparations(),2);assert.equal(model.searches,0);
  model.commit(0);assert.equal(preparations(),3);assert.equal(model.canStart(),true);
  assert.ok(model.start());assert.equal(preparations(),3);assert.equal(model.searches,1);
});
test('direct row-to-row focus handoff never exposes an intermediate empty interaction set', () => {
  const {model,begin}=setup();const {step}=begin();step(0);step(1);
  const initial=[...model.order], [first,second]=initial; model.interact(first,true);step(2);
  const snapshots=[];model.notify=()=>snapshots.push([...model.order]);
  model.transferFocus(first,second);model.interact(second,true);
  assert.deepEqual(snapshots,[initial,initial]);assert.deepEqual([...model.interactions],[`focus:${second}`]);
  for(let i=3;i<6;i++)step(i);
  assert.deepEqual(model.order,initial);model.transferFocus(second,null);
  assert.notDeepEqual(model.order,initial);assert.equal(model.interactions.size,0);
});
