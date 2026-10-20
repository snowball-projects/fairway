import test from 'node:test';import assert from 'node:assert/strict';
import fixture from './fixtures/plan-continuation/protocol.json' with {type:'json'};
import {createProtocolAdapter} from './fixtures/plan-continuation/adapter.mjs';
import {LogicalTransport,LogicalPages,PROTOCOL_SHA} from '../src/fairway/static/logical-transport.mjs';
import {canonicalRequest} from '../src/fairway/static/preparation-dto.mjs';
const c=name=>fixture.cases.find(c=>c.case===name),request=body=>Object.fromEntries(Object.entries(body).filter(([k])=>k!=='generation'));
const make=(scenario='held',override)=>{const adapter=createProtocolAdapter(fixture,{scenario});if(override)override(adapter);return {adapter,client:new LogicalTransport({adapter,authorization:{allowed:true,caller:'offline-reviewer'}})};};
const post=async(client,name)=>{const body=c(name).post.body;return client.update(request(body),body.generation);};
test('new consumer retains fake-only pinned fixture and authorization guards',()=>{
 assert.throws(()=>new LogicalTransport({adapter:{fetcher:fetch}}),/fake-only/);
 const adapter=createProtocolAdapter(fixture);assert.throws(()=>new LogicalTransport({adapter,authorization:{allowed:false}}),/unauthorized/);
 assert.equal(adapter.protocolSha,PROTOCOL_SHA);
});
test('admitted/held/clear/edit/clean chunk retain one logical session and accounting; source work receipt is not stop proof',async()=>{
 const {adapter,client}=make();const catalog=await client.readCatalog();assert.equal(catalog.courses.length,4);assert.equal(catalog.catalogReleaseKey,'offline-release-11');
 await post(client,'admitted-without-upstream');let view=await client.read();assert.equal(view.upstreamStarted,false);assert.equal(view.logicalStopped,null);assert.equal(view.rows.length,4);
 adapter.advance('held-chunk');view=await client.read();assert.equal(view.operationActive,true);
 await post(client,'clear-while-held');view=await client.read();assert.equal(view.rows.length,0);assert.equal(view.operationActive,true);assert.equal(view.logicalStopped,null);
 await post(client,'edit-while-held');view=await client.read();assert.equal(view.rows.length,4);assert.equal(view.operationActive,true);
 adapter.advance('clean-stale-chunk-not-logical-terminal');view=await client.read();assert.equal(view.operationActive,false);assert.equal(view.workReceiptPresent,true);assert.equal(view.logicalStopped,null);assert.equal(view.logicalBudget.provider_requests,1);
 adapter.advance('explicit-trusted-retry-complete');view=await client.read();assert.equal(view.logicalStopped.status,'complete');assert.equal(view.rows.filter(r=>r.maximum_milliseconds!==null).length,4);assert.equal(view.logicalBudget.provider_requests,2);
 assert.equal(adapter.metrics.logicalSessionIds.size,1);assert.equal(adapter.metrics.posts,3);assert.equal(client.identity.session_id,'offline-session-0');assert.ok(!JSON.stringify(view).includes('calculator-ordered-completions'));
});
test('100-row whole pool advances24 to100 without new POST, and limited case keeps24 scores/76pending',async()=>{
 const {adapter,client}=make('pool');await client.readCatalog();await post(client,'full-pool-24-complete-76-pending');let view=await client.read();assert.equal(view.rows.length,100);assert.equal(view.summary.prepared_count,24);assert.equal(view.logicalStopped,null);
 adapter.advance('full-pool-complete-logical-terminal');view=await client.read();assert.equal(view.summary.prepared_count,100);assert.equal(view.logicalBudget.provider_requests,13);assert.equal(view.logicalStopped.status,'complete');assert.equal(adapter.metrics.posts,1);assert.equal(adapter.metrics.pages,8);
 const limited=make('limited');await post(limited.client,'deadline-limited-retains-provisional-vectors');view=await limited.client.read();assert.equal(view.rows.length,100);assert.equal(view.summary.prepared_count,24);assert.equal(view.logicalStopped.status,'limited');assert.equal(view.logicalBudget.remaining_milliseconds_at_snapshot,0);
});
test('area stage remains distinct and a clean course chunk does not end its logical preparation',async()=>{
 const {adapter,client}=make('area');await post(client,'two-origins-clean-chunk-area-still-pending');let view=await client.read();assert.equal(view.areaSearchComplete,false);assert.equal(view.logicalStopped,null);assert.equal(view.workReceiptPresent,true);
 adapter.advance('two-origins-point-area-complete');view=await client.read();assert.equal(view.areas[0].geometry.type,'Point');assert.equal(view.areaSearchComplete,true);assert.equal(view.logicalStopped.status,'complete');assert.equal(view.logicalBudget.provider_requests,12);
});
test('same-revision release replacement rejects across both resources with zero preparation POST',async()=>{
 const {adapter,client}=make();const fetcher=adapter.fetcher;
 adapter.fetcher=async(path,options)=>{const reply=await fetcher(path,options);if(path.includes('/catalog/courses')){const value=await reply.json();value.catalog_release_key='different-release';return Response.json(value);}return reply;};
 await assert.rejects(client.readCatalog(),/catalog_release_changed/);assert.equal(adapter.metrics.posts,0);
});
test('event queries bind current generation/key and discard historical headers before any observer',async()=>{
 const {adapter,client}=make();await post(client,'admitted-without-upstream');await client.read();await post(client,'clear-while-held');const fetcher=adapter.fetcher;let observed=0;
 adapter.fetcher=async(path,options)=>{const reply=await fetcher(path,options);if(path.includes('/events')){const value=await reply.json();value.events.unshift(c('held-chunk').read.events_response.events.at(-1));return Response.json(value);}return reply;};
 await assert.rejects(client.read(()=>observed++),/mixed_event_generation/);assert.equal(observed,0);
 const path=adapter.metrics.requests.filter(r=>r.path.includes('/events')).at(-1).path;assert.ok(path.includes('generation=2')&&path.includes('request_key=')&&path.includes('limit=64'));
});
test('snapshot pages bind release, ledger and active state atomically; same counts cannot mix metadata',()=>{
 const sample=c('full-pool-24-complete-76-pending').read,first=sample.pages[0];const context={...sample.events_response,request:first.request};
 for(const field of ['catalog_release_key','logical_budget','operation_active']){
  const view=new LogicalPages(context);view.accept(first);const bad=structuredClone(sample.pages[1]);if(field==='catalog_release_key')bad[field]='new-release';if(field==='logical_budget')bad[field].provider_requests++;if(field==='operation_active'){bad[field]=true;bad.active_work_id=9;}
  assert.throws(()=>view.accept(bad));assert.equal(view.rows().length,25);assert.equal(view.completeRead,false);
 }
});
test('raw logical terminal without literal fixture witness, held terminal and bad native proof never reach observer',async()=>{
 for(const mutation of [(r)=>r.terminal.native_admission_released=true,(r)=>r.operation_active=true,(r)=>r.terminal.snapshot_sequence--,(r)=>r.terminal.scope='chunk']){
  const {adapter,client}=make('limited');await post(client,'deadline-limited-retains-provisional-vectors');const fetcher=adapter.fetcher;let observed=0;
  adapter.fetcher=async(path,options)=>{const reply=await fetcher(path,options);if(path.includes('/events')){const value=await reply.json();mutation(value);return Response.json(value);}return reply;};await assert.rejects(client.read(()=>observed++));assert.equal(observed,0);
 }
 const {adapter,client}=make('limited');adapter.attestLogicalStop=()=>false;await post(client,'deadline-limited-retains-provisional-vectors');await assert.rejects(client.read(),/logical_stop_unconfirmed/);
});
test('budget cannot reset on a newer view; negative counters, expanded caps and extended remaining time fail',async()=>{
 const {adapter,client}=make('pool');await post(client,'full-pool-24-complete-76-pending');await client.read();adapter.advance('full-pool-complete-logical-terminal');const fetcher=adapter.fetcher;let observed=0;
 adapter.fetcher=async(path,options)=>{const reply=await fetcher(path,options);if(path.includes('/snapshot')){const value=await reply.json();value.logical_budget.provider_requests=0;return Response.json(value);}return reply;};await assert.rejects(client.read(()=>observed++),/logical_budget_reset/);assert.equal(observed,0);
 const page=structuredClone(c('held-chunk').read.pages[0]),context={...c('held-chunk').read.events_response,request:page.request};for(const values of [{provider_requests:-1},{request_limit:33},{remaining_milliseconds_at_snapshot:30001}]){const bad=structuredClone(page);Object.assign(bad.logical_budget,values);assert.throws(()=>new LogicalPages(context).accept(bad),/budget/);}
});
test('same owner/input deduplicates, replacement session refused, busy grants no retry, reads never create work',async()=>{
 const {adapter,client}=make();await post(client,'admitted-without-upstream');await post(client,'admitted-without-upstream');assert.equal(adapter.metrics.posts,1);
 adapter.fetcher=async()=>Response.json(c('predispatch-busy-no-global-journal-proof').error,{status:503});await assert.rejects(client.read(),error=>error.retryable===false&&error.code==='busy');assert.equal(adapter.metrics.posts,1);
 const other=make();await post(other.client,'admitted-without-upstream');const fetcher=other.adapter.fetcher;
 other.adapter.fetcher=async(path,options)=>{const reply=await fetcher(path,options);const value=await reply.json();if(options.method==='POST')value.session_id='replacement-session';return Response.json(value);};await assert.rejects(post(other.client,'clear-while-held'),/changed_plan_binding/);assert.equal(other.client.identity.session_id,'offline-session-0');
});
test('read-only recovery validates current pointer and cannot adopt stale input or backward tokens',async()=>{
 for(const wrong of ['generation','snapshot_sequence','catalog_release_key']){
  const {adapter,client}=make();await post(client,'admitted-without-upstream');let observed=0;
  const pointer=structuredClone(c('admitted-without-upstream').read.events_response);if(wrong==='generation')pointer.generation++;if(wrong==='snapshot_sequence')pointer.snapshot_sequence=0;if(wrong==='catalog_release_key')pointer.catalog_release_key='foreign-release';
  adapter.fetcher=async()=>Response.json({status:409,code:'cursor_expired',recovery:'restart-current-reads',retryable:false,latest:pointer},{status:409});await assert.rejects(client.read(()=>observed++));assert.equal(observed,0);assert.equal(adapter.metrics.posts,1);
 }
});

