import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {gunzipSync} from 'node:zlib';
import {loadPublicCatalog,validatePublicCatalog} from '../src/fairway/static/public-catalog.mjs';
import {PublicPlanningSession,resolvePublicOrigin} from '../src/fairway/static/public-planning.mjs';
import {catalogCounts} from '../src/fairway/static/catalog-read.mjs';

import {CatalogRead} from '../src/fairway/static/catalog-read.mjs';
import {fixture} from './native5-fixture.mjs';
const course=(id,longitude=0)=>({course_id:`c-${id}`,facility_id:'f-one',name:id,facility_name:'One',nonmember_bookable:true,plan_eligible:true,access:'public',arrival:null,destination_id:null,map_location:{latitude:0,longitude},round_options:[{round_holes:9}],physical_holes:9});
function transport(change=()=>{}){
  const {value,manifest}=fixture();change(value,manifest);
  const raw=JSON.stringify(value),hash=createHash('sha256').update(raw).digest('hex');
  manifest.files={'catalog.json':{path:`native-catalog-${hash}.json`,sha256:hash,bytes:Buffer.byteLength(raw)}};
  const calls=[];
  return {manifest,raw,calls,fetcher:async(url,options)=>{calls.push({url:String(url),options});return new Response(calls.length===1?JSON.stringify(manifest):raw);}};
}
test('immutable load resolves within a Pages subpath and uses only two credential-free GETs',async()=>{
  const t=transport();const model=await loadPublicCatalog('https://example.test/fairway/data/catalog-release.json',t);
  assert.equal(model.revision,2);assert.equal(model.courses.length,3);
  assert.deepEqual(t.calls.map(c=>new URL(c.url).pathname),['/fairway/data/catalog-release.json',`/fairway/data/${t.manifest.files['catalog.json'].path}`]);
  assert.ok(t.calls.every(c=>c.options.credentials==='omit'&&c.options.mode==='same-origin'&&!c.options.body));
});
test('changed payload fails closed without legacy fallback or retry',async()=>{
  const t=transport();const original=t.fetcher;t.fetcher=async(url,options)=>{const r=await original(url,options);return t.calls.length===2?new Response(t.raw+' '):r;};
  await assert.rejects(loadPublicCatalog('https://example.test/fairway/data/catalog-release.json',t),/checksum/);
  assert.equal(t.calls.length,2);
});
for(const defect of ['revision','release','count','duplicate','relationship','orphan','unknown'])test(`reject native ${defect} mismatch`,()=>{
  const {value,manifest}=fixture();
  if(defect==='revision')value.revision++;
  if(defect==='release')value.catalog_release_key='b'.repeat(64);
  if(defect==='count')manifest.counts.courses++;
  if(defect==='duplicate')value.courses[1]=structuredClone(value.courses[0]);
  if(defect==='relationship')value.facilities.find(f=>f.course_ids.length).course_ids.pop();
  if(defect==='orphan')value.courses[0].facility_id='f-missing';
  if(defect==='unknown')value.courses[0].nonmember_bookable=undefined;
  assert.throws(()=>validatePublicCatalog(value,manifest));
});
for(const path of ['../elsewhere.json','https://evil.test/catalog.json','/catalog.json'])test(`reject manifest path ${path}`,async()=>{
  const t=transport();t.manifest.files['catalog.json'].path=path;
  await assert.rejects(loadPublicCatalog('https://example.test/fairway/data/catalog-release.json',t),/manifest/);assert.equal(t.calls.length,1);
});
test('HTTP and declared oversized responses stop without fallback',async()=>{
  for(const response of [new Response('no',{status:503}),new Response('{}',{headers:{'content-length':'99999999'}})]){
    let calls=0;await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',{fetcher:async()=>{calls++;return response;}}));assert.equal(calls,1);
  }
});
test('committed origins select every nearby course across both neighborhoods without routing',()=>{
  const model=new CatalogRead({revision:2,facilities:[{facility_id:'f-one'}],courses:[course('first'),course('second',10),...Array.from({length:100},(_,i)=>course(`extra-${i}`))]});
  const session=new PublicPlanningSession();session.setCatalog(model);
  const origins=[{id:'one',coordinate:[0,0]},{id:'two',coordinate:[0,10]}];
  assert.equal(session.update(origins),true);assert.equal(session.courseCards().length,102);assert.equal(session.update(origins),false);
  assert.ok(session.courseCards().every(c=>c.status==='unavailable'&&c.rank===null&&c.maximum_seconds===null&&c.travel_times_seconds.every(t=>t===null)));
  assert.equal(session.hasAdmitted,false);assert.equal(session.active,null);assert.deepEqual(session.areas,[]);
  session.update(origins.slice(0,1));assert.equal(session.courseCards().length,101);
  session.update([]);assert.equal(session.courseCards().length,0);
});
test('radius/access/round edits retain nulls and apply documented filters',()=>{
  const item={...course('unknown'),plan_eligible:false,nonmember_bookable:null};
  const session=new PublicPlanningSession();session.setCatalog(new CatalogRead({revision:2,facilities:[{facility_id:'f-one'}],courses:[item]}));session.update([{id:'one',coordinate:[0,0]}]);
  assert.equal(session.cards.length,0);session.accessChanged('all');assert.equal(session.cards.length,1);
  session.update(session.origins,'maximum',[18]);assert.equal(session.cards.length,0);
  assert.throws(()=>session.radiusChanged(NaN));assert.throws(()=>session.update([{id:'one',coordinate:[91,0]}]));
});
test('address lookup has an injected deterministic transport and no private route',async()=>{
  let call;const value=await resolvePublicOrigin('committed address',{fetcher:async(url,options)=>{call={url,options};return {ok:true,json:async()=>({features:[]})};}});
  assert.deepEqual(value.features,[]);assert.equal(call.url.origin,'https://photon.komoot.io');assert.equal(call.url.searchParams.get('q'),'committed address');assert.equal(call.options.credentials,'omit');
});
test('committed 1019 release validates complete typed scope and rejects old-schema fallback',()=>{
  const raw=gunzipSync(readFileSync(new URL('../data/catalog-release/catalog.json.gz',import.meta.url)));
  const manifest=JSON.parse(readFileSync(new URL('../data/catalog-release/manifest.json',import.meta.url)));
  assert.equal(createHash('sha256').update(raw).digest('hex'),manifest.files['catalog.json'].sha256);
  assert.equal(manifest.revision,1019);assert.equal(manifest.schema,5);assert.equal(manifest.format_version,2);
  assert.equal(manifest.files['catalog.json'].sha256,'19860e8fc34466dec3ab6fd20e8d269b87ce24c75bfe2d4bd46a3f98c2643b6b');
  const value=JSON.parse(raw),model=validatePublicCatalog(value,manifest);
  assert.throws(()=>validatePublicCatalog({...value,format_version:1,schema:4},{...manifest,format_version:1,schema:4}),/identity/);
  assert.equal(model.facilities.length,7430);assert.equal(model.courses.length,4747);assert.equal(model.destinations.size,2889);
  assert.deepEqual(catalogCounts(model.facilities),{total:7430,onMap:4640,pending:2790});
  assert.equal(model.optionalObservations.size,5014);
  const teal=model.courses.flatMap(c=>c.tee_sets).find(t=>t.id==='t-ddc5031b-f1b3-4519-8d5a-74d6bd8159cd');
  assert.equal(teal.rated_category,'W');assert.equal(teal.difficulty_rating,68.1);assert.equal(teal.slope,116);
  assert.equal(teal.yardage,null);assert.equal(teal.yardage_unit,null);
  const academy=model.facilities.find(f=>f.facility_id==='f-0129c277-d9de-4db0-b203-0d560081c668').optional.price_observation.filter(row=>row.fee_kind==='instruction'&&row.product_name?.startsWith('Bethpage'));
  assert.equal(academy.length,12);assert.ok(academy.every(row=>row.product_name.includes(' - ')&&!row.product_name.includes('\u2014')&&row.currency===null));
  assert.ok([...model.facilities,...model.courses].every(r=>!Object.hasOwn(r,'fact_groups')));
  assert.equal(model.provenance.notes.length,8286);assert.ok(model.provenance.notes.every(n=>Object.keys(n).length===1&&typeof n.id==='string'));
  assert.ok(model.courses.some(c=>c.name===null&&c.nonmember_bookable===null));
  assert.ok(model.facilities.some(f=>!f.course_ids.length));
});


