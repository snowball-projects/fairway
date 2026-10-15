import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../src/fairway/static/app.js',import.meta.url),'utf8');
function harness(resolveOrigin=async()=>({features:[]})){
  const row={input:{value:'A committed address'},coordinate:null,committedLabel:null,lookupPromise:null,controller:null};
  const commits=[],statuses=[],calls=[];
  const context={AbortController,state:{rows:[row],coreBounds:[24,-125,50,-66]},planningMode:true,planningSession:{error:null,key:'existing'},planningAdapter:{resolveOrigin:async q=>{calls.push(q);return resolveOrigin(q);}},setOrigin:(r,label,coordinate)=>{commits.push(coordinate);r.coordinate=coordinate;r.committedLabel=label.trim();},setStatus:(...args)=>statuses.push(args),closeSuggestions:()=>{},address:()=>'',syncPlanning:()=>{},document:{createElement:()=>{throw Error('Multiple-choice DOM is outside this harness');}}};
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
test('public entry never imports a private or fake planning transport or reads raw optional payloads',()=>{
  assert.doesNotMatch(source,/logical-plan|assembly-plan|fixture-only|\.payload\b|priceFacts|comparablePrice/);
  assert.doesNotMatch(source,/fetch\([^)]*api\//);
});
test('actual course details preserve typed tee unknowns and source scope without interpreting raw optional keys',()=>{
  class Element{constructor(tag){this.tag=tag;this.children=[];this.value='';}append(...nodes){this.children.push(...nodes);}set textContent(value){this.value=String(value);}get textContent(){return this.value+this.children.map(n=>typeof n==='string'?n:n.textContent).join(' ');}}
  const context={URL,STYLES:{regulation:'Regulation'},document:{createElement:tag=>new Element(tag)}};vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function node('),source.indexOf('function mobile('))+source.slice(source.indexOf('function courseMetadata('),source.indexOf('function renderRanking(')),context);
  const element=context.courseMetadata({style:'regulation',nonmember_bookable:null,round_options:[],tee_sets:[{name:'White',distance:null,distance_unit:null,difficulty_rating:71.2,slope:123}],fact_groups:[{module:'prices',course_id:'c-example',observed_on:null,collected_on:'2026-10-14',status:'extracted',conflict:true,source_url:'https://operator.example/fees',payload:{scalar_fee_alias:'DO_NOT_RENDER_RAW_99',amenity_alias:true}}]});
  assert.match(element.textContent,/Nonmember booking unconfirmed/);assert.match(element.textContent,/Not documented/);assert.match(element.textContent,/course difficulty rating \(not a quality rating\)/);assert.match(element.textContent,/123/);assert.match(element.textContent,/course observation.*conflicting/);assert.match(element.textContent,/Observed date unknown/);assert.doesNotMatch(element.textContent,/DO_NOT_RENDER_RAW_99|scalar fee alias|amenity alias/);
});
