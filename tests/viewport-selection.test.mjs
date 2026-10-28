import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import vm from 'node:vm';
import {CatalogRead,browseCard,courseMatches,sortCourses,STYLES,located,mapEligible,catalogCounts,cityLabel,accessLabel,displayAddress,recordLabel} from '../src/fairway/static/catalog-read.mjs';
import {renderOptional,renderKnownOptional,OPTIONAL_DOMAINS} from '../src/fairway/static/optional-facts.mjs';
import {fixture} from './native5-fixture.mjs';
import {validatePublicCatalog} from '../src/fairway/static/public-catalog.mjs';
import {OPTIONAL_SCHEMA} from '../src/fairway/static/optional-schema.mjs';
const source=readFileSync(new URL('../src/fairway/static/app.js',import.meta.url),'utf8');
function actual(name){
  const start=source.indexOf(`function ${name}(`);assert.ok(start>=0,name);
  const firstLine=source.slice(start,source.indexOf('\n',start));try{new vm.Script(firstLine);return firstLine;}catch{}
  for(let end=source.indexOf('\n}',start);end>=0;end=source.indexOf('\n}',end+2)){
    const code=source.slice(start,end+2);try{new vm.Script(code);return code;}catch{}
  }
  throw Error('Cannot extract '+name);
}
class Element {
  constructor(tag,document){Object.assign(this,{tag,document,children:[],dataset:{},attrs:{},listeners:new Map(),value:'',hidden:false,style:{setProperty(k,v){this[k]=v;}}});this.classList={toggle:(name,yes)=>{const values=new Set((this.className||'').split(' ').filter(Boolean));yes?values.add(name):values.delete(name);this.className=[...values].join(' ');}};}
  append(...nodes){for(const node of nodes){node.remove?.();if(typeof node==='object')node.parent=this;this.children.push(node);}}
  insertBefore(node,before){if(node===before)return;node.remove();node.parent=this;const at=this.children.indexOf(before);this.children.splice(at<0?this.children.length:at,0,node);}
  replaceChildren(...nodes){for(const node of this.children)if(typeof node==='object')node.parent=null;this.children=[];this.value='';this.append(...nodes);}
  remove(){if(this.parent){this.parent.children.splice(this.parent.children.indexOf(this),1);this.parent=null;}}
  set textContent(value){this.replaceChildren();this.value=String(value);}
  get textContent(){return this.value+this.children.map(n=>typeof n==='string'?n:n.textContent).join(' ');}
  get firstElementChild(){return this.children[0]||null;}
  get lastElementChild(){return this.children.at(-1)||null;}
  setAttribute(k,v){this.attrs[k]=String(v);}
  addEventListener(t,fn){const f=this.listeners.get(t)||[];f.push(fn);this.listeners.set(t,f);}
  emit(t,event={}){for(const f of this.listeners.get(t)||[])f.call(this,event);}
  contains(n){return this===n||this.children.some(c=>typeof c==='object'&&c.contains(n));}
  matches(selector){return selector.startsWith('.')?(this.className||'').split(' ').includes(selector.slice(1)):selector.startsWith('[value=')?this.value===selector.slice(8,-2):this.tag===selector;}
  querySelectorAll(selector){const parts=selector.split(' '),matches=[];for(const c of this.children)if(typeof c==='object'){if(c.matches(parts[0])){if(parts.length===1)matches.push(c);else matches.push(...c.querySelectorAll(parts.slice(1).join(' ')));}matches.push(...c.querySelectorAll(selector));}return [...new Set(matches)];}
  querySelector(s){return this.querySelectorAll(s)[0]||null;}
  focus(){this.document.activeElement=this;}
}
const empty=()=>Object.fromEntries(OPTIONAL_DOMAINS.map(d=>[d,[]]));
function catalog(){
 const facilities=[['f-one','Shared facility',36,41,-88],['f-two','Other facility',18,42,-89]].map(([facility_id,name,physical_holes,latitude,longitude])=>({facility_id,name,state:'IL',physical_holes,access:null,website:null,address:null,map_location:{latitude,longitude,kind:'property_point'},optional:empty(),round_options:[]}));
 const courses=[['c-a','Bravo','f-one',41,-88],['c-b','Charlie','f-one',41.1,-88.1],['c-c','Alpha','f-two',42,-89]].map(([course_id,name,facility_id,latitude,longitude])=>({course_id,name,facility_id,facility_name:facilities.find(f=>f.facility_id===facility_id).name,state:'IL',physical_holes:18,access:null,nonmember_bookable:null,arrival:null,destination_id:null,map_location:{latitude,longitude},identity_status:'operator_defined',address:null,style:null,optional:empty(),round_options:[],components:[],tee_sets:[],website:null}));
 for(const f of facilities)f.course_inventory=courses.filter(c=>c.facility_id===f.facility_id).map(c=>({...c}));
 return new CatalogRead({revision:760,facilities,courses});
}
function harness(model=catalog()){
 const document={activeElement:null,createElement:tag=>new Element(tag,document)};
 const controls=Object.fromEntries(['browse-state','browse-access','browse-holes','browse-round','browse-style','browse-sort','browse-description','preparation-status'].map(id=>[id,document.createElement('div')]));
 for(const c of Object.values(controls))c.value='all';controls['browse-sort'].value='name';
 controls['courses-grip']=document.createElement('button');
 const nonmember=document.createElement('option');nonmember.value='nonmember';controls['browse-access'].append(nonmember);
 const view={results:document.createElement('div'),catalogName:document.createElement('span'),rankingDescription:document.createElement('p'),resultCount:document.createElement('span'),resultsPanel:{hidden:false}};
 const frames=[],events={},effects={fit:[],popups:0,draws:0,planning:0,render:0};let bounds=[40,-90,43,-87],openPopup=null;
 const map={getBounds:()=>({contains:p=>{const [lat,lng]=Array.isArray(p)?p:[p.lat,p.lng];return lat>=bounds[0]&&lat<=bounds[2]&&lng>=bounds[1]&&lng<=bounds[3];}}),on:(types,fn)=>{for(const t of types.split(' '))events[t]=fn;},closePopup:p=>{effects.closes=(effects.closes||0)+1;assert.ok(!p.closing,'must not close a popup during its close notification');p.closing=true;events.popupclose?.({popup:p});p.open=false;p.listeners.remove?.();p.closing=false;}};
 const L={latLng:(lat,lng)=>({lat,lng}),popup:options=>{effects.popups++;const p={options,listeners:{},setLatLng(c){this.coordinate=c;return this;},setContent(c){this.content=c;return this;},openOn(){this.open=true;openPopup=this;return this;},isOpen(){return this.open;},getElement(){return this.content;},on(t,fn){this.listeners[t]=fn;return this;}};return p;}};
 const ctx={URL,L,map,document,view,preparationFacilities:{clearLayers(){}},meetingLayer:{clearLayers(){}},STYLES,located,mapEligible,catalogCounts,cityLabel,accessLabel,displayAddress,recordLabel,browseCard,courseMatches,sortCourses,catalogModel:model,state:{activeCourse:null,activeRows:[],rows:[],ranking:null,routingCatalogLabel:'Catalog760'},COLORS:[],planningMode:false,browseMode:true,browseScope:{kind:'viewport',label:'Courses in this map area'},activeFacility:null,popupSelection:null,cataloguePopup:null,movingCourseCard:false,viewportFrame:null,listLimit:60,catalogDate:'revision760',rankingNodes:new Map(),browseNodes:new Map(),rowInteractions:new Set(),$:id=>controls[id],renderOptional:(o,p)=>renderOptional(o,{...p,document}),renderKnownOptional:(o,p)=>renderKnownOptional(o,{...p,document}),requestAnimationFrame:fn=>{frames.push(fn);return frames.length;},drawFacilities:()=>effects.draws++,fitPoints:(p,z)=>effects.fit.push([p,z]),setDrawer:()=>{view.resultsPanel.hidden=false;},selected:()=> 'maximum',updateDisplaySortOptions(){},duration:()=> 'Unavailable',planningSession:{update(){effects.planning++;throw Error('No automatic planning');},invalidate(){effects.planning++;throw Error('No browse invalidation');}}};
 ctx.mobile=()=>false;ctx.REDUCED_MOTION=false;ctx.coursesDrawer=null;
 vm.createContext(ctx);
 for(const name of ['node','selectableCourses','selectCourse','moveCourseCard','courseCard','renderRanking','knownLink','knownAddress','appendKnownOptional','knownRounds','coursePopupDetails','facilityDetails','selectCoincidentFacilities','selectFacilityById','selectionPopupOptions','openSelectionPopup','closeSelection','reconcilePopupChoices','reconcileBrowseSelection','selectedFirst','refreshBrowseViewport','filterOptions','scopedRecords','matchesCourseFilters','scopedFacilities','browseRecordId','facilityGroup','renderFacilityGroups','updateLoadedCount','renderCourses'])vm.runInContext(actual(name),ctx);
 vm.runInContext(source.slice(source.indexOf('map.on("moveend zoomend"'),source.indexOf('async function loadCatalog()')),ctx);
 const real=ctx.renderCourses;ctx.renderCourses=()=>{effects.render++;return real();};ctx.renderCourses();
 return {ctx,view,effects,controls,document,frames,events,ids:()=>view.results.querySelectorAll('.course-card').map(card=>card.dataset.courseId),cards:()=>view.results.querySelectorAll('.course-card'),pan:box=>{bounds=box;events.moveend();events.zoomend();},flush:()=>{while(frames.length)frames.shift()();},popup:()=>openPopup};
}
test('move/zoom follows the viewport in one frame, drops stale selection and never routes',()=>{
 const h=harness();assert.deepEqual(h.ids(),['c-c','c-a','c-b']);h.ctx.selectCourse('c-b');assert.equal(h.ids()[0],'c-b');
 const before=h.effects.render;h.pan([41.8,-89.2,42.2,-88.8]);assert.equal(h.frames.length,1);h.flush();
 assert.equal(h.effects.render,before+1);assert.deepEqual(h.ids(),['c-c']);assert.equal(h.ctx.state.activeCourse,null);assert.equal(h.ctx.activeFacility,null);assert.equal(h.ctx.cataloguePopup,null);assert.equal(h.effects.planning,0);
});
test('zoom within an unchanged viewport preserves card nodes and course-button focus',()=>{
 const h=harness(),card=h.cards().find(c=>c.dataset.courseId==='c-a'),focus=card.querySelector('.course-focus');focus.focus();
 h.pan([40,-90,43,-87]);h.flush();assert.equal(h.cards().find(c=>c.dataset.courseId==='c-a'),card);assert.equal(card.querySelector('.course-focus'),focus);assert.equal(h.document.activeElement,focus);
});
test('card clicks select/highlight and promote exactly one existing card; repeated clicks never duplicate it',()=>{
 const h=harness(),item=h.cards().find(card=>card.dataset.courseId==='c-b').parent,card=item.firstElementChild;
 for(let i=0;i<8;i++)card.querySelector('.course-focus').onclick();
 assert.equal(h.ids()[0],'c-b');assert.equal(new Set(h.ids()).size,3);assert.equal(h.cards().filter(c=>c.dataset.active==='true').length,1);assert.equal(h.view.results.querySelector('.facility-courses').children[0],item);assert.equal(h.effects.popups,1);assert.equal(h.effects.fit.length,8);assert.equal(h.ctx.popupSelection.kind,'course');assert.equal(h.ctx.popupSelection.id,'c-b');assert.equal(h.view.results.children.length,1);assert.equal(h.view.results.querySelectorAll('.facility-group').length,2);
});
test('shared-facility pin promotes its normal cards without inventing a selected individual; choosing an inventory course selects it',()=>{
 const h=harness();h.ctx.selectFacilityById('f-one');assert.equal(h.ctx.state.activeCourse,null);assert.deepEqual(h.ids(),['c-a','c-b','c-c']);assert.equal(h.ctx.popupSelection.kind,'facility');
 const button=h.popup().content.querySelectorAll('button').find(n=>n.textContent.includes('Charlie'));assert.ok(button);button.emit('click');assert.equal(h.ctx.state.activeCourse,'c-b');assert.deepEqual(h.ids(),['c-b','c-a','c-c']);assert.equal(h.ctx.popupSelection.kind,'course');
});
test('single-course facility pin selects its existing card and popup; clicking the map deselects both',()=>{
 const h=harness();h.ctx.selectFacilityById('f-two');assert.equal(h.ctx.state.activeCourse,'c-c');assert.equal(h.ctx.popupSelection.kind,'course');h.events.click();assert.equal(h.ctx.state.activeCourse,null);assert.equal(h.ctx.activeFacility,null);assert.equal(h.ctx.cataloguePopup,null);assert.ok(h.cards().every(c=>c.dataset.active==='false'));
});
test('closing a popup and filtering out a selected course both clear stale highlight',()=>{
 const h=harness();h.ctx.selectCourse('c-a');h.events.popupclose({popup:h.ctx.cataloguePopup});assert.equal(h.ctx.state.activeCourse,null);
 h.ctx.selectCourse('c-b');h.controls['browse-holes'].value='9';h.ctx.renderCourses();assert.equal(h.ctx.state.activeCourse,null);assert.deepEqual(h.ids(),[]);assert.equal(h.ctx.cataloguePopup,null);
});
test('explicit selection promotes its whole facility before the 60-facility window',()=>{
 const h=harness(),base=h.ctx.catalogModel.courses[0];
 for(let i=0;i<80;i++){const f={...h.ctx.catalogModel.facilities[0],facility_id:`f-extra-${i}`};h.ctx.catalogModel.facilities.push(f);h.ctx.catalogModel.facilityById.set(f.facility_id,f);const c={...base,facility_id:f.facility_id,course_id:`c-extra-${i}`,name:`ZZ${String(i).padStart(2,'0')}`};h.ctx.catalogModel.courses.push(c);h.ctx.catalogModel.courseById.set(c.course_id,c);}
 h.ctx.renderCourses();assert.equal(h.ids().length,61);assert.ok(!h.ids().includes('c-extra-79'));h.ctx.selectCourse('c-extra-79');assert.equal(h.ids()[0],'c-extra-79');assert.equal(h.ids().length,61);assert.equal(new Set(h.ids()).size,61);
});
test('a selected course with its own visible point is not cleared because its facility point is outside',()=>{
 const h=harness(),course=h.ctx.catalogModel.courseById.get('c-a');course.map_location={latitude:42,longitude:-89};h.pan([41.8,-89.2,42.2,-88.8]);h.flush();h.ctx.selectCourse('c-a');h.ctx.renderCourses();assert.equal(h.ctx.state.activeCourse,'c-a');assert.equal(h.ids()[0],'c-a');
});
test('map moves in planning preserve the committed-origin pool/selection and make no calculations',()=>{
 const h=harness();h.ctx.planningMode=true;h.ctx.browseMode=false;h.ctx.state.ranking={courses:h.ctx.catalogModel.courses.slice(0,2).map(c=>({...browseCard(c,h.ctx.catalogModel.destinations),browseOnly:false,rank:null})),objective:'maximum'};
 h.ctx.renderCourses();h.ctx.rowInteractions.add('pointer:c-a');h.ctx.selectCourse('c-b');assert.equal(h.ids()[0],'c-b');const pool=h.ctx.state.ranking.courses;h.pan([20,-120,21,-119]);h.flush();assert.deepEqual(h.ids(),['c-b','c-a']);assert.equal(h.ctx.state.activeCourse,'c-b');assert.equal(h.ctx.state.ranking.courses,pool);assert.equal(h.effects.planning,0);assert.equal(h.ctx.selectCourse('c-c'),false);
});
test('popup projection omits nulls/empty sections and provenance but preserves false, zero and restrictions',()=>{
 const h=harness(),course=h.ctx.catalogModel.courseById.get('c-a');
 const unknown=h.ctx.coursePopupDetails(course);assert.doesNotMatch(unknown.textContent,/unconfirmed|unknown|unavailable|not recorded|not documented|await|source|license|status|scope/i);assert.equal(unknown.querySelectorAll('details').length,0);
 course.nonmember_bookable=false;course.booking_conditions='Members must accompany guests.';course.access_qualification='Walking only after 3pm.';
 const {value}=fixture(),row=structuredClone(value.courses.find(c=>c.optional.practice_observation.length).optional.practice_observation[0]);
 course.optional.practice_observation=[{...row,driving_range_available:false,driving_range_station_count:0,qualification:'Range access requires a lesson.',collected_on:'2026-10-01',observed_on:'2026-09-30'}];
 const known=h.ctx.coursePopupDetails(course),text=known.textContent;assert.match(text,/Nonmember booking: No/);assert.match(text,/Members must accompany guests/);assert.match(text,/Walking only after 3pm/);assert.match(text,/Range access requires a lesson/);assert.match(text,/driving range available No/);assert.match(text,/driving range station count 0/);assert.match(text,/Observed 2026-09-30/);assert.doesNotMatch(text,/Unconfirmed|Source license|collected|status extracted|date unknown/);
});
test('known popup facts preserve metadata-only empty arrays and do not mutate stored optional rows',()=>{
 const h=harness(),course=h.ctx.catalogModel.courses[0],before=JSON.stringify(course);
 assert.equal(renderKnownOptional(empty(),{subjectLabel:'Course',document:h.document}),null);h.ctx.coursePopupDetails(course);assert.equal(JSON.stringify(course),before);
 const f=h.ctx.catalogModel.facilities[0],text=h.ctx.facilityDetails(f).textContent;assert.doesNotMatch(text,/unknown|unconfirmed|not recorded|await|inventory|entrance unverified/i);assert.match(text,/36 holes/);assert.doesNotMatch(text,/physical holes|Property point/);assert.match(text,/2 courses/);
});

