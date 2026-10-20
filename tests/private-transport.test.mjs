import test from 'node:test';
import assert from 'node:assert/strict';
import facility from './fixtures/catalog-native/facility-corica-example.json' with {type:'json'};
import empty from './fixtures/catalog-native/facility-empty-cog-hill-example.json' with {type:'json'};
import course from './fixtures/catalog-native/course-corica-research21-example.json' with {type:'json'};
import sequence from './fixtures/sqlite-preparation-sequence.json' with {type:'json'};
import {createNativeCatalogAdapter} from './fixtures/native-catalog-adapter.mjs';
import {PrivateTransport,TransportError} from '../src/fairway/static/private-transport.mjs';
import {preparationRequestKey} from '../src/fairway/static/preparation-dto.mjs';
const authorization={allowed:true,caller:'offline-reviewer'},clone=structuredClone;
const client=(fetcher)=>new PrivateTransport({mode:'offline-deterministic',authorization,fetcher,sleep:async()=>{}});
const step=sequence.steps[0];
function fakePreparation({partial=false,alter=null,cursorExpired=false,snapshotConflict=false}={}) {
  const calls=[];let poll=0,conflicted=false;
  const request=partial?sequence.large_pool.partial_24_scored.request:step.request;
  const source=partial?sequence.large_pool.partial_24_scored:step.frames.at(-1).snapshot;
  const fetcher=async(path,options)=>{
    calls.push({path,method:options.method});
    if(options.authorization?.caller!==authorization.caller || options.authorization?.allowed!==true)return Response.json({code:'unauthorized',engine_unknown:false,operation_started:false},{status:401});
    const url=new URL(path,'https://reserved.invalid');
    const key=await preparationRequestKey(request),generation=7,revision=source.catalog_revision,session='offline-session-0001';
    const binding={session_id:session,generation,request_key:key,catalog_revision:revision,cursor:1,snapshot_sequence:source.snapshot_sequence,events:[]};
    if(options.method==='POST')return Response.json({...binding,cursor:0,operation_started:true});
    if(url.pathname.endsWith('/events')) {
      poll++;
      const result={...binding,terminal:{fairway_reservation_cleared:true,native_admission_released:false,evidence:{basis:'offline-fake-clear'}}};
      if(alter)alter(result,'events');
      if(cursorExpired&&poll===1)return Response.json({code:'cursor_expired',latest:result},{status:409});
      return Response.json(result);
    }
    const snapshot=clone(source);Object.assign(snapshot,{generation,request:clone(request),request_key:key,preparation_limited:partial,area_search_complete:!partial});
    snapshot.offset=Number(url.searchParams.get('offset'));snapshot.limit=1000;snapshot.has_more=false;
    if(snapshotConflict&&!conflicted){conflicted=true;return Response.json({code:'snapshot_changed',latest:{...binding,snapshot_sequence:source.snapshot_sequence+1}},{status:409});}
    snapshot.snapshot_sequence=Number(url.searchParams.get('expected_snapshot_sequence'));
    if(alter)alter(snapshot,'snapshot');
    return Response.json(snapshot);
  };
  return {fetcher,calls,request};
}
test('real binding and unauthenticated callers are rejected before a read',()=>{
  assert.throws(()=>new PrivateTransport({fetcher:fetch,mode:'real',authorization}),/not reviewed/);
  assert.throws(()=>new PrivateTransport({fetcher:fetch,mode:'offline-deterministic',authorization:{allowed:false}}),/unauthorized/);
});
test('native course/facility examples have one consistent revision, three cards and no invented empty-facility courses',async()=>{
  const adapter=createNativeCatalogAdapter({facilityExamples:[facility,empty],courseExample:course});
  const read=await adapter.transport.readCatalog();assert.equal(read.revision,21);assert.equal(read.facilities.length,2);assert.equal(read.courses.length,3);
  assert.equal(read.facilityCourses(empty.facilities[0].facility_id).length,0);assert.equal(read.destinations.size,1);
  assert.ok(read.courses.every(c=>c.arrival===null));assert.equal(adapter.metrics.posts,0);
});
test('revision conflicts restart only complete catalog reads without POST',async()=>{
  const adapter=createNativeCatalogAdapter({facilityExamples:[facility,empty],courseExample:course});let fail=true,posts=0;
  const read=await client(async(path,options)=>{if(options.method==='POST')posts++;if(path.includes('/courses')&&fail){fail=false;return Response.json({code:'catalog_revision_changed'},{status:409});}return adapter.transport.fetcher(path,options);}).readCatalog();
  assert.equal(read.courses.length,3);assert.equal(adapter.metrics.reads,3);assert.equal(posts,0);
});
test('malformed short pages never masquerade as a full catalog',async()=>{
  await assert.rejects(client(async()=>Response.json({...facility,limit:1000,total:2,has_more:false})).readCatalog(),/invalid_catalog_page/);
});
test('immutable preparation reads restart expired cursor and snapshot token without budget-resetting POST',async()=>{
  const fake=fakePreparation({cursorExpired:true,snapshotConflict:true});const views=[];
  const outcome=await client(fake.fetcher).prepare(fake.request,7,view=>views.push(view));
  assert.equal(views.length,1);assert.equal(views[0].rows().length,4);assert.equal(outcome.native_admission_released,false);
  assert.equal(fake.calls.filter(c=>c.method==='POST').length,1);assert.equal(fake.calls.filter(c=>c.path.includes('/snapshot')).length,2);
});
test('finite limited preparation keeps all100 rows and24 integer complete vectors, distinct from fatal provider errors',async()=>{
  const fake=fakePreparation({partial:true});let view;
  await client(fake.fetcher).prepare(fake.request,7,value=>view=value);
  assert.equal(view.preparationLimited,true);assert.equal(view.areaSearchComplete,false);assert.equal(view.rows().length,100);
  assert.equal(view.rows().filter(r=>r.maximum_milliseconds!==null).length,24);assert.equal(view.summary.ranking_complete,false);
  assert.equal(fake.calls.filter(c=>c.method==='POST').length,1);
});
test('missing status, wrong ownership binding, forged terminal and inconsistent full summary fail visibly',async()=>{
  for(const alter of [(s,k)=>{if(k==='snapshot')delete s.preparation_limited;},(s,k)=>{if(k==='events')s.session_id='different-session';},(s,k)=>{if(k==='events')s.terminal.native_admission_released=true;},(s,k)=>{if(k==='snapshot')s.prepared_count=0;}]){
    const fake=fakePreparation({alter});await assert.rejects(client(fake.fetcher).prepare(fake.request,7,()=>{}));assert.equal(fake.calls.filter(c=>c.method==='POST').length,1);
  }
});
test('unknown global journal overrides predispatch-looking retry and no retries happen automatically',async()=>{
  for(const unknown of [false,true]){let calls=0;
    const transport=client(async()=>{calls++;return Response.json({code:'busy',operation_started:false,retryable:true,engine_unknown:unknown},{status:503,headers:{'Retry-After':'10'}});});
    await assert.rejects(transport.prepare(step.request,7,()=>{}),error=>error instanceof TransportError&&error.retryable===!unknown&&error.unknown===unknown);assert.equal(calls,1);
  }
});
test('invalid or incomplete origins and unreviewed request fields dispatch nothing',async()=>{
  let calls=0;const transport=client(async()=>{calls++;});
  for(const request of [{...step.request,origins:[]},{...step.request,origins:[{id:'a',coordinate:[null,-88]}]},{...step.request,origins:[{id:'a',coordinate:[42,-88],label:'extra'}]},{...step.request,radius_km:1000},{...step.request,continuation:true}])await assert.rejects(transport.prepare(request,7,()=>{}),/invalid_preparation_request/);
  assert.equal(calls,0);
});
test('observer failure cannot confer admission release',async()=>{
  const fake=fakePreparation();await assert.rejects(client(fake.fetcher).prepare(fake.request,7,()=>{throw Error('UI failed');}),error=>error.code==='observer_failed'&&error.unknown===true);
});

