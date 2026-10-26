import {recordLabel} from '../src/fairway/static/catalog-read.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {PublicPlanningSession} from '../src/fairway/static/public-planning.mjs';
import {renderKnownOptional} from '../src/fairway/static/optional-facts.mjs';
import {cityLabel,mapEligible,displayAddress,accessLabel} from '../src/fairway/static/catalog-read.mjs';
import {fixture,document} from './native5-fixture.mjs';
const source=readFileSync(new URL('../src/fairway/static/app.js',import.meta.url),'utf8');
function harness(resolveOrigin=async()=>({features:[]})){
  const row={input:{value:'A committed address'},coordinate:null,committedLabel:null,lookupPromise:null,controller:null};
  const commits=[],statuses=[],calls=[];
  const context={AbortController,state:{rows:[row],coreBounds:[24,-125,50,-66]},planningMode:true,planningSession:{error:null,key:'existing'},planningAdapter:{resolveOrigin:async (q,options)=>{calls.push({query:q,...options});return resolveOrigin(q,options);}},setOrigin:(r,label,coordinate)=>{commits.push(coordinate);r.coordinate=coordinate;r.committedLabel=label.trim();},setStatus:(...args)=>statuses.push(args),closeSuggestions:()=>{},address:()=>'',syncPlanning:()=>{},document:{createElement:()=>{throw Error('Multiple-choice DOM is outside this harness');}}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function parseCoordinate('),source.indexOf('function formatCoordinate('))+source.slice(source.indexOf('function looksLikeCoordinateInput('),source.indexOf('function duration('))+source.slice(source.indexOf('async function commitOrigin('),source.indexOf('function unusedColor(')),context);
  return {row,commits,statuses,calls,context,commit:trigger=>context.commitOrigin(row,trigger)};
}
test('actual Enter/blur coordinate commit stays local and deduplicates unchanged input',async()=>{
  const h=harness();h.row.input.value='41.1, -88.0';assert.equal(await h.commit('enter'),true);assert.equal(await h.commit('blur'),true);
  assert.equal(h.commits.length,1);assert.equal(h.calls.length,0);assert.deepEqual([...h.commits[0]],[41.1,-88]);
});
test('actual simultaneous Enter and blur share one lookup and commit',async()=>{
  let release;const h=harness(()=>new Promise(resolve=>{release=resolve;}));
  const enter=h.commit('enter'),blur=h.commit('blur');assert.equal(h.calls.length,1);
  release({features:[{geometry:{coordinates:[-88,41]}}]});assert.equal(await enter,true);assert.equal(await blur,true);assert.equal(h.commits.length,1);
});
for(const change of ['edit','removed'])test(`actual ${change} rejects stale lookup results`,async()=>{
  let release;const h=harness(()=>new Promise(resolve=>{release=resolve;}));const pending=h.commit('enter');
  if(change==='edit')h.row.input.value='A different address';else h.context.state.rows=[];
  release({features:[{geometry:{coordinates:[-88,41]}}]});assert.equal(await pending,false);assert.equal(h.commits.length,0);
});
test('invalid or out-of-core coordinate input never becomes an address lookup',async()=>{
  const h=harness();for(const input of ['91, 0','22, -88','', '1']){h.row.input.value=input;assert.equal(await h.commit('enter'),false);}assert.equal(h.calls.length,0);assert.equal(h.commits.length,0);
});
test('actual typing handler only invalidates local state',()=>{
  let invalidated=0,updated=0;
  const row={coordinate:[41,-88],committedLabel:'old',marker:{remove(){}},input:{}};
  const context={row,closeSuggestions:()=>{},updatePlan:()=>updated++,planningSession:{invalidate:()=>invalidated++},committedOrigins:()=>[]};vm.createContext(context);
  const start=source.indexOf('  row.input.oninput = '),end=source.indexOf('  row.input.onkeydown = ',start);
  vm.runInContext(source.slice(start,end),context);row.input.oninput();assert.equal(row.coordinate,null);assert.equal(invalidated,1);assert.equal(updated,1);
});
test('clearing one origin commits the remaining neighborhood on Enter/blur without private admission flags',async()=>{
  const h=harness(),first=h.row,second={id:'two',coordinate:[42,-89],committedLabel:'42, -89',input:{value:'42, -89'}};
  Object.assign(first,{id:'one',coordinate:[41,-88],committedLabel:'41, -88'});first.input.value='41, -88';h.context.state.rows.push(second);
  const session=new PublicPlanningSession();session.setCatalog({catalogReleaseKey:'a'.repeat(64),destinations:new Map(),courses:[['one',41,-88],['two',42,-89]].map(([id,latitude,longitude])=>({course_id:`c-${id}`,facility_id:`f-${id}`,name:id,facility_name:id,plan_eligible:true,nonmember_bookable:true,access:'public',map_location:{latitude,longitude},destination_id:null,arrival:null}))});
  const origins=()=>h.context.state.rows.filter(r=>r.coordinate).map(r=>({id:r.id,coordinate:r.coordinate}));
  h.context.planningSession=session;h.context.committedOrigins=origins;h.context.syncPlanning=()=>session.update(origins());h.context.updatePlan=()=>{};h.context.row=first;
  session.update(origins());assert.equal(session.cards.length,2);assert.equal(session.hasAdmitted,false);assert.equal(session.posting,false);
  const start=source.indexOf('  row.input.oninput = '),end=source.indexOf('  row.input.onkeydown = ',start);vm.runInContext(source.slice(start,end),h.context);
  first.input.value='';first.input.oninput();assert.equal(session.cards.length,0);
  assert.equal(await h.commit('enter'),false);assert.deepEqual(session.cards.map(c=>c.id),['c-two']);assert.equal(session.origins.length,1);
  assert.equal(await h.commit('blur'),false);assert.deepEqual(session.cards.map(c=>c.id),['c-two']);
  second.input.value='';second.coordinate=null;session.invalidate([]);await h.context.commitOrigin(second,'blur');assert.equal(session.cards.length,0);assert.equal(session.origins.length,0);assert.equal(h.calls.length,0);
});
test('public entry never imports a private or fake planning transport or reads raw optional payloads',()=>{
  assert.doesNotMatch(source,/logical-plan|assembly-plan|fixture-only|\.payload\b|priceFacts|comparablePrice/);
  assert.doesNotMatch(source,/fetch\([^)]*api\//);
});
test('actual popup facility details show known facility and owned-round scopes without unknown fields',()=>{
  const context={URL,document,renderKnownOptional:(o,options)=>renderKnownOptional(o,{...options,document}),selectableCourses:()=>[],activeFacility:null,planningMode:false,browseMode:true,cityLabel,mapEligible,displayAddress,accessLabel,recordLabel};vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function node('),source.indexOf('function mobile('))+source.slice(source.indexOf('function knownLink('),source.indexOf('function selectFacilityById(')),context);
  const f=fixture().value.facilities.find(f=>f.optional.amenity_observation.length),element=context.facilityDetails(f);
  assert.doesNotMatch(element.textContent,/Facility access unconfirmed|Unconfirmed|Not documented|unknown|not a current quote|Source license/);assert.match(element.textContent,/restaurant available Yes/);assert.match(element.textContent,/Documented paired 18/);assert.doesNotMatch(element.textContent,/driving range lighted|greens grass/);
});

for(const action of ['edit','remove','escape'])test(`actual ${action} handler aborts the active lookup transport`,async()=>{
 let seenSignal;
 const h=harness((query,{signal})=>new Promise((resolve,reject)=>{seenSignal=signal;signal.addEventListener('abort',()=>reject(signal.reason),{once:true});}));
 h.row.input.setAttribute=()=>{};h.row.input.removeAttribute=()=>{};h.row.suggestions={replaceChildren(){}};
 h.context.row=h.row;h.context.updatePlan=()=>{};h.context.committedOrigins=()=>[];h.context.planningSession.invalidate=()=>{};
 vm.runInContext(source.slice(source.indexOf('function closeSuggestions('),source.indexOf('function suggestionOptions(')),h.context);
 const pending=h.commit('enter');assert.equal(seenSignal.aborted,false);
 if(action==='edit'){
  const start=source.indexOf('  row.input.oninput = '),end=source.indexOf('  row.input.onkeydown = ',start);
  vm.runInContext(source.slice(start,end),h.context);h.row.input.value='Edited address';h.row.input.oninput();
 }else if(action==='remove'){
  h.context.state.rows.unshift({},{});Object.assign(h.context,{canRemoveOrigin:()=>true,element:{remove(){}},renumber(){},syncPlanning(){},fitCommittedOrigins(){},remove:{}});
  const start=source.indexOf('  remove.onclick = '),end=source.indexOf('  element.append(',start);
  vm.runInContext(source.slice(start,end),h.context);h.context.remove.onclick();
 }else{
  h.context.moveSuggestion=()=>false;
  const start=source.indexOf('  row.input.onkeydown = '),end=source.indexOf('  row.input.onblur = ',start);
  vm.runInContext(source.slice(start,end),h.context);h.row.input.onkeydown({key:'Escape'});
 }
 assert.equal(seenSignal.aborted,true);assert.equal(await pending,false);assert.equal(h.commits.length,0);assert.equal(h.statuses.length,0);
});
test('recommitting a different address cancels its superseded lookup',async()=>{
 const signals=[],h=harness((query,{signal})=>{signals.push(signal);return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(signal.reason),{once:true}));});
 h.context.closeSuggestions=(row,abort)=>{if(abort){row.controller?.abort();row.controller=null;row.lookupPromise=null;row.lookupQuery=null;}};
 const first=h.commit('enter');h.row.input.value='Another address';const second=h.commit('enter');
 assert.equal(signals[0].aborted,true);assert.equal(signals[1].aborted,false);assert.equal(await first,false);h.row.controller.abort();assert.equal(await second,false);
 assert.equal(h.commits.length,0);assert.equal(h.statuses.length,0);
});