test('search-only unmapped records stay selectable until the next ordinary viewport change',()=>{
 const h=harness(),course=h.ctx.catalogModel.courseById.get('c-a');course.map_location=null;
 h.ctx.browseScope={ids:['f-one'],label:'Facility search'};h.ctx.renderCourses();assert.deepEqual(h.ids(),['c-a','c-b']);h.ctx.selectCourse('c-a');assert.equal(h.ctx.state.activeCourse,'c-a');assert.equal(h.ctx.popupSelection,null);
 h.pan([40,-90,43,-87]);h.flush();assert.deepEqual(h.ids(),['c-c','c-b']);assert.equal(h.ctx.state.activeCourse,null);
});
test('a deferred browse frame cannot replace a newly entered planning view or reopen a collapsed drawer',()=>{
 const h=harness();h.pan([41.8,-89.2,42.2,-88.8]);h.ctx.planningMode=true;const count=h.effects.render;h.flush();assert.equal(h.effects.render,count);
 h.ctx.planningMode=false;h.view.resultsPanel.hidden=true;h.pan([41.8,-89.2,42.2,-88.8]);h.flush();assert.equal(h.view.resultsPanel.hidden,true);assert.deepEqual(h.ids(),['c-c']);
});
test('leaving planning restores viewport scope even when an older search scope remains',()=>{
 const h=harness();h.ctx.planningMode=true;h.ctx.browseMode=false;h.ctx.browseScope={ids:['f-one'],label:'Old search'};h.pan([41.8,-89.2,42.2,-88.8]);h.flush();
 h.controls['close-plan']={};h.ctx.planningSession.invalidate=()=>{};h.ctx.committedOrigins=()=>[];
 const start=source.indexOf('$("close-plan").onclick ='),end=source.indexOf('$("progress-toggle").onclick',start);vm.runInContext(source.slice(start,end),h.ctx);h.controls['close-plan'].onclick();assert.equal(h.ctx.browseScope.kind,'viewport');assert.deepEqual(h.ids(),['c-c']);
});
test('inventory entries excluded by current filters are known text rather than dead selection buttons',()=>{
 const h=harness();h.ctx.catalogModel.courseById.get('c-b').physical_holes=9;h.controls['browse-holes'].value='18';h.ctx.selectFacilityById('f-one');assert.equal(h.ctx.state.activeCourse,'c-a');
 const popup=h.ctx.facilityDetails(h.ctx.catalogModel.facilityById.get('f-one'));
 assert.match(popup.textContent,/Charlie/);assert.ok(!popup.querySelectorAll('button').some(button=>button.textContent.includes('Charlie')));assert.equal(h.ctx.selectCourse('c-b'),false);
});
test('known popup links reject non-http URLs and unknown-only observations/rounds create no empty disclosures',()=>{
 const h=harness(),course=h.ctx.catalogModel.courseById.get('c-a');course.website='javascript:alert(1)';course.booking_url='https://operator.example/book';course.contact_url='file:///private';course.round_options=[{id:'r-a',name:null,round_holes:null,description:null,optional:empty(),tee_sets:[]}];
 const popup=h.ctx.coursePopupDetails(course);assert.equal(popup.querySelectorAll('details').length,0);assert.deepEqual(popup.querySelectorAll('a').map(a=>a.href),['https://operator.example/book']);
});