test('operation_started:false without an explicit known journal does not grant retry or release',async()=>{
  const transport=client(async()=>Response.json({code:'busy',operation_started:false,retryable:true},{status:503,headers:{'Retry-After':'10'}}));
  await assert.rejects(transport.prepare(step.request,7,()=>{}),error=>error.retryable===false&&error.neverStarted===false);
});

test('fake-authorized session and catalog reads reject another caller without provider work',async()=>{
  const fake=fakePreparation();
  const other=new PrivateTransport({mode:'offline-deterministic',authorization:{allowed:true,caller:'another-reviewer'},fetcher:fake.fetcher});
  await assert.rejects(other.prepare(fake.request,7,()=>{}),error=>error.code==='unauthorized'&&error.neverStarted===true&&error.retryable===false);
  assert.equal(fake.calls.length,1);
  const adapter=createNativeCatalogAdapter({facilityExamples:[facility,empty],courseExample:course});
  const read=new PrivateTransport({mode:'offline-deterministic',authorization:{allowed:true,caller:'another-reviewer'},fetcher:adapter.transport.fetcher});
  await assert.rejects(read.readCatalog(),/unauthorized/);assert.equal(adapter.metrics.reads,0);assert.equal(adapter.metrics.posts,0);
});

test('snapshot conflict cannot roll an event67 view back to17, negative tokens or an earlier restart binding',async()=>{
  const source=sequence.large_pool.fully_prepared,request=source.request,key=await preparationRequestKey(request);
  for(const tokens of [[17],[-1],[66],[68,67]]) {
    const calls=[],views=[];let index=0;
    const binding={session_id:'regression-session-0001',generation:7,request_key:key,catalog_revision:source.catalog_revision,cursor:1,snapshot_sequence:source.snapshot_sequence,events:[],terminal:{fairway_reservation_cleared:true,native_admission_released:false,evidence:{basis:'offline-fake-clear'}}};
    const fetcher=async(path,options)=>{
      calls.push({path,method:options.method});
      if(options.method==='POST')return Response.json({...binding,cursor:0,operation_started:true});
      if(path.includes('/events'))return Response.json(binding);
      if(index<tokens.length)return Response.json({code:'snapshot_changed',latest:{...binding,snapshot_sequence:tokens[index++]}},{status:409});
      const snapshot=clone(sequence.large_pool.partial_24_scored);Object.assign(snapshot,{generation:7,request,request_key:key,limit:1000,has_more:false,preparation_limited:true,area_search_complete:false});return Response.json(snapshot);
    };
    await assert.rejects(client(fetcher).prepare(request,7,(view,result)=>views.push([view.snapshotSequence,result.snapshot_sequence])),error=>error.code==='invalid_snapshot_restart'&&error.unknown===true);
    assert.equal(views.length,0);assert.equal(calls.filter(c=>c.method==='POST').length,1);assert.equal(calls.filter(c=>c.path.includes('/snapshot')).length,tokens.length);
  }
});
test('invalid terminal never reaches the observer or a final snapshot read, while observer failure keeps unknown semantics',async()=>{
  for(const alter of [(s,k)=>{if(k==='events')s.terminal.native_admission_released=true;},(s,k)=>{if(k==='events')s.terminal.fairway_reservation_cleared=false;},(s,k)=>{if(k==='events')s.terminal.evidence.basis='untrusted';}]){
    const fake=fakePreparation({alter});let paints=0;
    await assert.rejects(client(fake.fetcher).prepare(fake.request,7,()=>paints++),error=>error.code==='terminal_clear_unconfirmed'&&error.unknown===true);
    assert.equal(paints,0);assert.equal(fake.calls.filter(c=>c.path.includes('/snapshot')).length,0);assert.equal(fake.calls.filter(c=>c.method==='POST').length,1);
  }
  const valid=fakePreparation();let paints=0;await assert.rejects(client(valid.fetcher).prepare(valid.request,7,()=>{paints++;throw Error('observer failed');}),error=>error.code==='observer_failed'&&error.unknown===true);assert.equal(paints,1);
});
