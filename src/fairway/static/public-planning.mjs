import {browseCard,courseMatches} from './catalog-read.mjs';
export const PUBLIC_PROTOCOL='public-catalog-only-v1';
export const distanceKm=([a,b],[c,d])=>{const r=Math.PI/180,x=(c-a)*r,y=(d-b)*r;return 12742.0176*Math.asin(Math.min(1,Math.sqrt(Math.sin(x/2)**2+Math.cos(a*r)*Math.cos(c*r)*Math.sin(y/2)**2)));};
// Browser-local catalog regions only. This object owns no routing work or admission.
export class PublicPlanningSession {
  constructor({notify=()=>{}}={}){Object.assign(this,{notify,transport:{protocol:PUBLIC_PROTOCOL},catalog:null,origins:[],objective:'maximum',holes:[9,18],radiusKilometers:32.18688,accessPolicy:'nonmember',cards:[],areas:[],phase:'entry',error:null,blocked:false,active:null,pending:null,posting:false,key:null,hasAdmitted:false,limited:false});}
  setCatalog(catalog){this.catalog=catalog;this.key=null;this.update(this.origins,this.objective,this.holes);}
  courseCards(){return this.cards;}
  invalidate(origins=[]){this.origins=structuredClone(origins);this.cards=[];this.areas=[];this.key=null;this.phase='entry';this.notify(this);}
  update(origins,objective=this.objective,holes=this.holes){
    if(!Array.isArray(origins)||origins.length>8||new Set(origins.map(o=>o.id)).size!==origins.length||origins.some(o=>typeof o.id!=='string'||!Array.isArray(o.coordinate)||o.coordinate.length!==2||!o.coordinate.every(Number.isFinite)||Math.abs(o.coordinate[0])>90||Math.abs(o.coordinate[1])>180)||!['maximum','combined'].includes(objective)||!Array.isArray(holes)||!holes.length||holes.some(h=>![9,18].includes(h)))throw new Error('Invalid committed origin');
    const key=JSON.stringify([this.catalog?.catalogReleaseKey??null,origins,objective,holes,this.radiusKilometers,this.accessPolicy]);if(key===this.key)return false;
    this.key=key;this.origins=structuredClone(origins);this.objective=objective;this.holes=[...holes];this.cards=[];this.phase=this.catalog?'catalog-only':'loading';
    if(this.catalog&&origins.length){
      for(const course of this.catalog.courses){
        const point=course.map_location;if(!point||!origins.some(o=>distanceKm(o.coordinate,[point.latitude,point.longitude])<=this.radiusKilometers))continue;
        if(!courseMatches(course,{access:this.accessPolicy,roundHoles:holes.length===1?String(holes[0]):'all'}))continue;
        this.cards.push({...browseCard(course,this.catalog.destinations),browseOnly:false,catalogOnly:true,rank:null,status:'unavailable',reason:'driving_times_unavailable',travel_times_seconds:origins.map(()=>null),travel_time_reasons:origins.map(()=>'unavailable')});
      }
    }
    this.notify(this);return true;
  }
  radiusChanged(value){if(!Number.isFinite(value)||value<=0||value>160)throw new Error('Invalid radius');this.radiusKilometers=value;return this.update(this.origins);}
  accessChanged(value){if(!['nonmember','all','public','private','restricted','unknown'].includes(value))throw new Error('Invalid access');this.accessPolicy=value;return this.update(this.origins);}
}
// Existing public Photon service, invoked only by the committed Enter/blur handler.
export async function resolvePublicOrigin(query,{fetcher=globalThis.fetch}={}){
  const url=new URL('https://photon.komoot.io/api/');url.search=new URLSearchParams({q:query,limit:'5',bbox:'-125,24,-66,50'});
  const response=await fetcher(url,{credentials:'omit',referrerPolicy:'no-referrer',signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error('Address lookup unavailable');const value=await response.json();if(!Array.isArray(value.features))throw new Error('Invalid address response');return value;
}