test('coincident facility choices clear the previous individual without arbitrary course selection',()=>{
 const h=harness();h.ctx.selectCourse('c-a');h.ctx.selectCoincidentFacilities(['f-one','f-two'],{lat:41,lng:-88});
 assert.equal(h.ctx.state.activeCourse,null);assert.equal(h.ctx.activeFacility,null);assert.equal(h.ctx.popupSelection.kind,'coincident');assert.match(h.popup().content.textContent,/2 golf records at this point/);assert.equal(new Set(h.ids()).size,3);
 h.pan([41.8,-89.2,42.2,-88.8]);h.flush();assert.equal(h.ctx.popupSelection,null);
});
test('unmapped multi-course facility search closes a previous mapped popup without inventing a point',()=>{
 const h=harness();h.ctx.selectCourse('c-c');h.ctx.catalogModel.facilityById.get('f-one').map_location=null;h.ctx.browseScope={ids:['f-one'],label:'Facility search'};h.ctx.selectFacilityById('f-one');assert.equal(h.ctx.popupSelection,null);assert.equal(h.ctx.cataloguePopup,null);assert.equal(h.ctx.state.activeCourse,null);assert.deepEqual(h.ids(),['c-a','c-b']);
});


test('viewport updates preserve loaded windows above60 and focused eligible cards',()=>{
 const h=harness(),base=h.ctx.catalogModel.courses[0];
 for(let i=0;i<100;i++){const c={...base,course_id:`c-loaded-${i}`,name:`ZZ${String(i).padStart(3,'0')}`};h.ctx.catalogModel.courses.push(c);h.ctx.catalogModel.courseById.set(c.course_id,c);}
 h.ctx.listLimit=120;h.ctx.renderCourses();assert.equal(h.ids().length,103);
 const card=h.cards().find(c=>c.dataset.courseId==='c-loaded-99'),focus=card.querySelector('.course-focus');focus.focus();
 h.pan([40,-90,43,-87]);h.flush();assert.equal(h.ids().length,103);assert.equal(h.document.activeElement,focus);assert.ok(h.view.results.contains(card));
 // Newly entering alphabetically earlier records must not push a held eligible card out.
 for(let i=0;i<100;i++){const c={...base,course_id:`c-entered-${i}`,name:`AA${i}`};h.ctx.catalogModel.courses.push(c);h.ctx.catalogModel.courseById.set(c.course_id,c);}
 h.pan([40,-90,43,-87]);h.flush();assert.ok(h.ids().includes('c-loaded-99'));assert.equal(h.document.activeElement,focus);assert.equal(card.querySelector('.course-focus'),focus);
});
test('changing filters after a multi-course popup is open closes stale choices and returns popup focus safely',()=>{
 const h=harness();h.ctx.catalogModel.courseById.get('c-b').physical_holes=9;
 h.ctx.selectFacilityById('f-one');const stale=h.popup().content.querySelectorAll('button').find(button=>button.textContent.includes('Charlie'));assert.ok(stale);stale.focus();
 h.controls['browse-holes'].value='18';h.ctx.renderCourses();assert.equal(h.ctx.cataloguePopup,null);assert.equal(h.ctx.activeFacility,null);assert.equal(h.document.activeElement,h.controls['courses-grip']);assert.ok(!h.ids().includes('c-b'));
});
test('planning filters also close an already-open mixed-course popup instead of retaining dead choices',()=>{
 const h=harness();h.ctx.catalogModel.courseById.get('c-b').physical_holes=9;h.ctx.planningMode=true;h.ctx.browseMode=false;
 h.ctx.state.ranking={courses:h.ctx.catalogModel.courses.slice(0,2).map(c=>({...browseCard(c,h.ctx.catalogModel.destinations),browseOnly:false,rank:null})),objective:'maximum'};h.ctx.renderCourses();h.ctx.selectFacilityById('f-one');assert.equal(h.ctx.popupSelection.kind,'facility');
 h.controls['browse-holes'].value='18';h.ctx.renderCourses();assert.equal(h.ctx.cataloguePopup,null);assert.deepEqual(h.ids(),['c-a']);
});
test('strictly accepted qualification-only observations retain their known restriction in popup',()=>{
 const h=harness(),{value,manifest}=fixture(),target=value.courses.find(c=>c.optional.practice_observation.length).optional.practice_observation[0];
 const metadata=new Set(['id','observation_id','facility_id','course_id','component_id','round_id','source_id','source_url','source_license','source_attribution','collected_on','observed_on','effective_from','effective_to','status','conflict','qualification']);
 const restriction='Practice access requires a scheduled lesson.';
 function update(object){if(!object||typeof object!=='object')return;if(object.observation_id===target.observation_id)object.qualification=restriction;if(object.id===target.id)for(const key of Object.keys(OPTIONAL_SCHEMA.practice_observation))if(!metadata.has(key))object[key]=null;for(const child of Object.values(object))update(child);}
 update(value);const model=validatePublicCatalog(value,manifest),row=[...model.optionalObservations.values()].find(r=>r.id===target.id),groups=empty();groups.practice_observation=[row];
 const node=renderKnownOptional(groups,{subjectLabel:'Practice at this course',document:h.document});assert.ok(node);assert.match(node.textContent,/Practice access requires a scheduled lesson/);assert.equal(node.querySelectorAll('dl').length,0);
});
test('Leaflet close notification before remove does not close the same popup recursively',()=>{
 const h=harness();h.ctx.selectCourse('c-a');const popup=h.ctx.cataloguePopup;h.ctx.map.closePopup(popup);assert.equal(h.effects.closes,1);assert.equal(h.ctx.cataloguePopup,null);assert.equal(h.ctx.state.activeCourse,null);assert.equal(h.ctx.activeFacility,null);
});


