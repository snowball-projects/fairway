import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {loadInitialMap,loadPublicCatalog} from '../src/fairway/static/public-catalog.mjs';
import {catalogCounts,searchCatalog} from '../src/fairway/static/catalog-read.mjs';
import {fixture} from './native5-fixture.mjs';
import {publishedCatalog} from './catalog-model.mjs';
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const base='https://example.test/fairway/data/catalog-release.json';
function transport(){
 const {value,manifest}=fixture(),full=JSON.stringify(publishedCatalog(value)),sha=hash(full);
 manifest.files={'browser-details.json':{sha256:sha,bytes:Buffer.byteLength(full),path:`native-catalog-${sha}.json`}};
 const index={courses:[],map_format:3,revision:manifest.revision,catalog_release_key:manifest.catalog_release_key,catalog_sha256:sha,counts:manifest.counts,
  facilities:value.facilities.map(f=>[f.facility_id,f.name,f.state,f.address?.city??null,f.map_location?[f.map_location.latitude,f.map_location.longitude,f.map_location.kind]:null,f.physical_holes,value.courses.filter(c=>c.facility_id===f.facility_id).length,f.access]),
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
 for(const [i,record] of map.facilities.entries()) {
  assert.equal(record.physical_holes,t.value.facilities[i].physical_holes);
  assert.equal(record.course_count,t.value.courses.filter(c=>c.facility_id===record.facility_id).length);
  assert.equal(record.access,t.value.facilities[i].access);
 }
 // A deployment changes the mutable manifest between map and detail requests.
 const pinned=structuredClone(map.manifest);t.manifest.revision++;
 const full=await loadPublicCatalog(base,{fetcher:t.fetcher,pinnedManifest:pinned});
 assert.equal(t.calls.length,3);assert.equal(full.revision,map.revision);
 assert.equal(full.courses.length,map.counts.courses);

});
test('initial map retains null names and independent course markers without manufacturing facilities',async()=>{
 const t=transport();t.index.facilities[0][0]='osm/way/88';t.index.facilities[0][1]=null;
 t.index.courses=[['osm/way/99',null,null,null,[41,-88,'property_point'],9,1,'public']];
 const map=await loadInitialMap(base,{fetcher:async url=>new Response(String(url)===base?JSON.stringify(t.manifest):JSON.stringify(t.index))});
 assert.equal(map.facilities.length,t.value.facilities.length);
 assert.equal(map.facilities[0].name,null);
 assert.equal(map.mapRecords.length,map.facilities.length+1);
 assert.equal(map.mapRecords.at(-1).record_kind,'course');
 assert.equal(map.courses[0].facility_id,null);
});