test('streamed UTF8 chunks preserve original checksum bytes across split characters',async()=>{
 const t=transport(value=>value.source_licenses.push({source:'Équipe ⛳',license:'CC0-1.0',attribution:'Équipe ⛳'}));let reads=0;
 const model=await loadPublicCatalog('https://example.test/data/catalog-release.json',{fetcher:async()=>{
  const bytes=new TextEncoder().encode(++reads===1?JSON.stringify(t.manifest):t.raw);let offset=0;
  return new Response(new ReadableStream({pull(controller){if(offset===bytes.length)controller.close();else controller.enqueue(bytes.slice(offset,++offset));}}));
 }});
 assert.equal(model.sourceLicenses.at(-1).attribution,'Équipe ⛳');assert.equal(reads,2);
});
test('same-byte-length changed payload still fails the original checksum before validation',async()=>{
 const t=transport(),changed=t.raw.replace('Synthetic','Xynthetic');assert.notEqual(changed,t.raw);assert.equal(Buffer.byteLength(changed),Buffer.byteLength(t.raw));let count=0;
 await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',{fetcher:async()=>new Response(++count===1?JSON.stringify(t.manifest):changed)}),/checksum/);assert.equal(count,2);
});
test('declared payload size remains UTF8 bytes rather than UTF16 character count',async()=>{
 const t=transport(value=>value.source_licenses.push({source:'Équipe ⛳',license:'CC0-1.0',attribution:'Équipe ⛳'}));assert.ok(Buffer.byteLength(t.raw)>t.raw.length);t.manifest.files['catalog.json'].bytes=t.raw.length;
 await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',t),/checksum/);assert.equal(t.calls.length,2);
});

