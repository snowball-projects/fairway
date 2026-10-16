import {CatalogRead} from './catalog-read.mjs';
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
export async function loadPublicCatalog(manifestURL,{fetcher=globalThis.fetch}={}){
  const base=new URL(manifestURL);const read=async(url,max)=>{const response=await fetcher(url,{credentials:'omit',cache:'no-cache',mode:'same-origin'});if(!response.ok)throw new Error('Published catalog unavailable');const declared=Number(response.headers?.get?.('content-length'));if(declared>max)throw new Error('Published catalog too large');const text=await response.text(),bytes=new TextEncoder().encode(text);if(bytes.length>max)throw new Error('Published catalog too large');return {text,bytes};};
  const manifest=JSON.parse((await read(base,16384)).text),file=manifest.files?.['catalog.json'];
  if(manifest.format_version!==2||manifest.schema!==5||!file||!Number.isSafeInteger(file.bytes)||file.bytes<2||file.bytes>MAX_BYTES||! /^[a-f0-9]{64}$/.test(file.sha256)||file.path!==`native-catalog-${file.sha256}.json`)throw new Error('Invalid published catalog manifest');
  const url=new URL(file.path,base);if(url.origin!==base.origin||url.pathname.substring(0,url.pathname.lastIndexOf('/'))!==base.pathname.substring(0,base.pathname.lastIndexOf('/')))throw new Error('Invalid catalog location');
  const raw=await read(url,MAX_BYTES);if(raw.bytes.length!==file.bytes||await digest(raw.bytes)!==file.sha256)throw new Error('Published catalog checksum mismatch');
  return validatePublicCatalog(JSON.parse(raw.text),manifest);
}
