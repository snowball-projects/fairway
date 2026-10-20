import test from 'node:test';import assert from 'node:assert/strict';
import fixture from './fixtures/plan-continuation/protocol.json' with {type:'json'};
import {createProtocolAdapter} from './fixtures/plan-continuation/adapter.mjs';
import {LogicalTransport} from '../src/fairway/static/logical-transport.mjs';
import {LogicalPlanningSession} from '../src/fairway/static/logical-planning-session.mjs';
const c=name=>fixture.cases.find(c=>c.case===name),tick=()=>new Promise(r=>setImmediate(r));
const until=async pred=>{for(let i=0;i<100&&!pred();i++)await tick();assert.ok(pred(),'fixture state reached');};
function setup(scenario='held') {const adapter=createProtocolAdapter(fixture,{scenario}),transport=new LogicalTransport({adapter,authorization:{allowed:true,caller:'offline-reviewer'}}),waits=[];
 const session=new LogicalPlanningSession({transport,sleep:()=>new Promise(r=>waits.push(r))});return {adapter,transport,session,waits};}
const release=async f=>{f.waits.shift()?.();await tick();};
test('input clear/edit keeps one owner through clean stale work and trusted-host retry, without browser retry/reset',async()=>{
 const f=setup();f.session.update(c('admitted-without-upstream').post.body.origins);await until(()=>f.waits.length>0);
 assert.equal(f.session.owned,true);assert.equal(f.session.active.logical,true);assert.equal(f.session.upstreamStarted,false);assert.equal(f.session.courseCards().length,4);
 f.adapter.advance('held-chunk');await release(f);await until(()=>f.session.operationActive);f.session.update([]);await until(()=>f.transport.current.generation===2);await release(f);await until(()=>f.session.lastView?.generation===2);
 assert.equal(f.session.courseCards().length,0);assert.equal(f.session.phase,'clearing');assert.equal(f.session.operationActive,true);assert.equal(f.session.active.logical,true);
 f.session.update(c('edit-while-held').post.body.origins);await until(()=>f.transport.current.generation===3);await release(f);await until(()=>f.session.lastView.generation===3);
 f.adapter.advance('clean-stale-chunk-not-logical-terminal');await release(f);await until(()=>f.session.lastView.snapshotSequence===9);assert.equal(f.session.logicalStopped,false);assert.equal(f.session.active.logical,true);
 f.adapter.advance('explicit-trusted-retry-complete');await release(f);await until(()=>!f.session.polling);assert.equal(f.session.phase,'complete');assert.equal(f.session.active,null);assert.equal(f.session.owned,true);assert.equal(f.transport.identity.session_id,'offline-session-0');assert.equal(f.adapter.metrics.posts,3);
});
test('typing/invalidation and ordinary browse never POST, stale results stay hidden, recommit same input reuses ownership',async()=>{
 const f=setup();const origins=c('admitted-without-upstream').post.body.origins;f.session.update(origins);await until(()=>f.waits.length>0);f.session.invalidate([]);
 assert.equal(f.session.courseCards().length,0);assert.equal(f.adapter.metrics.posts,1);assert.equal(f.session.active.logical,true);
 f.adapter.advance('held-chunk');await release(f);await until(()=>f.session.operationActive);assert.equal(f.session.courseCards().length,0);f.session.update(origins);await until(()=>!f.session.posting);await release(f);await until(()=>f.session.courseCards().length===4);assert.equal(f.adapter.metrics.posts,1);
 // Controlled fixture stop for test cleanup, never a provider cancel.
 f.session.blocked=true;await release(f);await until(()=>!f.session.polling);
});
test('one pending latest input coalesces behind a held POST and rebases generation, without second session',async()=>{
 const f=setup();const fetcher=f.adapter.fetcher;let start;const gate=new Promise(r=>start=r);let first=true;
 f.adapter.fetcher=async(path,options)=>{if(options.method==='POST'&&first){first=false;await gate;}return fetcher(path,options);};
 f.session.update(c('admitted-without-upstream').post.body.origins);await until(()=>f.session.posting);f.session.update([]);f.session.update(c('edit-while-held').post.body.origins);
 // Only last committed pending input is retained; skipped generation2 is allowed
 // by the source, but supplied fixture requires clear2 then edit3. Use clear2
 // as latest to exercise this literal fixture without fabricating a new POST.
 f.session.update([]);start();await until(()=>f.transport.current?.generation===2);assert.equal(f.adapter.metrics.posts,2);assert.equal(f.adapter.metrics.logicalSessionIds.size,1);
 f.session.blocked=true;await release(f);await until(()=>!f.session.polling);
});
test('limited full pool remains100 with24 provisional/76pending; logical stop leaves owner and ledger intact',async()=>{
 const f=setup('limited');f.session.update(c('deadline-limited-retains-provisional-vectors').post.body.origins);await until(()=>!f.session.posting&&!f.session.polling&&f.session.lastView);
 assert.equal(f.session.phase,'partial');assert.equal(f.session.courseCards().length,100);assert.equal(f.session.courseCards().filter(c=>c.maximum_seconds!==null).length,24);assert.equal(f.session.logicalStopped,true);assert.equal(f.session.owned,true);assert.equal(f.session.logicalBudget.remaining_milliseconds_at_snapshot,0);
});
test('fatal malformed progress revokes provisional vectors, retains ownership and blocks replacement input',async()=>{
 const f=setup('pool');f.session.update(c('full-pool-24-complete-76-pending').post.body.origins);await until(()=>f.waits.length>0);assert.equal(f.session.courseCards().filter(c=>c.maximum_seconds!==null).length,24);
 f.adapter.fetcher=async()=>Response.json({code:'upstream_outcome_unknown',engine_unknown:true,retryable:false},{status:503});await release(f);await until(()=>f.session.blocked);
 assert.equal(f.session.owned,true);assert.ok(f.session.courseCards().every(c=>c.maximum_seconds===null&&c.travel_times_seconds.every(t=>t===null)));
 assert.equal(f.session.update(c('edit-while-held').post.body.origins),false);assert.equal(f.adapter.metrics.posts,1);
});

test('invalid filters fail before local settings or input change',()=>{
 const f=setup();for(const holes of [[],[9,27],[9,9],null])assert.throws(()=>f.session.update([], 'maximum', holes));
 assert.throws(()=>f.session.radiusChanged(0));assert.equal(f.session.radiusKilometers,32.18688);
 assert.throws(()=>f.session.accessChanged('invalid'));assert.equal(f.session.accessPolicy,'nonmember');assert.equal(f.adapter.metrics.posts,0);
});