test('strictly accepted unnamed component with unknown hole count keeps known optional facts',()=>{
 const h=harness(),{value,manifest}=fixture(),course=value.courses.find(c=>c.components.length),component=course.components[0];
 function clear(object){if(!object||typeof object!=='object')return;if(object.id===component.id&&Object.hasOwn(object,'name')){object.name=null;object.physical_holes=null;}for(const child of Object.values(object))clear(child);}clear(value);
 h.ctx.catalogModel=validatePublicCatalog(value,manifest);const popup=h.ctx.coursePopupDetails(h.ctx.catalogModel.courseById.get(course.course_id));
 const details=popup.querySelectorAll('details').find(d=>d.firstElementChild.textContent==='Component');assert.ok(details);assert.equal(details.firstElementChild.tag,'summary');assert.match(details.textContent,/greens grass name Documented bentgrass/);assert.match(details.textContent,/Synthetic Person/);assert.doesNotMatch(details.textContent,/Unconfirmed|Not documented/);
 component.optional=empty();const blank=h.ctx.coursePopupDetails(course);assert.ok(!blank.querySelectorAll('details').some(d=>d.firstElementChild.textContent==='Component'));
});
test('strictly accepted unnamed round with unknown holes keeps its known description and optional restrictions',()=>{
 const h=harness(),{value,manifest}=fixture(),course=value.courses.find(c=>c.round_options.some(r=>Object.values(r.optional).some(rows=>rows.length))),round=course.round_options.find(r=>Object.values(r.optional).some(rows=>rows.length));
 function clear(object){if(!object||typeof object!=='object')return;if(object.id===round.id&&Object.hasOwn(object,'round_holes')){object.name=null;object.round_holes=null;}for(const child of Object.values(object))clear(child);}clear(value);
 h.ctx.catalogModel=validatePublicCatalog(value,manifest);const popup=h.ctx.coursePopupDetails(h.ctx.catalogModel.courseById.get(course.course_id));const details=popup.querySelectorAll('details').find(d=>d.firstElementChild.textContent==='Round');assert.ok(details);assert.match(details.textContent,/Dated weekdays only/);assert.doesNotMatch(details.textContent,/Unconfirmed|Not documented/);
});
test('a visible facility pin is not rejected by a prior different facility-search scope before viewport frame',()=>{
 const h=harness();h.ctx.browseScope={ids:['f-one'],label:'Facility search'};h.ctx.renderCourses();h.ctx.selectFacilityById('f-two');assert.equal(h.ctx.state.activeCourse,'c-c');assert.equal(h.ids()[0],'c-c');assert.equal(h.ctx.popupSelection.kind,'course');h.pan([41.8,-89.2,42.2,-88.8]);h.flush();assert.equal(h.ctx.state.activeCourse,'c-c');assert.equal(h.ctx.popupSelection.kind,'course');
});
test('an explicit facility search outside the prior viewport survives its fit and viewport transition',()=>{
 const h=harness();h.pan([40.8,-88.2,41.3,-87.8]);h.flush();assert.ok(!h.ids().includes('c-c'));h.ctx.browseScope={ids:['f-two'],label:'Facility search'};h.ctx.selectFacilityById('f-two');assert.equal(h.ctx.state.activeCourse,'c-c');assert.equal(h.ctx.popupSelection.kind,'course');assert.equal(h.effects.fit.length,1);h.pan([41.8,-89.2,42.2,-88.8]);h.flush();assert.equal(h.ctx.state.activeCourse,'c-c');assert.equal(h.ctx.popupSelection.kind,'course');
});
test('replacing popup content during a course choice stops the original click before it deselects on the map',()=>{
 const h=harness();h.ctx.selectFacilityById('f-one');const oldContent=h.popup().content,button=oldContent.querySelectorAll('button').find(n=>n.textContent.includes('Charlie'));
 const path=[];for(let n=button;n;n=n.parent)path.push(n);
 let stopped=false;const event={stopPropagation(){stopped=true;}};
 for(const n of path){n.emit('click',event);if(stopped)break;}
 if(!stopped)h.events.click();
 assert.equal(stopped,true);assert.equal(h.ctx.state.activeCourse,'c-b');assert.equal(h.ctx.popupSelection.kind,'course');assert.equal(h.ids()[0],'c-b');assert.notEqual(h.popup().content,oldContent);
});
test('mobile popup scrolls within the map area between controls and the resized Courses sheet',()=>{
 const h=harness();h.ctx.mobile=()=>true;h.ctx.window={innerHeight:844};h.document.querySelector=()=>({getBoundingClientRect:()=>({bottom:218})});h.view.resultsPanel.getBoundingClientRect=()=>({height:489.52});
 h.ctx.selectFacilityById('f-one');const popup=h.popup(),options=popup.options,oldHeight=options.maxHeight;assert.equal(options.autoPan,true);assert.ok(options.maxHeight<90);assert.ok(options.maxHeight+40+options.autoPanPaddingTopLeft[1]+options.autoPanPaddingBottomRight[1]<=844);
 h.view.resultsPanel.getBoundingClientRect=()=>({height:300});h.ctx.selectCourse('c-b');assert.equal(h.popup(),popup);assert.ok(popup.options.maxHeight>oldHeight);assert.equal(h.ctx.state.activeCourse,'c-b');
 h.ctx.mobile=()=>false;h.ctx.openSelectionPopup();assert.equal(popup.options.autoPan,false);assert.equal(popup.options.maxHeight,null);
});
test('short-screen popup fallback retains selection and uses controls in their collapsed-sheet positions',()=>{
 const h=harness();h.ctx.mobile=()=>true;h.ctx.window={innerHeight:390};h.controls['catalog-search']={getBoundingClientRect:()=>({bottom:110})};h.view.resultsPanel.getBoundingClientRect=()=>({height:234});h.document.querySelector=()=>({getBoundingClientRect:()=>h.view.resultsPanel.hidden?{top:320,bottom:362}:{top:174,bottom:218}});h.ctx.coursesDrawer={makeMapRoom(){h.view.resultsPanel.hidden=true;}};
 h.ctx.selectCourse('c-c');assert.equal(h.ctx.state.activeCourse,'c-c');assert.equal(h.view.resultsPanel.hidden,true);assert.equal(h.popup().options.autoPanPaddingTopLeft[1],118);assert.ok(h.popup().options.maxHeight+40+118+78<=390);
 h.ctx.window.innerHeight=90;h.ctx.openSelectionPopup();assert.equal(h.ctx.cataloguePopup,null);assert.equal(h.ctx.state.activeCourse,'c-c');assert.equal(h.ctx.popupSelection.id,'c-c');
});

