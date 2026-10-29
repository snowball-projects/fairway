import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../src/fairway/static/app.js',import.meta.url),'utf8');
function actual(name){
 const syncStart=source.indexOf(`function ${name}(`);
 const start=source.slice(syncStart-6,syncStart)==="async "?syncStart-6:syncStart;
 for(let end=source.indexOf('\n}',start);end>=0;end=source.indexOf('\n}',end+2)){
  const code=source.slice(start,end+2);try{new vm.Script(code);return code;}catch{}
 }
 throw Error(name);
}
function harness(){
 const controls={'catalog-status':{hidden:true,textContent:''}},calls=[];let resolve,reject;
 const ctx=vm.createContext({catalogModel:null,initialMap:{manifest:{revision:981}},detailsRequest:null,deferredSelection:null,catalogURL:'https://example.test/data/catalog-release.json',
  performance:{mark(){}},$:id=>controls[id],loadPublicCatalog:(url,options)=>{calls.push({url,options});return new Promise((yes,no)=>{resolve=yes;reject=no;});},applyCatalog:next=>{ctx.catalogModel=next;},renderCourses:()=>{},setDrawer:()=>{},
 });
 for(const name of ['ensureCatalog','selectFacilityById','selectCoincidentFacilities'])vm.runInContext(actual(name),ctx);
 return {ctx,controls,calls,resolve:next=>resolve(next),reject:()=>reject(Error('Interrupted'))};
}
test('early interaction waits for pinned map release and concurrent detail requests coalesce',async()=>{
 const h=harness();h.ctx.initialMap=null;h.ctx.ensureCatalog();assert.equal(h.calls.length,0);
 h.ctx.initialMap={manifest:{revision:981}};h.ctx.ensureCatalog();h.ctx.ensureCatalog();
 assert.equal(h.calls.length,1);assert.equal(h.calls[0].options.pinnedManifest,h.ctx.initialMap.manifest);
 assert.match(h.controls['catalog-status'].textContent,/Loading course details/);
 h.resolve({revision:981});await h.ctx.detailsRequest;assert.equal(h.ctx.catalogModel.revision,981);
});
test('latest pending selection wins without fake course rows, then replays only after details load',async()=>{
 const h=harness(),selected=[];
 h.ctx.selectFacilityById('f-first');h.ctx.selectFacilityById('f-latest');assert.equal(h.calls.length,1);assert.equal(h.ctx.catalogModel,null);
 h.ctx.selectFacilityById=id=>selected.push(id);h.resolve({revision:981});await h.ctx.detailsRequest;
 assert.deepEqual(selected,['f-latest']);assert.equal(h.ctx.deferredSelection,null);
});
test('failure retains the map and pinned identity, clears pending work, and permits explicit retry',async()=>{
 const h=harness(),index=h.ctx.initialMap;
 h.ctx.ensureCatalog();h.reject();await h.ctx.detailsRequest;
 assert.equal(h.ctx.catalogModel,null);assert.equal(h.ctx.initialMap,index);assert.equal(h.ctx.detailsRequest,null);
 assert.match(h.controls['catalog-status'].textContent,/Course details unavailable/);
 h.ctx.ensureCatalog();assert.equal(h.calls.length,2);assert.equal(h.calls[1].options.pinnedManifest,index.manifest);
 h.resolve({revision:981});await h.ctx.detailsRequest;
});
test('closing Courses cancels pending selection even while Plan remains open',async()=>{
 const h=harness(),selected=[];
 const panel=()=>({hidden:false,contains:()=>false,setAttribute(){},focus(){}});
 Object.assign(h.controls,{'plan-panel':panel(),'courses-grip':panel(),'plan-toggle':panel()});
 h.ctx.view={resultsPanel:panel(),appShell:{classList:{toggle(){}}}};
 Object.assign(h.ctx,{document:{activeElement:null},mobile:()=>false,coursesDrawer:null,setFilterOpen:()=>{}});
 for(const name of ['setDrawer','detailPanelsChanged'])vm.runInContext(actual(name),h.ctx);
 h.ctx.selectFacilityById('f-pending');assert.equal(h.calls.length,1);
 assert.equal(h.controls['plan-panel'].hidden,false);
 h.ctx.setDrawer('courses',false);h.ctx.detailPanelsChanged();
 assert.equal(h.ctx.deferredSelection,null);assert.equal(h.ctx.view.resultsPanel.hidden,true);
 h.ctx.selectFacilityById=id=>{selected.push(id);h.ctx.setDrawer('courses',true);};
 h.resolve({revision:981});await h.ctx.detailsRequest;
 assert.deepEqual(selected,[]);assert.equal(h.ctx.view.resultsPanel.hidden,true);assert.equal(h.controls['plan-panel'].hidden,false);
});
test('pin fits its verified index point immediately and latest selection replays without a second fit',async()=>{
 const h=harness(),fits=[],selected=[];
 h.ctx.initialMap.mapRecords=[{facility_id:'f-first',map_location:{latitude:41,longitude:-88}},{facility_id:'f-last',map_location:{latitude:42,longitude:-89}}];
 Object.assign(h.ctx,{located:f=>Boolean(f.map_location),fitPoints:(points,zoom,animate)=>fits.push({points,zoom,animate}),mobile:()=>false,REDUCED_MOTION:true});
 h.ctx.selectFacilityById('f-first');h.ctx.selectFacilityById('f-last');
 assert.deepEqual(JSON.parse(JSON.stringify(fits)),[{points:[[41,-88]],zoom:15,animate:false},{points:[[42,-89]],zoom:15,animate:false}]);
 assert.equal(h.calls.length,1);assert.equal(h.ctx.catalogModel,null);
 h.ctx.selectFacilityById=(id,fit)=>selected.push({id,fit});h.resolve({revision:981});await h.ctx.detailsRequest;
 assert.deepEqual(selected,[{id:'f-last',fit:false}]);assert.equal(fits.length,2);
});
test('drawer opens before synchronous index fit and a later camera start cancels pending selection',async()=>{
 const h=harness(),events={},order=[],selected=[];let open=false;
 h.ctx.initialMap.mapRecords=[{facility_id:'f-pin',map_location:{latitude:41,longitude:-88}}];
 Object.assign(h.ctx,{map:{on:(names,handler)=>{for(const name of names.split(' '))events[name]=handler;}},located:()=>true,
  setDrawer:(which,value)=>{open=value;order.push('drawer');},fitPoints:(points,zoom,animate)=>{assert.equal(open,true);assert.equal(animate,false);events.movestart();order.push('fit');}});
 vm.runInContext(source.slice(source.indexOf('map.on("movestart zoomstart"'),source.indexOf('map.on("moveend zoomend"')),h.ctx);
 h.ctx.selectFacilityById('f-pin');assert.deepEqual(order,['drawer','fit']);assert.ok(h.ctx.deferredSelection);
 events.movestart();assert.equal(h.ctx.deferredSelection,null);
 h.ctx.selectFacilityById=id=>selected.push(id);h.resolve({revision:981});await h.ctx.detailsRequest;assert.deepEqual(selected,[]);
});
test('initial and detail failures state the unavailable data without instructions',()=>{
 const h=harness();vm.runInContext(actual('catalogLoadMessage'),h.ctx);
 h.ctx.initialMap=null;h.controls['catalog-status'].textContent='Catalog unavailable.';
 assert.equal(h.ctx.catalogLoadMessage(),'Catalog unavailable.');
 h.controls['catalog-status'].textContent='Loading…';assert.match(h.ctx.catalogLoadMessage(),/Catalog is still loading/);
 h.ctx.initialMap={manifest:{revision:981}};h.controls['catalog-status'].textContent='Course details unavailable.';
 assert.match(h.ctx.catalogLoadMessage(),/Course details unavailable/);
});
test('a pan before detail readiness follows the new viewport without publishing course rows',()=>{
 const h=harness();let frame,renders=0;
 Object.assign(h.ctx,{viewportFrame:null,planningMode:false,browseMode:false,browseScope:{ids:['f-old']},requestAnimationFrame:fn=>{frame=fn;return 1;},renderCourses:()=>renders++});
 vm.runInContext(actual('refreshBrowseViewport'),h.ctx);h.ctx.refreshBrowseViewport();frame();
 assert.equal(h.ctx.browseScope.kind,'viewport');assert.equal(h.ctx.browseScope.ids,undefined);assert.equal(renders,0);
});

