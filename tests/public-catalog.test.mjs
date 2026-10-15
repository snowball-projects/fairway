import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {loadPublicCatalog,validatePublicCatalog} from '../src/fairway/static/public-catalog.mjs';
import {PublicPlanningSession,resolvePublicOrigin} from '../src/fairway/static/public-planning.mjs';
import {catalogCounts} from '../src/fairway/static/catalog-read.mjs';

const release='a'.repeat(64);
const course=(id,longitude=0)=>({course_id:`c-${id}`,facility_id:'f-one',name:id,facility_name:'One',nonmember_bookable:true,plan_eligible:true,access:'public',arrival:null,destination_id:null,map_location:{latitude:0,longitude},round_options:[{round_holes:9}],physical_holes:9,fact_groups:[]});
function fixture(){
  const value={format_version:1,schema:4,revision:758,catalog_release_key:release,facilities:[{facility_id:'f-one',name:'One',course_ids:['c-first','c-second']}],courses:[course('first'),course('second',10)],destinations:[]};
  return {value,manifest:{format_version:1,schema:4,revision:758,catalog_release_key:release,counts:{facilities:1,courses:2,destinations:0}}};
}
function transport(change=()=>{}){
  const {value,manifest}=fixture();change(value,manifest);
  const raw=JSON.stringify(value),hash=createHash('sha256').update(raw).digest('hex');
  manifest.files={'catalog.json':{path:`native-catalog-${hash}.json`,sha256:hash,bytes:Buffer.byteLength(raw)}};
  const calls=[];
  return {manifest,raw,calls,fetcher:async(url,options)=>{calls.push({url:String(url),options});return new Response(calls.length===1?JSON.stringify(manifest):raw);}};
}
test('immutable load resolves within a Pages subpath and uses only two credential-free GETs',async()=>{
  const t=transport();const model=await loadPublicCatalog('https://example.test/fairway/data/catalog-release.json',t);
  assert.equal(model.revision,758);assert.equal(model.courses.length,2);
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
  if(defect==='relationship')value.facilities[0].course_ids.pop();
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
  const {value,manifest}=fixture();value.courses.push(...Array.from({length:100},(_,i)=>course(`extra-${i}`)));value.facilities[0].course_ids=value.courses.map(c=>c.course_id);manifest.counts.courses=102;
  const session=new PublicPlanningSession();session.setCatalog(validatePublicCatalog(value,manifest));
  const origins=[{id:'one',coordinate:[0,0]},{id:'two',coordinate:[0,10]}];
  assert.equal(session.update(origins),true);assert.equal(session.courseCards().length,102);assert.equal(session.update(origins),false);
  assert.ok(session.courseCards().every(c=>c.status==='unavailable'&&c.rank===null&&c.maximum_seconds===null&&c.travel_times_seconds.every(t=>t===null)));
  assert.equal(session.hasAdmitted,false);assert.equal(session.active,null);assert.deepEqual(session.areas,[]);
  session.update(origins.slice(0,1));assert.equal(session.courseCards().length,101);
  session.update([]);assert.equal(session.courseCards().length,0);
});
test('radius/access/round edits retain nulls and apply documented filters',()=>{
  const {value,manifest}=fixture();value.courses[0].plan_eligible=false;value.courses[0].nonmember_bookable=null;
  const session=new PublicPlanningSession();session.setCatalog(validatePublicCatalog(value,manifest));session.update([{id:'one',coordinate:[0,0]}]);
  assert.equal(session.cards.length,0);session.accessChanged('all');assert.equal(session.cards.length,1);
  session.update(session.origins,'maximum',[18]);assert.equal(session.cards.length,0);
  assert.throws(()=>session.radiusChanged(NaN));assert.throws(()=>session.update([{id:'one',coordinate:[91,0]}]));
});
test('address lookup has an injected deterministic transport and no private route',async()=>{
  let call;const value=await resolvePublicOrigin('committed address',{fetcher:async(url,options)=>{call={url,options};return {ok:true,json:async()=>({features:[]})};}});
  assert.deepEqual(value.features,[]);assert.equal(call.url.origin,'https://photon.komoot.io');assert.equal(call.url.searchParams.get('q'),'committed address');assert.equal(call.options.credentials,'omit');
});
test('frozen 758 export preserves real full-pool identities, map denominator and sparse observations',()=>{
  const raw=gunzipSync(readFileSync(new URL('../data/catalog-release/catalog.json.gz',import.meta.url)));
  const manifest=JSON.parse(readFileSync(new URL('../data/catalog-release/manifest.json',import.meta.url)));
  assert.equal(createHash('sha256').update(raw).digest('hex'),manifest.files['catalog.json'].sha256);
  const value=JSON.parse(raw),model=validatePublicCatalog(value,manifest);
  assert.equal(model.facilities.length,7387);assert.equal(model.courses.length,3641);assert.equal(model.destinations.size,2144);
  assert.deepEqual(catalogCounts(model.facilities),{total:7387,onMap:4640,pending:2747});
  assert.equal(new Set([...model.facilities,...model.courses].flatMap(r=>r.fact_groups||[]).map(g=>g.id)).size,4794);
  assert.ok(model.courses.some(c=>c.name===null&&c.nonmember_bookable===null));
  assert.ok(model.facilities.some(f=>!f.course_ids.length));
});
