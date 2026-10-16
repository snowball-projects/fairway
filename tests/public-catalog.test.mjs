import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
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
test('committed 856 release validates complete typed scope and rejects old-schema fallback',()=>{
  const raw=gunzipSync(readFileSync(new URL('../data/catalog-release/catalog.json.gz',import.meta.url)));
  const manifest=JSON.parse(readFileSync(new URL('../data/catalog-release/manifest.json',import.meta.url)));
  assert.equal(createHash('sha256').update(raw).digest('hex'),manifest.files['catalog.json'].sha256);
  assert.equal(manifest.revision,856);assert.equal(manifest.schema,5);assert.equal(manifest.format_version,2);
  assert.equal(manifest.files['catalog.json'].sha256,'d13bc28d5f8c076a1c46ff5a325bff922a1166571ed1a15cde6ebe632c68d594');
  const value=JSON.parse(raw),model=validatePublicCatalog(value,manifest);
  assert.throws(()=>validatePublicCatalog({...value,format_version:1,schema:4},{...manifest,format_version:1,schema:4}),/identity/);
  assert.equal(model.facilities.length,7430);assert.equal(model.courses.length,4336);assert.equal(model.destinations.size,2640);
  assert.deepEqual(catalogCounts(model.facilities),{total:7430,onMap:4640,pending:2790});
  assert.equal(model.optionalObservations.size,4826);
  assert.ok([...model.facilities,...model.courses].every(r=>!Object.hasOwn(r,'fact_groups')));
  assert.equal(model.provenance.notes.length,8286);assert.ok(model.provenance.notes.every(n=>Object.keys(n).length===1&&typeof n.id==='string'));
  assert.ok(model.courses.some(c=>c.name===null&&c.nonmember_bookable===null));
  assert.ok(model.facilities.some(f=>!f.course_ids.length));
});


test('loader reuses each bounded UTF8 body for byte length and checksum without redundant encodings',async()=>{
 const t=transport(value=>value.source_licenses.push({source:'Équipe ⛳',license:'CC0-1.0',attribution:'Équipe ⛳'})),bodies=[JSON.stringify(t.manifest),t.raw],Encoder=globalThis.TextEncoder,encodings=[];let reads=0;
 globalThis.TextEncoder=class extends Encoder{encode(text){encodings.push(text);return super.encode(text);}};
 try {
  const model=await loadPublicCatalog('https://example.test/data/catalog-release.json',{fetcher:async()=>({ok:true,headers:{get:()=>null},text:async()=>bodies[reads++]})});
  assert.equal(model.sourceLicenses.at(-1).attribution,'Équipe ⛳');assert.equal(reads,2);assert.deepEqual(encodings,bodies);
 }finally{globalThis.TextEncoder=Encoder;}
});
test('same-byte-length changed payload still fails the original checksum before validation',async()=>{
 const t=transport(),changed=t.raw.replace('Synthetic','Xynthetic');assert.notEqual(changed,t.raw);assert.equal(Buffer.byteLength(changed),Buffer.byteLength(t.raw));let count=0;
 await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',{fetcher:async()=>new Response(++count===1?JSON.stringify(t.manifest):changed)}),/checksum/);assert.equal(count,2);
});
test('declared payload size remains UTF8 bytes rather than UTF16 character count',async()=>{
 const t=transport(value=>value.source_licenses.push({source:'Équipe ⛳',license:'CC0-1.0',attribution:'Équipe ⛳'}));assert.ok(Buffer.byteLength(t.raw)>t.raw.length);t.manifest.files['catalog.json'].bytes=t.raw.length;
 await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',t),/checksum/);assert.equal(t.calls.length,2);
});
