import {CatalogRead,mapRecords} from './catalog-read.mjs';

async function readJSON(url,fetcher) {
  const response=await fetcher(url);
  if(!response.ok)throw new Error('Published catalog unavailable');
  return response.json();
}
async function loadPublished(manifestURL,{fetcher=globalThis.fetch,pinnedManifest}={},initialMap=false) {
  const base=new URL(manifestURL);
  const manifest=pinnedManifest??await readJSON(base,fetcher);
  const file=manifest.files[initialMap?'initial-map.json':'browser-details.json'];
  const value=await readJSON(new URL(file.path,base),fetcher);
  if(!initialMap)return new CatalogRead(value);
  const records=(rows,identity)=>rows.map(([id,name,state,city,point,physical_holes,course_count,access])=>({
    [identity]:id,physical_holes,course_count,access,...(identity==='course_id'?{facility_id:null}:{}),name,state,
    address:city===null?null:{city},
    map_location:point===null?null:{latitude:point[0],longitude:point[1],kind:point[2]},
  }));
  const facilities=records(value.facilities,'facility_id'),courses=records(value.courses,'course_id');
  return {facilities,courses,mapRecords:mapRecords({facilities,courses}),states:value.states,counts:value.counts,revision:value.revision,manifest};
}
export const loadPublicCatalog=(url,options)=>loadPublished(url,options);
export const loadInitialMap=(url,options)=>loadPublished(url,options,true);
