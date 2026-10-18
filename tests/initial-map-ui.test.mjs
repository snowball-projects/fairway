import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../src/fairway/static/app.js',import.meta.url),'utf8');
function actual(name){
 const start=source.indexOf(`function ${name}(`);
 for(let end=source.indexOf('\n}',start);end>=0;end=source.indexOf('\n}',end+2)){
  const code=source.slice(start,end+2);try{new vm.Script(code);return code;}catch{}
 }
 throw Error(name);
}
function harness(){
 const controls={'catalog-status':{hidden:true,textContent:''}},calls=[];let resolve,reject;
 const ctx=vm.createContext({catalogModel:null,initialMap:{manifest:{revision:981}},detailsRequest:null,deferredSelection:null,catalogURL:'https://example.test/data/catalog-release.json',
  $:id=>controls[id],loadPublicCatalog:(url,options)=>{calls.push({url,options});return new Promise((yes,no)=>{resolve=yes;reject=no;});},applyCatalog:next=>{ctx.catalogModel=next;},renderCourses:()=>{},setDrawer:()=>{},
 });
 for(const name of ['ensureCatalog','selectFacilityById','selectCoincidentFacilities'])vm.runInContext(actual(name),ctx);
 return {ctx,controls,calls,resolve:next=>resolve(next),reject:()=>reject(Error('Interrupted'))};
}
test('early interaction waits for verified map identity and concurrent detail requests coalesce',async()=>{
 const h=harness();h.ctx.initialMap=null;h.ctx.ensureCatalog();assert.equal(h.calls.length,0);
 h.ctx.initialMap={manifest:{revision:981}};h.ctx.ensureCatalog();h.ctx.ensureCatalog();
 assert.equal(h.calls.length,1);assert.equal(h.calls[0].options.pinnedManifest,h.ctx.initialMap.manifest);
 assert.match(h.controls['catalog-status'].textContent,/Loading course details/);
 h.resolve({revision:981});await h.ctx.detailsRequest;assert.equal(h.ctx.catalogModel.revision,981);
});
test('latest pending selection wins without fake course rows, then replays only after full validation',async()=>{
 const h=harness(),selected=[];
 h.ctx.selectFacilityById('f-first');h.ctx.selectFacilityById('f-latest');assert.equal(h.calls.length,1);assert.equal(h.ctx.catalogModel,null);
 h.ctx.selectFacilityById=id=>selected.push(id);h.resolve({revision:981});await h.ctx.detailsRequest;
 assert.deepEqual(selected,['f-latest']);assert.equal(h.ctx.deferredSelection,null);
});
test('failure retains the map and pinned identity, clears pending work, and permits explicit retry',async()=>{
 const h=harness(),index=h.ctx.initialMap;
 h.ctx.ensureCatalog();h.reject();await h.ctx.detailsRequest;
 assert.equal(h.ctx.catalogModel,null);assert.equal(h.ctx.initialMap,index);assert.equal(h.ctx.detailsRequest,null);
 assert.match(h.controls['catalog-status'].textContent,/unavailable.*retry/);
 h.ctx.ensureCatalog();assert.equal(h.calls.length,2);assert.equal(h.calls[1].options.pinnedManifest,index.manifest);
 h.resolve({revision:981});await h.ctx.detailsRequest;
});
