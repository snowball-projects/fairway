import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {CatalogRead,browseCard,courseMatches,sortCourses,STYLES,located,mapEligible,cityLabel,accessLabel,displayAddress} from '../src/fairway/static/catalog-read.mjs';
import {renderOptional,renderKnownOptional,OPTIONAL_DOMAINS} from '../src/fairway/static/optional-facts.mjs';
import {fixture} from './native5-fixture.mjs';
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
function harness(){
 const document={activeElement:null,createElement:tag=>new Element(tag,document)};
 const controls=Object.fromEntries(['browse-state','browse-access','browse-holes','browse-round','browse-style','browse-sort','browse-description','preparation-status'].map(id=>[id,document.createElement('div')]));
 for(const c of Object.values(controls))c.value='all';controls['browse-sort'].value='name';
 const nonmember=document.createElement('option');nonmember.value='nonmember';controls['browse-access'].append(nonmember);
 const view={results:document.createElement('div'),catalogName:document.createElement('span'),rankingDescription:document.createElement('p'),resultCount:document.createElement('span'),resultsPanel:{hidden:false}};
 const frames=[],events={},effects={fit:[],popups:0,draws:0,planning:0,render:0};let bounds=[40,-90,43,-87],openPopup=null;
 const map={getBounds:()=>({contains:p=>{const [lat,lng]=Array.isArray(p)?p:[p.lat,p.lng];return lat>=bounds[0]&&lat<=bounds[2]&&lng>=bounds[1]&&lng<=bounds[3];}}),on:(types,fn)=>{for(const t of types.split(' '))events[t]=fn;},closePopup:p=>{p.open=false;p.listeners.remove?.();events.popupclose?.({popup:p});}};
 const L={latLng:(lat,lng)=>({lat,lng}),popup:()=>{effects.popups++;const p={listeners:{},setLatLng(c){this.coordinate=c;return this;},setContent(c){this.content=c;return this;},openOn(){this.open=true;openPopup=this;return this;},isOpen(){return this.open;},on(t,fn){this.listeners[t]=fn;return this;}};return p;}};
 const ctx={URL,L,map,document,view,preparationFacilities:{clearLayers(){}},meetingLayer:{clearLayers(){}},STYLES,located,mapEligible,cityLabel,accessLabel,displayAddress,browseCard,courseMatches,sortCourses,catalogModel:catalog(),state:{activeCourse:null,activeRows:[],rows:[],ranking:null,routingCatalogLabel:'Catalog760'},COLORS:[],planningMode:false,browseMode:true,browseScope:{kind:'viewport',label:'Courses in this map area'},activeFacility:null,popupSelection:null,cataloguePopup:null,movingCourseCard:false,viewportFrame:null,listLimit:60,catalogDate:'revision760',rankingNodes:new Map(),browseNodes:new Map(),rowInteractions:new Set(),$:id=>controls[id],renderOptional:(o,p)=>renderOptional(o,{...p,document}),renderKnownOptional:(o,p)=>renderKnownOptional(o,{...p,document}),requestAnimationFrame:fn=>{frames.push(fn);return frames.length;},drawFacilities:()=>effects.draws++,fitPoints:(p,z)=>effects.fit.push([p,z]),setDrawer:()=>{view.resultsPanel.hidden=false;},selected:()=> 'maximum',updateDisplaySortOptions(){},duration:()=> 'Unavailable',planningSession:{update(){effects.planning++;throw Error('No automatic planning');},invalidate(){effects.planning++;throw Error('No browse invalidation');}}};
 vm.createContext(ctx);
 for(const name of ['node','selectableCourses','selectCourse','moveCourseCard','courseCard','courseMetadata','populateCourseMetadata','observationFields','renderRanking','knownLink','knownAddress','appendKnownOptional','knownRounds','coursePopupDetails','facilityDetails','selectCoincidentFacilities','selectFacilityById','openSelectionPopup','closeSelection','reconcileBrowseSelection','selectedFirst','refreshBrowseViewport','filterOptions','scopedRecords','matchesCourseFilters','updateLoadedCount','renderCourses'])vm.runInContext(actual(name),ctx);
 vm.runInContext(source.slice(source.indexOf('map.on("moveend zoomend"'),source.indexOf('async function loadCatalog()')),ctx);
 const real=ctx.renderCourses;ctx.renderCourses=()=>{effects.render++;return real();};ctx.renderCourses();
 return {ctx,view,effects,controls,document,frames,events,ids:()=>view.results.querySelector('.course-list').children.map(item=>item.firstElementChild.dataset.courseId),cards:()=>view.results.querySelectorAll('.course-card'),pan:box=>{bounds=box;events.moveend();events.zoomend();},flush:()=>{while(frames.length)frames.shift()();},popup:()=>openPopup};
}
test('move/zoom follows the viewport in one frame, drops stale selection and never routes',()=>{
 const h=harness();assert.deepEqual(h.ids(),['c-c','c-a','c-b']);h.ctx.selectCourse('c-b');assert.equal(h.ids()[0],'c-b');
 const before=h.effects.render;h.pan([41.8,-89.2,42.2,-88.8]);assert.equal(h.frames.length,1);h.flush();
 assert.equal(h.effects.render,before+1);assert.deepEqual(h.ids(),['c-c']);assert.equal(h.ctx.state.activeCourse,null);assert.equal(h.ctx.activeFacility,null);assert.equal(h.ctx.cataloguePopup,null);assert.equal(h.effects.planning,0);
});
test('zoom within an unchanged viewport preserves card nodes, expanded details and focus',()=>{
 const h=harness(),card=h.cards().find(c=>c.dataset.courseId==='c-a'),details=card.querySelector('.course-facts');details.open=true;details.emit('toggle');const count=details.children.length;details.children[0].focus();
 h.pan([40,-90,43,-87]);h.flush();assert.equal(h.cards().find(c=>c.dataset.courseId==='c-a'),card);assert.equal(card.querySelector('.course-facts'),details);assert.equal(details.open,true);assert.equal(details.children.length,count);assert.equal(h.document.activeElement,details.children[0]);
});
test('card clicks select/highlight and promote exactly one existing card; repeated clicks never duplicate it',()=>{
 const h=harness(),item=h.view.results.querySelector('.course-list').children.find(item=>item.firstElementChild.dataset.courseId==='c-b'),card=item.firstElementChild;
 for(let i=0;i<8;i++)card.querySelector('.course-focus').onclick();
 assert.equal(h.ids()[0],'c-b');assert.equal(new Set(h.ids()).size,3);assert.equal(h.cards().filter(c=>c.dataset.active==='true').length,1);assert.equal(h.view.results.querySelector('.course-list').children[0],item);assert.equal(h.effects.popups,1);assert.equal(h.effects.fit.length,8);assert.equal(h.ctx.popupSelection.kind,'course');assert.equal(h.ctx.popupSelection.id,'c-b');assert.equal(h.view.results.children.length,1);assert.equal(h.view.results.querySelector('.facility-card'),null);
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
test('explicit selection beyond the display window is promoted before the 60-card slice',()=>{
 const h=harness(),base=h.ctx.catalogModel.courses[0];
 for(let i=0;i<80;i++){const c={...base,course_id:`c-extra-${i}`,name:`ZZ${String(i).padStart(2,'0')}`};h.ctx.catalogModel.courses.push(c);h.ctx.catalogModel.courseById.set(c.course_id,c);}
 h.ctx.renderCourses();assert.equal(h.ids().length,60);assert.ok(!h.ids().includes('c-extra-79'));h.ctx.selectCourse('c-extra-79');assert.equal(h.ids()[0],'c-extra-79');assert.equal(h.ids().length,60);assert.equal(new Set(h.ids()).size,60);
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
 const f=h.ctx.catalogModel.facilities[0],text=h.ctx.facilityDetails(f).textContent;assert.doesNotMatch(text,/unknown|unconfirmed|not recorded|await|inventory|entrance unverified/i);assert.match(text,/36 physical holes/);assert.match(text,/2 courses/);
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
 assert.equal(h.ctx.state.activeCourse,null);assert.equal(h.ctx.activeFacility,null);assert.equal(h.ctx.popupSelection.kind,'coincident');assert.match(h.popup().content.textContent,/2 facilities at this point/);assert.equal(new Set(h.ids()).size,3);
 h.pan([41.8,-89.2,42.2,-88.8]);h.flush();assert.equal(h.ctx.popupSelection,null);
});
test('unmapped multi-course facility search closes a previous mapped popup without inventing a point',()=>{
 const h=harness();h.ctx.selectCourse('c-c');h.ctx.catalogModel.facilityById.get('f-one').map_location=null;h.ctx.browseScope={ids:['f-one'],label:'Facility search'};h.ctx.selectFacilityById('f-one');assert.equal(h.ctx.popupSelection,null);assert.equal(h.ctx.cataloguePopup,null);assert.equal(h.ctx.state.activeCourse,null);assert.deepEqual(h.ids(),['c-a','c-b']);
});