for(const declared of [null,'1'])test(`manifest streaming limit cancels excess bytes with content-length ${declared}`,async()=>{
 let pulled=0,cancelled=0,calls=0;
 const body=new ReadableStream({pull(controller){pulled++;controller.enqueue(new Uint8Array(1024));},cancel(){cancelled++;}});
 await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',{fetcher:async()=>{calls++;return new Response(body,{headers:declared?{'content-length':declared}:{}});}}),/too large/);
 assert.equal(calls,1);assert.equal(cancelled,1);assert.ok(pulled<=18);
});
test('catalog streaming limit cancels excess bytes before parsing or hashing',async()=>{
 const t=transport();let pulled=0,cancelled=0,calls=0;
 const body=new ReadableStream({pull(controller){pulled++;controller.enqueue(new Uint8Array(1024*1024));},cancel(){cancelled++;}});
 await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',{fetcher:async()=>++calls===1?new Response(JSON.stringify(t.manifest)):new Response(body)}),/too large/);
 assert.equal(calls,2);assert.equal(cancelled,1);assert.ok(pulled<=66);
});
for(const phase of ['headers','manifest','catalog'])test(`deadline terminates stalled ${phase} and cancels active streams`,async()=>{
 const t=transport();let calls=0,cancelled=0,signal;
 const stalled=()=>new Response(new ReadableStream({cancel(){cancelled++;return new Promise(()=>{});}}));
 await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',{timeoutMs:30,fetcher:async(url,options)=>{
  calls++;signal=options.signal;
  if(phase==='headers')return new Promise(()=>{});
  return phase==='catalog'&&calls===1?new Response(JSON.stringify(t.manifest)):stalled();
 }}),{name:'TimeoutError'});
 assert.equal(signal.aborted,true);assert.equal(calls,phase==='catalog'?2:1);assert.equal(cancelled,phase==='headers'?0:1);
});
test('caller cancellation terminates body consumption and pre-aborted loads make no requests',async()=>{
 const controller=new AbortController();let calls=0,cancelled=0;
 const pending=loadPublicCatalog('https://example.test/data/catalog-release.json',{signal:controller.signal,fetcher:async()=>{
  calls++;return new Response(new ReadableStream({pull(){controller.abort();},cancel(){cancelled++;}}));
 }});
 await assert.rejects(pending,{name:'AbortError'});assert.equal(cancelled,1);
 await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',{signal:controller.signal,fetcher:async()=>{calls++;}}),{name:'AbortError'});assert.equal(calls,1);
});
test('rejected HTTP bodies and declared oversize bodies are cancelled without reading',async()=>{
 for(const options of [{status:503},{headers:{'content-length':'99999999'}}]){
  let cancelled=false;
  await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',{fetcher:async()=>new Response(new ReadableStream({cancel(){cancelled=true;}}),options)}));
  assert.equal(cancelled,true);
 }
});
function abortAwareFetch(signals){return async(url,{signal})=>{
 signals.push(signal);signal.throwIfAborted();
 return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>resolve(new Response('{"features":[]}')),500);
  signal.addEventListener('abort',()=>{clearTimeout(timer);reject(signal.reason);},{once:true});
 });
};}
test('origin lookup composes caller cancellation and its deadline',async()=>{
 const signals=[],controller=new AbortController();
 const pending=resolvePublicOrigin('address',{signal:controller.signal,fetcher:abortAwareFetch(signals)});
 controller.abort();await assert.rejects(pending,{name:'AbortError'});assert.equal(signals[0].aborted,true);
 await assert.rejects(resolvePublicOrigin('address',{timeoutMs:20,fetcher:abortAwareFetch(signals)}),{name:'TimeoutError'});
 assert.equal(signals[1].aborted,true);
});
test('exact manifest byte limit succeeds and a finished load leaves its request signal active',async()=>{
 const t=transport();const manifest=JSON.stringify(t.manifest).padEnd(16384,' ');let calls=0,signal;
 const model=await loadPublicCatalog('https://example.test/data/catalog-release.json',{timeoutMs:50,fetcher:async(url,options)=>{signal=options.signal;return new Response(++calls===1?manifest:t.raw);}});
 assert.equal(model.revision,2);await new Promise(resolve=>setTimeout(resolve,60));assert.equal(signal.aborted,false);
});
test('invalid UTF8 fails closed instead of checksumming a replacement encoding',async()=>{
 const t=transport(),bytes=new Uint8Array([123,34,128]),hash=createHash('sha256').update(bytes).digest('hex');let calls=0;
 t.manifest.files['catalog.json']={bytes:bytes.length,sha256:hash,path:`native-catalog-${hash}.json`};
 await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',{fetcher:async()=>new Response(++calls===1?JSON.stringify(t.manifest):bytes)}),TypeError);
 assert.equal(calls,2);
});

