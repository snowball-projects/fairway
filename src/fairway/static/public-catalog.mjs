import {CatalogRead,validIdentity,mapRecords} from './catalog-read.mjs';
import {validateScopedOptional} from './optional-facts.mjs';
const MAX_BYTES=64*1024*1024;
const digest=async bytes=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
export function validatePublicCatalog(value,manifest){
  if(value?.format_version!==2||value.schema!==5||!Number.isSafeInteger(value.revision)||value.revision<0||! /^[a-f0-9]{64}$/.test(value.catalog_release_key)||['format_version','revision','schema','catalog_release_key'].some(k=>value[k]!==manifest[k]))throw new Error('Published catalog identity mismatch');
  for(const kind of ['facilities','courses','destinations'])if(!Array.isArray(value[kind])||value[kind].length!==manifest.counts?.[kind]||new Set(value[kind].map(r=>r[kind==='facilities'?'facility_id':kind==='courses'?'course_id':'id'])).size!==value[kind].length)throw new Error('Published catalog count or identity mismatch');
  const observations=validateScopedOptional(value);
  const model=new CatalogRead(value);model.catalogReleaseKey=value.catalog_release_key;model.sourceLicenses=value.source_licenses||[];
  model.optionalObservations=structuredClone(observations);model.provenance=structuredClone(value.provenance);model.relationships=structuredClone(value.relationships);
  const byFacility=new Map();for(const c of model.courses){const ids=byFacility.get(c.facility_id)||[];ids.push(c.course_id);byFacility.set(c.facility_id,ids);}
  for(const f of model.facilities){const actual=(byFacility.get(f.facility_id)||[]).sort();if(!Array.isArray(f.course_ids)||JSON.stringify([...f.course_ids].sort())!==JSON.stringify(actual))throw new Error('Published course relationships mismatch');}
  return model;
}
// Race injected transports too: a stalled response must not outlive the deadline.
async function abortable(work,signal){
  let onAbort;
  const aborted=new Promise((_,reject)=>{
    onAbort=()=>reject(signal.reason);
    if(signal.aborted)onAbort();else signal.addEventListener('abort',onAbort,{once:true});
  });
  try{return await Promise.race([aborted,work]);}
  finally{signal.removeEventListener('abort',onAbort);}
}
function cancelBody(body){
  // A producer's throwing/rejecting/pending cancellation hook cannot hold cleanup up.
  try{body?.cancel()?.catch(()=>{});}catch{}
}
async function readBounded(url,max,fetcher,signal,cache='no-cache'){
  signal.throwIfAborted();
  const pending=Promise.resolve(fetcher(url,{credentials:'omit',cache,mode:'same-origin',signal})).then(response=>{
    if(signal.aborted){cancelBody(response.body);throw signal.reason;}
    return response;
  });
  const response=await abortable(pending,signal);
  let reader,complete=false;
  try{
    signal.throwIfAborted();
    if(!response.ok)throw new Error('Published catalog unavailable');
    const declared=Number(response.headers?.get?.('content-length'));
    if(declared>max)throw new Error('Published catalog too large');
    reader=response.body?.getReader();
    if(!reader)throw new Error('Published catalog body unavailable');
    let buffer=new Uint8Array(Math.min(16384,max)),size=0,reads=0;
    while(true){
      const {done,value}=await abortable(reader.read(),signal);
      if(done){complete=true;break;}
      const next=size+value.byteLength;
      if(next>max)throw new Error('Published catalog too large');
      if(next>buffer.length){
        const grown=new Uint8Array(Math.min(max,Math.max(next,buffer.length*2)));
        grown.set(buffer.subarray(0,size));buffer=grown;
      }
      buffer.set(value,size);size=next;
      // Empty/tiny synchronous chunks must not starve the deadline's timer task.
      if(++reads%1024===0)await abortable(new Promise(resolve=>setTimeout(resolve,0)),signal);
    }
    const bytes=buffer.subarray(0,size);
    return {text:new TextDecoder('utf-8',{fatal:true}).decode(bytes),bytes};
  }finally{
    if(!complete){
      cancelBody(reader||response.body);
    }
    reader?.releaseLock();
  }
}
async function loadPublished(manifestURL,{fetcher=globalThis.fetch,signal,timeoutMs=30000,pinnedManifest}={},initialMap=false){
  const deadline=new AbortController();
  const timer=setTimeout(()=>deadline.abort(new DOMException('Published catalog timed out','TimeoutError')),timeoutMs);
  const combined=signal?AbortSignal.any([signal,deadline.signal]):deadline.signal;
  try{
    combined.throwIfAborted();
    const base=new URL(manifestURL),read=(url,max)=>readBounded(url,max,fetcher,combined);
    const manifest=pinnedManifest??JSON.parse((await read(base,16384)).text),file=manifest.files?.['catalog.json'];
    if(manifest.format_version!==2||manifest.schema!==5||!file||!Number.isSafeInteger(file.bytes)||file.bytes<2||file.bytes>MAX_BYTES||! /^[a-f0-9]{64}$/.test(file.sha256)||file.path!==`native-catalog-${file.sha256}.json`)throw new Error('Invalid published catalog manifest');
    const selected=initialMap?manifest.files['initial-map.json']:file,max=initialMap?4*1024*1024:MAX_BYTES;
    if(!selected||!Number.isSafeInteger(selected.bytes)||selected.bytes<2||selected.bytes>max||! /^[a-f0-9]{64}$/.test(selected.sha256)||selected.path!==`${initialMap?'initial-map':'native-catalog'}-${selected.sha256}.json`)throw new Error('Invalid published map manifest');
    const url=new URL(selected.path,base);if(url.origin!==base.origin||url.pathname.substring(0,url.pathname.lastIndexOf('/'))!==base.pathname.substring(0,base.pathname.lastIndexOf('/')))throw new Error('Invalid catalog location');
    // Hash-addressed bytes are immutable. Always revalidate the mutable manifest,
    // but allow HTTP cache reuse here; every cached byte is still hashed below.
    const raw=await readBounded(url,max,fetcher,combined,'force-cache');if(raw.bytes.length!==selected.bytes||await digest(raw.bytes)!==selected.sha256)throw new Error('Published catalog checksum mismatch');
    combined.throwIfAborted();
    if(initialMap)return {...validateInitialMap(JSON.parse(raw.text),manifest),manifest};
    return validatePublicCatalog(JSON.parse(raw.text),manifest);
  }finally{clearTimeout(timer);}
}
export const loadPublicCatalog=(url,options)=>loadPublished(url,options);
export const loadInitialMap=(url,options)=>loadPublished(url,options,true);