test('facility-only pin has one reusable facility entry without creating a course',()=>{
 const h=harness(),facility=h.ctx.catalogModel.facilityById.get('f-one');
 h.ctx.catalogModel.courses=h.ctx.catalogModel.courses.filter(c=>c.facility_id!=='f-one');for(const id of ['c-a','c-b'])h.ctx.catalogModel.courseById.delete(id);facility.course_inventory=[];
 h.pan([40.9,-88.2,41.2,-87.8]);h.flush();h.ctx.selectFacilityById('f-one');
 assert.deepEqual(h.ids(),[]);assert.equal(h.ctx.state.activeCourse,null);assert.equal(h.ctx.activeFacility,'f-one');
 assert.match(h.view.results.textContent,/Access not recorded Facility holes 36 holes/);assert.equal(h.view.results.querySelectorAll('.facility-group').length,1);assert.equal(h.view.results.querySelector('.selected-facility-context'),null);assert.equal(h.cards().length,0);
 h.pan([40,-90,43,-87]);h.flush();assert.deepEqual(h.ids(),['c-c']);assert.equal(h.view.results.querySelectorAll('.facility-group').length,2);assert.doesNotMatch(h.view.results.textContent,/No matching courses/);
 h.pan([41.8,-89.2,42.2,-88.8]);h.flush();assert.equal(h.ctx.activeFacility,null);assert.equal(h.view.results.querySelector('.selected-facility-context'),null);
});
test('visible facility pin selects its one actual eligible course despite a different course point',()=>{
 const h=harness();h.ctx.catalogModel.courseById.get('c-b').physical_holes=9;h.controls['browse-holes'].value='18';
 h.ctx.catalogModel.courseById.get('c-a').map_location={latitude:42,longitude:-89};h.pan([40.9,-88.2,41.2,-87.8]);h.flush();assert.deepEqual(h.ids(),[]);
 h.ctx.selectFacilityById('f-one');assert.equal(h.ctx.state.activeCourse,'c-a');assert.equal(h.ids()[0],'c-a');assert.equal(h.cards()[0].dataset.active,'true');assert.equal(h.ctx.selectCourse('c-b'),false);assert.equal(h.ctx.selectCourse('c-c',true,'f-one'),false);
 h.pan([41.8,-89.2,42.2,-88.8]);h.flush();assert.equal(h.ctx.state.activeCourse,'c-a');assert.equal(h.ids()[0],'c-a');
 h.pan([20,-120,21,-119]);h.flush();assert.equal(h.ctx.state.activeCourse,null);assert.deepEqual(h.ids(),[]);assert.doesNotMatch(h.view.results.textContent,/Discovery remains incomplete/);
});
test('shared facility choice includes actual filter-eligible courses outside the pin viewport and reconciles after filter changes',()=>{
 const h=harness();h.ctx.catalogModel.courseById.get('c-b').map_location={latitude:42,longitude:-89};h.ctx.catalogModel.courseById.get('c-b').physical_holes=9;
 h.pan([40.9,-88.2,41.05,-87.8]);h.flush();h.ctx.selectFacilityById('f-one');assert.equal(h.ctx.state.activeCourse,null);assert.deepEqual(new Set(h.ids()),new Set(['c-a','c-b']));
 const button=h.popup().content.querySelectorAll('button').find(b=>b.textContent.includes('Charlie'));assert.ok(button);button.emit('click');assert.equal(h.ctx.state.activeCourse,'c-b');assert.equal(h.ids()[0],'c-b');
 h.controls['browse-holes'].value='18';h.ctx.renderCourses();assert.equal(h.ctx.state.activeCourse,null);assert.deepEqual(h.ids(),['c-a']);assert.equal(h.view.results.querySelector('.selected-facility-context'),null);
});
test('filters with no eligible course show only the neutral empty state and no fake course',()=>{
 const h=harness();h.controls['browse-holes'].value='9';h.ctx.selectFacilityById('f-one');assert.equal(h.ctx.state.activeCourse,null);assert.deepEqual(h.ids(),[]);
 assert.equal(h.view.results.textContent.trim(),'No matching courses.');assert.equal(h.view.results.querySelector('.selected-facility-context'),null);assert.doesNotMatch(h.view.results.textContent,/Shared facility|No course records|Discovery remains incomplete/);
});


