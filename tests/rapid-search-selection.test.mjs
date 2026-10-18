import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../src/fairway/static/app.js',import.meta.url),'utf8');
function actual(name){
 const start=source.indexOf(`function ${name}(`);assert.ok(start>=0,name);
 for(let end=source.indexOf('\n}',start);end>=0;end=source.indexOf('\n}',end+2)){
  const code=source.slice(start,end+2);try{new vm.Script(code);return code;}catch{}
 }
 throw Error(name);
}
function harness(){
 let next=0;const frames=new Map(),events={},inputs={},applied=[],order=[];
 const ctx=vm.createContext({searchChoiceFrame:null,pendingSearchChoice:null,searchCameraActive:false,
  requestAnimationFrame:fn=>{const id=++next;frames.set(id,fn);return id;},cancelAnimationFrame:id=>frames.delete(id),
  applySearchChoice:result=>{applied.push(result);order.push(result.id);},closeSearch(){},
  document:{addEventListener:(name,fn)=>{inputs[name]=fn;}},$:id=>({addEventListener:(name,fn)=>{inputs[id+':'+name]=fn;}}),
  map:{on:(names,fn)=>{for(const name of names.split(' '))(events[name]??=[]).push(fn);},getContainer:()=>({addEventListener:(name,fn)=>{inputs['map:'+name]=fn;}})}
 });
 for(const name of ['cancelSearchChoice','scheduleSearchChoice','chooseSearch','bindSearchChoices'])vm.runInContext(actual(name),ctx);
 // The shipped viewport handler is registered before the search coordinator.
 ctx.map.on('moveend',()=>ctx.requestAnimationFrame(()=>order.push('old viewport')));
 ctx.bindSearchChoices();
 const fire=name=>{for(const f of events[name]||[])f();};
 const frame=()=>{const batch=[...frames];frames.clear();for(const [,fn] of batch)fn();};
 return {ctx,applied,order,inputs,fire,frame,frames};
}
test('rapid search choices during a normal animated zoom apply only the latest after the old viewport',()=>{
 const h=harness();h.fire('zoomstart');
 h.ctx.chooseSearch({id:'mapped'});h.frame();h.ctx.chooseSearch({id:'unmapped'});h.frame();h.ctx.chooseSearch({id:'empty'});h.frame();
 assert.deepEqual(h.applied,[]);h.fire('moveend');h.frame();
 assert.deepEqual(h.applied,[{id:'empty'}]);assert.deepEqual(h.order,['old viewport','empty']);h.frame();assert.equal(h.applied.length,1);
});
test('choices in one frame coalesce and a zoom beginning before that frame cannot consume the latest intent',()=>{
 const h=harness();h.ctx.chooseSearch({id:'first'});h.ctx.chooseSearch({id:'latest'});h.fire('zoomstart');h.frame();
 assert.equal(h.applied.length,0);h.fire('moveend');h.frame();assert.deepEqual(h.applied,[{id:'latest'}]);
});
test('without a pending zoom, including reduced-motion flow, a choice applies on the next frame',()=>{
 const h=harness();h.ctx.chooseSearch({id:'chosen'});h.frame();assert.deepEqual(h.applied,[{id:'chosen'}]);
});
for(const input of ['pointerdown','map:wheel','place-query:input','plan-toggle:click','courses-grip:click','keydown'])test('new user intent cancels queued search: '+input,()=>{
 const h=harness();h.fire('zoomstart');h.ctx.chooseSearch({id:'stale'});h.frame();
 h.inputs[input](input==='keydown'?{key:'Escape'}:{});h.fire('moveend');h.frame();assert.deepEqual(h.applied,[]);
 h.ctx.chooseSearch({id:'new'});h.frame();assert.deepEqual(h.applied,[{id:'new'}]);
});