test('a million empty chunks and reused one-byte buffers load within a bounded heap with exact checksum',()=>{
 const t=transport(value=>value.source_licenses.push({source:'Équipe ⛳',license:'CC0-1.0',attribution:'Équipe ⛳'}));
 const script=`
  import assert from 'node:assert/strict';
  import {loadPublicCatalog} from ${JSON.stringify(new URL('../src/fairway/static/public-catalog.mjs',import.meta.url).href)};
  const manifest=${JSON.stringify(t.manifest)},raw=${JSON.stringify(t.raw)};
  let calls=0,empty=1000000,offset=0;const bytes=new TextEncoder().encode(raw),one=new Uint8Array(1);
  const model=await loadPublicCatalog('https://example.test/data/catalog-release.json',{fetcher:async()=>{
   if(++calls===1)return new Response(JSON.stringify(manifest));
   return {ok:true,body:{getReader:()=>({async read(){
    if(empty-->0)return {done:false,value:new Uint8Array(0)};
    if(offset===bytes.length)return {done:true};
    one[0]=bytes[offset++];return {done:false,value:one};
   },cancel(){throw Error('Successful load must not cancel');},releaseLock(){}})}};
  }});
  assert.equal(model.sourceLicenses.at(-1).attribution,'Équipe ⛳');assert.equal(calls,2);
 `;
 const result=spawnSync(process.execPath,['--max-old-space-size=64','--input-type=module','--eval',script],{encoding:'utf8',timeout:20000,maxBuffer:1024*1024});
 assert.equal(result.error,undefined);assert.equal(result.status,0,result.stderr);
});
test('an endless stream of empty chunks still yields to the catalog deadline and cancels',async()=>{
 let cancelled=0,reads=0;
 await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',{timeoutMs:20,fetcher:async()=>({ok:true,body:{getReader:()=>({async read(){reads++;return {done:false,value:new Uint8Array(0)};},cancel(){cancelled++;return Promise.resolve();},releaseLock(){}})}})}),{name:'TimeoutError'});
 assert.ok(reads>0);assert.equal(cancelled,1);
});
for(const phase of ['manifest','catalog'])for(const reason of ['caller','deadline'])test(`late ${phase} response after ${reason} cancellation has its body cancelled`,async()=>{
 const t=transport(),controller=new AbortController();let release,calls=0,cancelled=0;
 const pending=loadPublicCatalog('https://example.test/data/catalog-release.json',{signal:controller.signal,timeoutMs:20,fetcher:async()=>{
  calls++;if(phase==='catalog'&&calls===1)return new Response(JSON.stringify(t.manifest));
  return new Promise(resolve=>{release=resolve;});
 }});
 // Let the first response finish before cancelling the second request.
 while(!release)await new Promise(resolve=>setImmediate(resolve));
 if(reason==='caller')controller.abort();
 await assert.rejects(pending,{name:reason==='caller'?'AbortError':'TimeoutError'});
 release(new Response(new ReadableStream({cancel(){cancelled++;return Promise.reject(Error('Cleanup failure'));}})));
 await new Promise(resolve=>setImmediate(resolve));assert.equal(cancelled,1);assert.equal(calls,phase==='catalog'?2:1);
});
test('a transport that aborts synchronously and returns a response still has its body cancelled',async()=>{
 const controller=new AbortController();let cancelled=0;
 await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',{signal:controller.signal,fetcher:()=>{
  controller.abort();return new Response(new ReadableStream({cancel(){cancelled++;}}));
 }}),{name:'AbortError'});
 assert.equal(cancelled,1);
});