test('cursor and advancing snapshot conflicts recover complete current GET reads only, with one POST',async()=>{
 for(const kind of ['events','snapshot']) {
  const {adapter,client}=make();await post(client,'admitted-without-upstream');const fetcher=adapter.fetcher;let once=true,observed=0;
  adapter.fetcher=async(path,options)=>{if(once&&path.endsWith(kind)===false&&path.includes('/'+kind+'?')){once=false;if(kind==='snapshot')adapter.advance('held-chunk');const latest=structuredClone(c(kind==='snapshot'?'held-chunk':'admitted-without-upstream').read.events_response);return Response.json({status:409,code:kind==='events'?'cursor_expired':'snapshot_changed',latest,recovery:'restart-current-reads',retryable:false},{status:409});}return fetcher(path,options);};
  const view=await client.read(()=>observed++);assert.equal(observed,1);assert.equal(view.snapshotSequence,kind==='snapshot'?4:3);assert.equal(adapter.metrics.posts,1);
 }
});
test('literal witness is synchronous explicit true; a promise or arbitrary raw proof cannot authorize stop',async()=>{
 const {adapter,client}=make('limited');await post(client,'deadline-limited-retains-provisional-vectors');adapter.attestLogicalStop=async()=>true;let observed=0;await assert.rejects(client.read(()=>observed++),/logical_stop_unconfirmed/);assert.equal(observed,0);
});
test('opaque source key and semantic equality stay separate; integer-valued coordinates do not borrow old JS hashes',async()=>{
 const {adapter,client}=make();await post(client,'admitted-without-upstream');assert.equal(client.current.request_key,c('admitted-without-upstream').post.response.request_key);
 const fetcher=adapter.fetcher;adapter.fetcher=async(path,options)=>{const reply=await fetcher(path,options);if(path.includes('/snapshot')){const page=await reply.json();page.request.origins[0].coordinate[0]+=.01;return Response.json(page);}return reply;};await assert.rejects(client.read(),/request mismatch/);assert.equal(adapter.metrics.posts,1);
});

test('unknown owned work from a stale read still blocks; superseding input does not erase a global hold',async()=>{
 const {adapter,client}=make();await post(client,'admitted-without-upstream');const fetcher=adapter.fetcher;let heldResolve;
 adapter.fetcher=async(path,options)=>path.includes('/events')?new Promise(r=>heldResolve=r):fetcher(path,options);
 const old=client.read();while(!heldResolve)await new Promise(r=>setImmediate(r));await post(client,'clear-while-held');heldResolve(Response.json({code:'upstream_outcome_unknown',engine_unknown:true,retryable:false},{status:503}));
 await assert.rejects(old,error=>error.ownershipUnknown===true);assert.equal(client.identity.session_id,'offline-session-0');assert.equal(adapter.metrics.posts,2);
});
test('fixture adapter refuses edited protocol objects instead of certifying arbitrary source receipts',()=>{
 const bad=structuredClone(fixture);bad.cases[0].post.response.request_key='f'.repeat(64);assert.throws(()=>createProtocolAdapter(bad),/Pinned protocol/);
});
