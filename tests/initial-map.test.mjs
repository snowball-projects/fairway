import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {loadInitialMap,loadPublicCatalog,validateInitialMap} from '../src/fairway/static/public-catalog.mjs';
import {catalogCounts,searchCatalog} from '../src/fairway/static/catalog-read.mjs';
import {fixture} from './native5-fixture.mjs';
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const base='https://example.test/fairway/data/catalog-release.json';
function transport(){
 const {value,manifest}=fixture(),full=JSON.stringify(value),sha=hash(full);
 manifest.files={'catalog.json':{sha256:sha,bytes:Buffer.byteLength(full),path:`native-catalog-${sha}.json`}};
 const index={map_format:1,revision:manifest.revision,catalog_release_key:manifest.catalog_release_key,catalog_sha256:sha,counts:manifest.counts,
  facilities:value.facilities.map(f=>[f.facility_id,f.name,f.state,f.address?.city??null,f.map_location?[f.map_location.latitude,f.map_location.longitude,f.map_location.kind]:null]),
  states:[{id:'IL',state:'IL',name:'Illinois',d:'M0,0L1,1Z'}]};
 const raw=JSON.stringify(index),mapSHA=hash(raw);
 manifest.files['initial-map.json']={sha256:mapSHA,bytes:Buffer.byteLength(raw),path:`initial-map-${mapSHA}.json`};
 const calls=[];
 const fetcher=async(url,options)=>{calls.push({url:String(url),options});return new Response(String(url)===base?JSON.stringify(manifest):String(url).includes('/initial-map-')?raw:full);};
 return {value,manifest,index,raw,full,fetcher,calls};
}
test('map/search loads only small index; detail request stays pinned without another manifest GET',async()=>{
 const t=transport(),map=await loadInitialMap(base,t);
 assert.equal(t.calls.length,2);assert.match(t.calls[1].url,/\/fairway\/data\/initial-map-/);
 assert.deepEqual(catalogCounts(map.facilities),catalogCounts(t.value.facilities));
 assert.deepEqual(searchCatalog(map.facilities,map.states,'Illinois').map(r=>r.kind),['state']);
 assert.equal(map.counts.courses,t.value.courses.length);
 // A deployment changes the mutable manifest between map and detail requests.
 const pinned=structuredClone(map.manifest);t.manifest.revision++;
 const full=await loadPublicCatalog(base,{fetcher:t.fetcher,pinnedManifest:pinned});
 assert.equal(t.calls.length,3);assert.equal(full.revision,map.revision);
 assert.equal(full.courses.length,map.counts.courses);
 assert.ok(t.calls.every(c=>c.options.credentials==='omit'));
 assert.deepEqual(t.calls.map(c=>c.options.cache),['no-cache','force-cache','force-cache']);
});
for(const defect of ['revision','release','catalog-sha','count','duplicate','latitude','kind','shape','states'])test(`map rejects ${defect} before pins`,()=>{
 const t=transport(),v=t.index;
 if(defect==='revision')v.revision++;
 if(defect==='release')v.catalog_release_key='b'.repeat(64);
 if(defect==='catalog-sha')v.catalog_sha256='b'.repeat(64);
 if(defect==='count')v.counts={...v.counts,courses:v.counts.courses+1};
 if(defect==='duplicate')v.facilities[1]=v.facilities[0];
 if(defect==='latitude')v.facilities[0][4]=[91,0,'property_point'];
 if(defect==='kind')v.facilities[0][4]=[0,0,'invented'];
 if(defect==='shape')v.facilities[0].push('unexpected');
 if(defect==='states')v.states.push(v.states[0]);
 assert.throws(()=>validateInitialMap(v,t.manifest));
});
test('cached wrong-version map bytes and later wrong-version details fail checksums without fallback',async()=>{
 for(const phase of ['map','details']){
  const t=transport();
  if(phase==='map')await assert.rejects(loadInitialMap(base,{fetcher:async(url,o)=>String(url).includes('/initial-map-')?new Response(t.raw+' '):t.fetcher(url,o)}),/checksum/);
  else {const map=await loadInitialMap(base,t);await assert.rejects(loadPublicCatalog(base,{pinnedManifest:map.manifest,fetcher:async()=>new Response(t.full+' ')}),/checksum/);}
 }
});
test('same-length cached map tampering is rejected by SHA independently of size and shape',async()=>{
 const t=transport(),name=t.index.facilities[0][1],changed=(name.startsWith('X')?'Y':'X')+name.slice(1);
 const tampered=t.raw.replace(JSON.stringify(name),JSON.stringify(changed));
 assert.equal(Buffer.byteLength(tampered),Buffer.byteLength(t.raw));
 assert.doesNotThrow(()=>validateInitialMap(JSON.parse(tampered),t.manifest));
 await assert.rejects(loadInitialMap(base,{fetcher:async(url,o)=>String(url).includes('/initial-map-')?new Response(tampered):t.fetcher(url,o)}),/checksum/);
});
test('missing/misdirected/oversized initial index cannot fall back to the complete catalog',async()=>{
 for(const defect of ['missing','path','size']){
  const t=transport();if(defect==='missing')delete t.manifest.files['initial-map.json'];
  if(defect==='path')t.manifest.files['initial-map.json'].path='../map.json';
  if(defect==='size')t.manifest.files['initial-map.json'].bytes=4*1024*1024+1;
  await assert.rejects(loadInitialMap(base,t),/map manifest/);assert.equal(t.calls.length,1);
 }
});
test('interrupted or stalled index never publishes a partial map and cancels its body',async()=>{
 for(const mode of ['abort','deadline','oversize']){
  const t=transport(),controller=new AbortController();let cancelled=false;
  const fetcher=async(url,o)=>{
   if(String(url)===base)return t.fetcher(url,o);
   return new Response(new ReadableStream({start(stream){stream.enqueue(new Uint8Array(mode==='oversize'?4*1024*1024+1:10));if(mode==='abort')setTimeout(()=>controller.abort(),0);},cancel(){cancelled=true;}}));
  };
  await assert.rejects(loadInitialMap(base,{fetcher,signal:controller.signal,timeoutMs:20}));assert.equal(cancelled,true);
 }
});
test('interrupted details can retry against same immutable release and retain complete relationships',async()=>{
 const t=transport(),map=await loadInitialMap(base,t),controller=new AbortController();controller.abort();
 await assert.rejects(loadPublicCatalog(base,{fetcher:t.fetcher,pinnedManifest:map.manifest,signal:controller.signal}));
 assert.equal(t.calls.length,2);
 const full=await loadPublicCatalog(base,{fetcher:t.fetcher,pinnedManifest:map.manifest});
 for(const f of full.facilities)assert.deepEqual([...f.course_ids].sort(),full.facilityCourses(f.facility_id).map(c=>c.course_id).sort());
});