test('browse and planning pills omit requested uncertainty labels and details without changing data',()=>{
 const h=harness(),native=h.ctx.catalogModel.courses[0];native.identity_status='needs_review';native.access=null;
 const card={...browseCard(native,h.ctx.catalogModel.destinations),routing_basis:'approximate_facility_point'},before=JSON.stringify(card);
 for(const browseOnly of [true,false]){
  const pill=h.ctx.courseCard({...card,browseOnly},'maximum').firstElementChild;
  assert.doesNotMatch(pill.textContent,/course identity unconfirmed|access unconfirmed|approximate facility point|course arrival unverified|Course details/i);
  assert.equal(pill.querySelectorAll('details').length,0);assert.match(pill.textContent,/18 holes/);assert.doesNotMatch(pill.textContent,/Address|Routing/);
 }
 assert.equal(JSON.stringify(card),before);assert.equal(native.identity_status,'needs_review');assert.equal(native.access,null);
});
test('facility pills retain known access and popup retains explicit restrictions, tee facts and scoped observations',()=>{
 const h=harness(),native=h.ctx.catalogModel.courses[0];
 for(const [access,label] of [['public','Public play'],['private','Private'],['restricted','Restricted']]){
  const facility=h.ctx.catalogModel.facilities[0];facility.access=access;
  assert.ok(h.ctx.facilityGroup(facility,facility.facility_id).textContent.includes(label));
 }
 const {value,manifest}=fixture();h.ctx.catalogModel=validatePublicCatalog(value,manifest);
 const course=value.courses.find(c=>c.plan_eligible===true);course.nonmember_bookable=false;course.booking_conditions='Members must accompany guests.';course.access_qualification='Walking only after 3pm.';
 const before=JSON.stringify(course),popup=h.ctx.coursePopupDetails(course),text=popup.textContent;
 assert.match(text,/Members must accompany guests/);assert.match(text,/Walking only after 3pm/);assert.match(text,/Nonmember booking: No/);assert.match(text,/course difficulty rating \(not a quality rating\)/);assert.match(text,/121/);
 assert.equal(JSON.stringify(course),before);
});
test('compact pills do not construct optional observations or read removed dropdown fields',()=>{
 const h=harness(),card=browseCard(h.ctx.catalogModel.courses[0],h.ctx.catalogModel.destinations);let reads=0;
 for(const key of ['optional','tee_sets','components','round_options'])Object.defineProperty(card,key,{get(){reads++;throw Error('Removed pill details must not inspect '+key);}});
 h.ctx.courseCard(card,'maximum');assert.equal(reads,0);
});
test('generated hole labels use holes while recorded keys, values and verified locations remain intact',()=>{
 const h=harness(),{value}=fixture(),row=Object.fromEntries(Object.keys(OPTIONAL_SCHEMA.architecture_event).map(key=>[key,null]));
 row.credits=[];row.physical_holes_before=18;row.physical_holes_after=27;const optional=empty();optional.architecture_event=[row];const before=JSON.stringify(optional);
 const text=renderKnownOptional(optional,{subjectLabel:'Course',document:h.document}).textContent;assert.match(text,/holes before 18/);assert.match(text,/holes after 27/);assert.doesNotMatch(text,/physical holes/);assert.equal(JSON.stringify(optional),before);
 const facility=h.ctx.catalogModel.facilities[0];facility.map_location.kind='verified_entrance';assert.match(h.ctx.facilityDetails(facility).textContent,/Verified entrance/);
 facility.map_location.kind='property_point';const ftext=h.ctx.facilityDetails(facility).textContent;assert.match(ftext,/36 holes/);assert.doesNotMatch(ftext,/physical holes|Property point/);
});


test('catalog progress has exactly four concise stats with facility map-count semantics',()=>{
 const h=harness();h.controls['progress-counts']=h.document.createElement('div');h.ctx.fmt=n=>n.toLocaleString('en-US');
 const added={...h.ctx.catalogModel.facilities[0],facility_id:'f-unmapped',map_location:null};h.ctx.catalogModel.facilities.push(added);h.ctx.catalogModel.mapRecords.push(added);
 vm.runInContext(actual('renderProgress'),h.ctx);h.ctx.renderProgress();
 const stats=h.controls['progress-counts'];assert.equal(stats.children.length,4);
 assert.deepEqual(stats.children.map(n=>n.children.map(c=>c.textContent)),[['3','Facilities'],['3','Courses'],['2','On map'],['1','Not yet mapped']]);
 assert.doesNotMatch(stats.textContent,/revision|qualification|SQLite|activity|unconfirmed|unknown/i);
});