export function validateInitialMap(value,manifest){
  if(manifest.format_version!==2||manifest.schema!==5||value?.map_format!==2||!Number.isSafeInteger(value.revision)||value.revision<0||! /^[a-f0-9]{64}$/.test(value.catalog_release_key)||value.revision!==manifest.revision||value.catalog_release_key!==manifest.catalog_release_key||value.catalog_sha256!==manifest.files?.['catalog.json']?.sha256)throw new Error('Published map identity mismatch');
  if(!Array.isArray(value.facilities)||value.facilities.length!==manifest.counts?.facilities||['facilities','courses','destinations'].some(k=>!Number.isSafeInteger(value.counts?.[k])||value.counts[k]<0||value.counts[k]!==manifest.counts[k]))throw new Error('Published map counts mismatch');
  const ids=new Set(),nullableText=v=>v===null||typeof v==='string';
  const facilities=value.facilities.map(row=>{
    if(!Array.isArray(row)||row.length!==5)throw new Error('Invalid map facility');
    const [facility_id,name,state,city,point]=row;
    if(typeof facility_id!=='string'||!validIdentity(facility_id,'f-')||ids.has(facility_id)||!nullableText(name)||!nullableText(state)||!nullableText(city))throw new Error('Invalid map facility identity');
    ids.add(facility_id);
    if(point!==null&&(!Array.isArray(point)||point.length!==3||!Number.isFinite(point[0])||Math.abs(point[0])>90||!Number.isFinite(point[1])||Math.abs(point[1])>180||!['property_point','reviewed_osm_point','verified_entrance','address_range_estimate'].includes(point[2])))throw new Error('Invalid map location');
    return {facility_id,name,state,address:city===null?null:{city},map_location:point===null?null:{latitude:point[0],longitude:point[1],kind:point[2]}};
  });
  if(!Array.isArray(value.courses)||value.courses.length>manifest.counts.courses)throw new Error('Invalid map courses');
  const courses=value.courses.map(row=>{
    if(!Array.isArray(row)||row.length!==5)throw new Error('Invalid map course');
    const [course_id,name,state,city,point]=row;
    if(!validIdentity(course_id,'c-')||ids.has(course_id)||!nullableText(name)||!nullableText(state)||!nullableText(city))throw new Error('Invalid map course identity');
    ids.add(course_id);
    if(point!==null&&(!Array.isArray(point)||point.length!==3||!Number.isFinite(point[0])||Math.abs(point[0])>90||!Number.isFinite(point[1])||Math.abs(point[1])>180||!['property_point','reviewed_osm_point','verified_entrance','address_range_estimate'].includes(point[2])))throw new Error('Invalid map course location');
    return {course_id,facility_id:null,name,state,address:city===null?null:{city},map_location:point===null?null:{latitude:point[0],longitude:point[1],kind:point[2]}};
  });
  if(!Array.isArray(value.states)||new Set(value.states.map(s=>s.id)).size!==value.states.length||value.states.some(s=>typeof s.id!=='string'||typeof s.name!=='string'||typeof s.d!=='string'||typeof s.state!=='string'))throw new Error('Invalid map states');
  return {facilities,courses,mapRecords:mapRecords({facilities,courses}),states:value.states,counts:value.counts,revision:value.revision};
}
