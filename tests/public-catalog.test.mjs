import test from 'node:test';
import assert from 'node:assert/strict';
import {loadPublicCatalog} from '../src/fairway/static/public-catalog.mjs';
import {PublicPlanningSession,resolvePublicOrigin} from '../src/fairway/static/public-planning.mjs';
import {CatalogRead} from '../src/fairway/static/catalog-read.mjs';
import {fixture} from './native5-fixture.mjs';
const course=(id,longitude=0)=>({course_id:`c-${id}`,facility_id:'f-one',name:id,facility_name:'One',nonmember_bookable:true,plan_eligible:true,access:'public',arrival:null,destination_id:null,map_location:{latitude:0,longitude},round_options:[{round_holes:9}],physical_holes:9});
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

test('browser details use response.json and preserve object references without cloning',async()=>{
 const {value}=fixture();const calls=[];
 const manifest={files:{'browser-details.json':{path:'browser-details-hash.json'}}};
 const model=await loadPublicCatalog('https://example.test/fairway/data/catalog-release.json',{fetcher:async url=>{
  calls.push(String(url));return {ok:true,json:async()=>calls.length===1?manifest:value};
 }});
 assert.deepEqual(calls,['https://example.test/fairway/data/catalog-release.json','https://example.test/fairway/data/browser-details-hash.json']);
 assert.equal(model.facilities,value.facilities);assert.equal(model.courses,value.courses);
 assert.equal(model.facilityById.get(value.facilities[0].facility_id),value.facilities[0]);
 assert.equal(model.destinations.get(value.destinations[0].id),value.destinations[0]);
});
test('HTTP errors retain normal unavailable presentation',async()=>{
 await assert.rejects(loadPublicCatalog('https://example.test/data/catalog-release.json',{fetcher:async()=>new Response('no',{status:503})}),/unavailable/);
});