// Actual catalog regression cases; the synthetic range-only contract is separate.
function releasedCatalog() {
 const value=JSON.parse(gunzipSync(readFileSync(new URL('../data/catalog-release/catalog.json.gz',import.meta.url))));
 const manifest=JSON.parse(readFileSync(new URL('../data/catalog-release/manifest.json',import.meta.url)));
 return validatePublicCatalog(value,manifest);
}
test('actual Emerald Hill facility selects its real course without a placeholder',()=>{
 const h=harness(releasedCatalog()),f=h.ctx.catalogModel.facilities.find(f=>f.released_id==='f-ac1969f3-8470-453a-8679-368195f6a15d'),id=f.facility_id;
 h.pan([f.map_location.latitude-.01,f.map_location.longitude-.01,f.map_location.latitude+.01,f.map_location.longitude+.01]);h.flush();h.ctx.selectFacilityById(id);
 assert.equal(h.ctx.state.activeCourse,'c-9240a483-ccb0-4650-97fa-65115eed819f');
 assert.equal(h.ids().filter(cid=>h.ctx.catalogModel.courseById.get(cid).facility_id===id).length,1);
 assert.match(h.view.results.textContent,/Emerald Hill Golf Course/);assert.match(h.view.results.textContent,/18 holes/);
});
for(const [releasedId,names] of [
 ['f-b8517239-5369-4f16-be97-37d62a5eb2cc',['Great White','Hammerhead','Mako']],
 ['f-db5245d7-c862-49d0-a761-c6e690402ce9',['The Black','The Gold']]
])test('actual Tiburon inventory preserves distinct layouts '+releasedId,()=>{
 const h=harness(releasedCatalog()),f=h.ctx.catalogModel.facilities.find(f=>f.released_id===releasedId),id=f.facility_id,before=h.ctx.catalogModel.courses.length;
 h.pan([f.map_location.latitude-.01,f.map_location.longitude-.01,f.map_location.latitude+.01,f.map_location.longitude+.01]);h.flush();h.ctx.selectFacilityById(id);
 assert.equal(h.ctx.state.activeCourse,null);
 const rows=h.ids().map(cid=>h.ctx.catalogModel.courseById.get(cid)).filter(c=>c.facility_id===id);
 assert.deepEqual(rows.map(c=>c.name).sort(),names);assert.equal(h.ctx.catalogModel.courses.length,before);
 for(const name of names)assert.ok(h.popup().content.textContent.includes(name));
});
test('synthetic range-only contract retains a facility pin and never fabricates a course',()=>{
 const h=harness(),facility=h.ctx.catalogModel.facilityById.get('f-one');facility.name='Synthetic range-only facility';facility.physical_holes=null;
 h.ctx.catalogModel.courses=h.ctx.catalogModel.courses.filter(c=>c.facility_id!=='f-one');for(const id of ['c-a','c-b'])h.ctx.catalogModel.courseById.delete(id);facility.course_inventory=[];h.view.results.replaceChildren();
 h.pan([40.9,-88.2,41.2,-87.8]);h.flush();h.ctx.selectFacilityById('f-one');
 assert.ok(mapEligible(facility));assert.equal(h.ctx.activeFacility,'f-one');assert.equal(h.ctx.state.activeCourse,null);assert.deepEqual(h.ids(),[]);
 assert.ok(h.popup().content.textContent.includes(facility.name));assert.equal(h.cards().length,0);assert.match(h.view.results.textContent,/Access not recorded Facility holes not recorded/);assert.equal(h.view.results.querySelectorAll('.facility-group').length,1);
 assert.equal(h.ctx.catalogModel.courses.length,1);assert.doesNotMatch(h.popup().content.textContent,/holes|course record|18/);
});

test('unnamed OSM grounds keep a visible marker and identity label without creating a course',()=>{
 const f={facility_id:'osm/way/88',name:null,state:null,physical_holes:null,access:null,address:null,website:null,map_location:{latitude:41,longitude:-88,kind:'property_point'},optional:empty(),round_options:[],course_inventory:[]};
 const model=new CatalogRead({revision:1164,facilities:[f],courses:[]}),h=harness(model);
 assert.equal(mapEligible(model.facilities[0]),true);h.ctx.selectFacilityById(f.facility_id);
 assert.match(h.popup().content.textContent,/Unnamed golf facility · OSM way 88/);
 assert.equal(model.facilities[0].name,null);assert.equal(model.courses.length,0);
});

test('explicit OSM course with unknown facility remains one course and has its own map record',()=>{
 const base=catalog(),course={...base.courses[0],course_id:'osm/way/99',facility_id:null,facility_name:null,facility_access:null,name:null,physical_holes:null,nonmember_bookable:null};
 const model=new CatalogRead({revision:1164,facilities:base.facilities,courses:[...base.courses,course]}),h=harness(model);
 assert.equal(model.facilities.length,2);assert.equal(model.mapRecords.length,3);
 assert.equal(model.mapRecordById.get(course.course_id).record_kind,'course');
 h.ctx.selectFacilityById(course.course_id);
 assert.equal(h.ctx.state.activeCourse,course.course_id);
 assert.match(h.popup().content.textContent,/Unnamed golf course · OSM way 99/);
 assert.equal(model.courseById.get(course.course_id).facility_id,null);
 assert.equal(model.courseById.get(course.course_id).name,null);
});

test('one OSM identity cannot occur as both a facility and a course',()=>{
 const base=catalog();base.facilities[0].facility_id='osm/way/99';
 const c={...base.courses[0],course_id:'osm/way/99',facility_id:null};
 assert.throws(()=>new CatalogRead({revision:1,facilities:base.facilities,courses:[c]}),/Invalid course identity/);
});


test('actual Palatine Twin Lakes stays one facility through selection, reopen, search and filters',()=>{
 const model=releasedCatalog(),h=harness(model),id='osm/way/33542466',f=model.facilityById.get(id),before=JSON.stringify(model.courses);
 assert.equal(f.name,'Twin Lakes Golf Course');assert.equal(f.map_location.latitude,42.10466495);assert.equal(f.map_location.longitude,-88.01672355405645);assert.equal(model.facilityCourses(id).length,0);
 h.pan([42.104,-88.017,42.105,-88.016]);h.flush();
 const item=h.view.results.querySelector('.course-list').firstElementChild,card=item.firstElementChild;
 for(let i=0;i<8;i++)card.querySelector('button').emit('click');
 assert.equal(h.view.results.querySelectorAll('.facility-group').length,1);assert.equal(h.view.results.querySelector('.course-list').firstElementChild,item);assert.equal(card.dataset.active,'true');assert.equal(card.dataset.facilityId,id);assert.equal(card.dataset.courseId,undefined);
 assert.equal(h.ctx.state.activeCourse,null);assert.equal(h.view.resultCount.textContent,'1');assert.equal(h.view.resultCount.attrs['aria-label'],'Number of entries loaded: 1 (0 courses, 1 facilities)');
 h.ctx.closeSelection();h.view.resultsPanel.hidden=true;h.ctx.selectFacilityById(id);assert.equal(h.view.resultsPanel.hidden,false);assert.equal(h.view.results.querySelectorAll('.facility-group').length,1);
 h.ctx.browseScope={ids:[id],label:'Facility search'};h.ctx.renderCourses();assert.equal(h.view.results.querySelectorAll('.facility-group').length,1);assert.deepEqual(h.ids(),[]);
 h.controls['browse-holes'].value='18';h.ctx.renderCourses();assert.equal(h.ctx.activeFacility,null);assert.equal(h.view.results.querySelectorAll('.facility-group').length,0);assert.equal(h.view.results.textContent.trim(),'No matching courses.');
 h.controls['browse-holes'].value='all';h.controls['browse-access'].value='public';h.ctx.renderCourses();assert.equal(h.view.results.querySelectorAll('.facility-group').length,0);
 h.controls['browse-access'].value='unknown';h.ctx.renderCourses();assert.equal(h.view.results.querySelectorAll('.facility-group').length,1);
 h.pan([40,-90,41,-89]);h.flush();assert.equal(h.view.results.querySelectorAll('.facility-group').some(c=>c.dataset.facilityId===id),false);
 assert.equal(JSON.stringify(model.courses),before);assert.equal(model.courseById.has(id),false);assert.equal(model.facilityCourses(id).length,0);
});