test('initial map paint starts background details with both panels closed',async()=>{
 const h=harness();let frame,timer;const order=[];
 Object.assign(h.ctx,{loadInitialMap:async()=>({states:[],manifest:{}}),geometry:null,
  drawFacilities:()=>order.push('draw'),renderProgress:()=>{},performance:{mark:()=>order.push('mark')},
  requestAnimationFrame:fn=>{frame=fn;},setTimeout:fn=>{timer=fn;},
  view:{resultsPanel:{hidden:true}},planningMode:false,browseMode:true});
 vm.runInContext(actual('loadCatalog'),h.ctx);await h.ctx.loadCatalog();
 assert.deepEqual(order,['draw','mark']);assert.equal(h.calls.length,0);
 frame();assert.equal(h.calls.length,0);timer();assert.equal(h.calls.length,1);
 h.resolve({revision:981});await h.ctx.detailsRequest;
});

test('map dot opens the drawer then centres at zoom 13 and selects without refitting',()=>{
 const h=harness(),events=[];
 Object.assign(h.ctx,{setDrawer:(...args)=>events.push(['drawer',...args]),
  map:{setView:(...args)=>events.push(['camera',...args])},selectFacilityById:(...args)=>events.push(['select',...args])});
 vm.runInContext(actual('selectMapDot'),h.ctx);
 const point={lat:41,lng:-88};h.ctx.selectMapDot(['f-one'],point);
 assert.deepEqual(JSON.parse(JSON.stringify(events)),[['drawer','courses',true,false],['camera',point,13,{animate:false}],['select','f-one',false]]);
});

test('colocated map selection centres at zoom 13 before opening the complete chooser',()=>{
 const h=harness(),events=[],ids=['f-one','f-two'],point={lat:41,lng:-88};
 Object.assign(h.ctx,{setDrawer:(...args)=>events.push(['drawer',...args]),map:{setView:(...args)=>events.push(['camera',...args])},
  selectCoincidentFacilities:(...args)=>events.push(['chooser',...args]),selectFacilityById:()=>assert.fail('must not replace chooser with one record')});
 vm.runInContext(actual('selectMapDot'),h.ctx);h.ctx.selectMapDot(ids,point);
 assert.deepEqual(JSON.parse(JSON.stringify(events)),[['drawer','courses',true,false],['camera',point,13,{animate:false}],['chooser',ids,point]]);
});