test('Village Links has one facility pill containing its two real courses through selection and filters',()=>{
 const model=releasedCatalog(),h=harness(model),id='osm/way/188163012',before=JSON.stringify({facilities:model.facilities,courses:model.courses});
 h.ctx.browseScope={ids:[id],label:'Facility search'};h.ctx.selectFacilityById(id);
 const group=h.view.results.querySelector('.facility-group'),rows=group.querySelectorAll('.course-card');
 assert.equal(h.view.results.querySelectorAll('.facility-group').length,1);assert.equal(rows.length,2);
 assert.deepEqual(rows.map(row=>row.querySelector('.course-title').textContent),['18-hole course','9-hole course']);
 assert.match(group.textContent,/Village Links of Glen Ellyn/);assert.match(group.textContent,/Public play/);assert.match(group.textContent,/27 holes/);
 assert.equal(group.querySelector('a').href,'https://villagelinksgolf.com/about-us/');
 assert.match(group.textContent,/485 Winchell Way, Glen Ellyn, IL 60137/);
 for(let i=0;i<8;i++){rows[1].querySelector('.course-focus').onclick();h.ctx.closeSelection();}
 assert.equal(h.view.results.querySelector('.facility-group'),group);assert.equal(h.cards().length,2);
 h.controls['browse-holes'].value='9';h.ctx.renderCourses();assert.equal(h.cards().length,1);assert.match(h.cards()[0].textContent,/9-hole course/);
 h.controls['browse-holes'].value='18';h.ctx.renderCourses();assert.equal(h.cards().length,1);assert.match(h.cards()[0].textContent,/18-hole course/);
 h.controls['browse-holes'].value='all';h.ctx.renderCourses();assert.equal(h.cards().length,2);
 assert.equal(JSON.stringify({facilities:model.facilities,courses:model.courses}),before);
});
test('Headwaters keeps its public access and 18 facility holes without fabricating a course',()=>{
 const model=releasedCatalog(),h=harness(model),id='osm/way/974432437',before=JSON.stringify({facilities:model.facilities,courses:model.courses});
 h.ctx.browseScope={ids:[id],label:'Facility search'};h.ctx.selectFacilityById(id);
 const group=h.view.results.querySelector('.facility-group');
 assert.equal(h.view.results.querySelectorAll('.facility-group').length,1);assert.equal(h.cards().length,0);
 assert.deepEqual(group.querySelectorAll('dt').map(row=>row.textContent),['Town','Website','Access','Facility holes']);
 assert.deepEqual(group.querySelectorAll('dd').map(row=>row.textContent),['not recorded','Website','Public play','18 holes']);
 assert.equal(group.querySelector('a').href,'https://www.headwaters.golf/');assert.match(group.textContent,/Courses: not recorded/);
 for(let i=0;i<8;i++){group.querySelector('button').emit('click');h.ctx.closeSelection();}
 assert.equal(h.view.results.querySelector('.facility-group'),group);assert.equal(h.ctx.state.activeCourse,null);
 h.controls['browse-access'].value='public';h.controls['browse-holes'].value='18';h.ctx.renderCourses();assert.equal(h.view.results.querySelector('.facility-group'),group);
 h.controls['browse-access'].value='private';h.ctx.renderCourses();assert.equal(h.view.results.querySelectorAll('.facility-group').length,0);assert.equal(h.ctx.activeFacility,null);
 h.controls['browse-access'].value='public';h.ctx.renderCourses();assert.equal(h.view.results.querySelectorAll('.facility-group').length,1);
 assert.equal(model.facilityCourses(id).length,0);assert.equal(model.courseById.has(id),false);
 assert.equal(JSON.stringify({facilities:model.facilities,courses:model.courses}),before);
});
test('missing facts occupy the same individual fields for every source and preserve an unknown facility identity',()=>{
 const h=harness(),f=h.ctx.catalogModel.facilities[0],unknown={...f,name:null,state:null,access:null,website:null,address:null,physical_holes:null};
 for(const catalog_origin of ['osm','matched_release','catalog_only']){
  const group=h.ctx.facilityGroup({...unknown,catalog_origin},f.facility_id).firstElementChild;
  assert.equal(group.querySelector('.facility-focus').textContent,'not recorded');
  assert.deepEqual(group.querySelectorAll('dt').map(row=>row.textContent),['Town','Website','Access','Facility holes']);
  assert.deepEqual(group.querySelectorAll('dd').map(row=>row.textContent),Array(4).fill('not recorded'));
 }
 const card=h.ctx.courseCard({...browseCard(h.ctx.catalogModel.courses[0],h.ctx.catalogModel.destinations),course_name:null,holes:9},'maximum');
 assert.equal(card.querySelector('.course-title').textContent,'not recorded');assert.equal(card.querySelector('.course-meta').textContent,'9 holes');
 const c={...h.ctx.catalogModel.courses[0],course_id:'osm/way/99',facility_id:null,facility_name:null};
 const model=new CatalogRead({revision:1,facilities:[],courses:[c]}),orphan=harness(model),group=orphan.view.results.querySelector('.facility-group');
 assert.equal(group.dataset.facilityId,undefined);assert.equal(group.querySelector('.facility-focus').disabled,true);
 assert.equal(orphan.cards().length,1);assert.equal(model.facilities.length,0);assert.equal(model.courseById.get(c.course_id).facility_id,null);
});
test('a display window never splits sibling courses and browse and planning share facility fields',()=>{
 const h=harness(),base=h.ctx.catalogModel.courses[0];
 for(let i=0;i<80;i++){const c={...base,course_id:`c-extra-${i}`,name:`ZZ${i}`};h.ctx.catalogModel.courses.push(c);h.ctx.catalogModel.courseById.set(c.course_id,c);}
 h.ctx.renderCourses();assert.equal(h.cards().length,83);assert.equal(h.view.results.querySelectorAll('.facility-group').length,2);
 const fields=h.view.results.querySelectorAll('.facility-group').map(group=>group.querySelector('.facility-facts').textContent);
 h.ctx.planningMode=true;h.ctx.browseMode=false;h.ctx.state.ranking={courses:h.ctx.catalogModel.courses.map(c=>({...browseCard(c,h.ctx.catalogModel.destinations),browseOnly:false})),objective:'maximum'};
 h.ctx.renderCourses();assert.equal(h.cards().length,83);assert.deepEqual(h.view.results.querySelectorAll('.facility-group').map(group=>group.querySelector('.facility-facts').textContent),fields);
});
