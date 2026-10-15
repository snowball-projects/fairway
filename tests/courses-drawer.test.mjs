import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {bindCoursesDrawer,drawerLimits,sheetLimits} from '../src/fairway/static/courses-drawer.mjs';

function harness(viewportWidth=1440,viewportHeight=844) {
  const shell={style:{},dataset:{}},panel={hidden:true};
  let captured=null,focus=0,viewport=viewportWidth,screenHeight=viewportHeight;
  const handlers={},grip={attributes:{},setAttribute(k,v){this.attributes[k]=v;},addEventListener(k,f){handlers[k]=f;},focus(){focus++;},setPointerCapture(id){captured=id;},hasPointerCapture(id){return captured===id;},releasePointerCapture(){captured=null;}};
  const changes=[];let controller;
  controller=bindCoursesDrawer({shell,panel,grip,viewport:()=>viewport,viewportHeight:()=>screenHeight,setOpen:open=>{panel.hidden=!open;changes.push(open);controller.sync(open);}});
  const send=(type,patch={})=>{const event={button:0,isPrimary:true,pointerId:1,clientX:500,clientY:300,detail:1,stopPropagation(){this.stopped=true;},preventDefault(){this.prevented=true;},...patch};handlers[type](event);return event;};
  return {shell,panel,grip,changes,send,controller,focus:()=>focus,captured:()=>captured,viewport:(value,newHeight=screenHeight)=>{viewport=value;screenHeight=newHeight;controller.sync(!panel.hidden);}};
}
test('reachable native grip toggles with pointer click and keyboard-generated click',()=>{
  const f=harness();assert.equal(f.shell.style.width,'0px');assert.equal(f.grip.attributes['aria-label'],'Open courses');
  f.send('click');assert.equal(f.panel.hidden,false);assert.equal(f.shell.style.width,'360px');assert.equal(f.grip.attributes['aria-expanded'],'true');
  f.send('click',{detail:0});assert.equal(f.panel.hidden,true);assert.equal(f.grip.attributes['aria-label'],'Open courses');
});
test('mouse drag resizes, captures only the grip, and never toggles on release click',()=>{
  const f=harness();f.send('click');f.send('pointerdown');assert.equal(f.captured(),1);assert.equal(f.focus(),1);
  assert.equal(f.send('pointermove',{clientX:380}).prevented,true);assert.equal(f.shell.style.width,'480px');
  f.send('pointerup',{clientX:380});assert.equal(f.captured(),null);f.send('click');assert.equal(f.panel.hidden,false);assert.equal(f.shell.style.width,'480px');assert.deepEqual(f.changes,[true]);
  f.send('click',{detail:0});assert.equal(f.panel.hidden,true);
});
test('mobile touch grip drags vertically down to collapse and up to open without release toggle',()=>{
  const f=harness(390);f.send('click');f.send('pointerdown',{pointerType:'touch',clientY:355});f.send('pointermove',{pointerType:'touch',clientY:830});f.send('pointerup');f.send('click');assert.equal(f.panel.hidden,true);assert.equal(f.shell.style.height,'0px');assert.equal(f.shell.style.width,'100%');
  f.send('pointerdown',{pointerType:'touch',clientY:822});f.send('pointermove',{pointerType:'touch',clientY:420});f.send('pointerup');f.send('click');assert.equal(f.panel.hidden,false);assert.equal(f.shell.style.height,'402px');assert.equal(f.shell.style.width,'100%');
});
test('small movement remains a click; cancelled and lost captures cannot leave an active resize',()=>{
  const f=harness();f.send('pointerdown');f.send('pointermove',{clientX:496});f.send('pointerup');f.send('click');assert.equal(f.panel.hidden,false);
  for(const end of ['pointercancel','lostpointercapture']){f.send('pointerdown');f.send('pointermove',{clientX:400});f.send(end);const saved=f.shell.style.width;f.send('pointermove',{clientX:250});assert.equal(f.shell.style.width,saved);f.send('click',{detail:0});f.send('click',{detail:0});}
});
test('secondary pointers and right clicks cannot take over a primary drag',()=>{
  const f=harness();f.send('click');f.send('pointerdown');f.send('pointerdown',{pointerId:2,isPrimary:false,clientX:100});f.send('pointermove',{pointerId:2,clientX:0});assert.equal(f.shell.style.width,'360px');f.send('pointermove',{clientX:400});assert.equal(f.shell.style.width,'460px');f.send('pointerup');
  f.send('pointerdown',{button:2});f.send('pointermove',{clientX:100});assert.equal(f.shell.style.width,'460px');
});
test('keyboard uses horizontal arrows on desktop and vertical arrows on mobile with map-space bounds',()=>{
  for(const viewport of [320,390,800,1440]){const f=harness(viewport),sheet=viewport<=800,limits=sheet?sheetLimits(844):drawerLimits(viewport),dimension=sheet?'height':'width',increase=sheet?'ArrowUp':'ArrowLeft',decrease=sheet?'ArrowDown':'ArrowRight';
    f.send('keydown',{key:'Home'});assert.equal(Number.parseFloat(f.shell.style[dimension]),limits.maximum);assert.ok(sheet?limits.maximum+240<=844:limits.maximum+44<=viewport);f.send('keydown',{key:decrease});f.send('keydown',{key:'End'});assert.equal(f.panel.hidden,true);f.send('keydown',{key:increase});assert.equal(f.panel.hidden,false);assert.equal(f.send('keydown',{key:increase}).prevented,true);f.viewport(320);assert.equal(f.shell.dataset.mode,'sheet');assert.equal(f.shell.style.width,'100%');}
  const f=harness();assert.equal(f.send('keydown',{key:'Tab'}).prevented,undefined);
});

const app=readFileSync(new URL('../src/fairway/static/app.js',import.meta.url),'utf8');
function extract(name){const start=app.search(new RegExp(`(?:async )?function ${name}\\(`)),next=app.slice(start+1).search(/\n(?:async )?function /);return app.slice(start,next<0?undefined:start+1+next);}
test('actual auto-open helper opens new committed origins once, preserves explicit collapse during polling, and defers mobile editing',()=>{
  const calls=[],context=vm.createContext({automaticCoursesKey:null,isMobile:false,editing:false,JSON,mobile:()=>context.isMobile,$:()=>({contains:()=>context.editing}),document:{activeElement:{}},setDrawer:(which,open)=>calls.push([which,open])});vm.runInContext(extract('openCoursesForOrigins'),context);
  context.origins=[{id:'o0',coordinate:[41,-88]}];vm.runInContext('openCoursesForOrigins(origins)',context);vm.runInContext('openCoursesForOrigins(origins)',context);assert.equal(calls.length,1);
  context.isMobile=true;context.editing=true;context.origins=[{id:'o0',coordinate:[41.005,-88]}];vm.runInContext('openCoursesForOrigins(origins)',context);assert.equal(calls.length,1);context.editing=false;vm.runInContext('openCoursesForOrigins(origins)',context);assert.equal(calls.length,2);
  vm.runInContext('openCoursesForOrigins([]);openCoursesForOrigins(origins)',context);assert.equal(calls.length,3);assert.match(extract('renderPreparation'),/openCoursesForOrigins\(session.origins\)/);
});
test('actual drawer wiring preserves filter focus and closes popover when panel collapses',()=>{
  const panel={hidden:true,contains:()=>true},plan={hidden:true,contains:()=>false},grip={setAttribute(){},focus(){this.focused=true;}},planToggle={setAttribute(){}},controls={'plan-panel':plan,'plan-toggle':planToggle,'courses-grip':grip};
  const sync=[],filter=[],context=vm.createContext({view:{resultsPanel:panel,appShell:{classList:{toggle(){}}}},document:{activeElement:{}},$:id=>controls[id],mobile:()=>false,coursesDrawer:{sync:open=>sync.push(open)},setFilterOpen:open=>filter.push(open),renderCourses(){}});vm.runInContext(extract('setDrawer'),context);vm.runInContext('setDrawer("courses",true);setDrawer("courses",false)',context);assert.deepEqual(sync,[true,false]);assert.deepEqual(filter,[false]);assert.equal(grip.focused,true);
  const first={focus(){this.focused=true;}},popover={hidden:true,querySelector:()=>first},toggle={setAttribute(){}};context.view.filterPopover=popover;context.view.filterToggle=toggle;panel.hidden=false;vm.runInContext(extract('setFilterOpen'),context);vm.runInContext('setFilterOpen(true,true)',context);assert.equal(first.focused,true);
});
test('header exposes numeric loaded count and requested controls without redundant Courses/X/US controls',()=>{
  const html=readFileSync(new URL('../src/fairway/static/index.html',import.meta.url),'utf8');assert.doesNotMatch(html,/id="(?:courses-toggle|close-courses|us-view)"/);assert.match(html,/title="Number of courses loaded"/);assert.match(html,/aria-describedby="courses-grip-help"/);
  const span={setAttribute(name,value){this[name]=value;}},context=vm.createContext({view:{resultCount:span}});vm.runInContext(extract('updateLoadedCount'),context);for(const count of [0,24,100]){context.count=count;vm.runInContext('updateLoadedCount(count)',context);assert.equal(span.textContent,String(count));assert.equal(span['aria-label'],`Number of courses loaded: ${count}`);}
  assert.doesNotMatch(app,/Nearby courses shown|Driving times are being prepared|Some driving times are pending|ranking is provisional|Sorted by/);
});

function mobileWiring() {
  const frames=[],handlers={},docHandlers={},shell={style:{},dataset:{}},origin={},panel={hidden:true,contains:()=>false};
  const document={activeElement:origin,addEventListener(type,fn){docHandlers[type]=fn;}};
  const attributes=()=>({attributes:{},setAttribute(k,v){this.attributes[k]=v;},focus(){}});
  const plan={hidden:false,contains:n=>n===origin},controls={'plan-panel':plan,'plan-toggle':attributes(),'browse-access':{value:'all'}};
  let captured=null,syncs=0,planningSyncs=0,filterOpen=true;
  const grip={...attributes(),addEventListener(type,fn){handlers[type]=fn;},focus(){document.activeElement=grip;docHandlers.focusout?.({});},setPointerCapture(id){captured=id;},hasPointerCapture(id){return captured===id;},releasePointerCapture(){captured=null;}};
  controls['courses-grip']=grip;controls['courses-drawer']=shell;
  const c=vm.createContext({$:id=>controls[id]||null,view:{resultsPanel:panel,appShell:{classList:{toggle(){}}}},document,mobile:()=>true,coursesDrawer:null,setFilterOpen:open=>{filterOpen=open;},renderCourses(){},syncPlanning(){planningSyncs++;},committedOrigins:()=>[],bindCoursesDrawer,window:{innerWidth:390,innerHeight:844,addEventListener(){}},requestAnimationFrame:fn=>frames.push(fn),automaticCoursesKey:null,planningMode:true,browseMode:false,state:{ranking:{}},planningSession:{origins:[{id:'o0',coordinate:[41,-88]}],invalidate(){}},JSON});
  vm.runInContext(extract('setDrawer')+'\n'+extract('openCoursesForOrigins'),c);
  const toggleStart=app.indexOf('$("plan-toggle").onclick ='),bindingEnd=app.indexOf('$("close-plan").onclick',toggleStart);
  vm.runInContext(app.slice(toggleStart,bindingEnd),c);
  const originalSync=c.coursesDrawer.sync;c.coursesDrawer.sync=open=>{syncs++;originalSync(open);};
  const send=(type,values={})=>handlers[type]({isPrimary:true,button:0,pointerId:1,clientX:370,clientY:300,detail:1,stopPropagation(){},preventDefault(){},...values});
  return {c,frames,send,grip,shell,panel,plan,controls,origin,syncs:()=>syncs,planningSyncs:()=>planningSyncs,filterOpen:()=>filterOpen,captured:()=>captured};
}
test('actual mobile Plan-toggle path uses only shipped controls, syncs collapsed grip, closes filters and continues planning',()=>{
  const f=mobileWiring();assert.equal(f.controls['courses-toggle'],undefined);f.send('click');assert.equal(f.panel.hidden,false);f.plan.hidden=true;f.controls['plan-toggle'].onclick();
  assert.equal(f.plan.hidden,false);assert.equal(f.panel.hidden,true);assert.equal(f.grip.attributes['aria-expanded'],'false');assert.equal(f.shell.style.height,'0px');assert.equal(f.shell.style.width,'100%');assert.equal(f.filterOpen(),false);assert.equal(f.c.browseMode,false);assert.equal(f.planningSyncs(),1);assert.ok(f.syncs()>=2);
});
test('actual mobile deferred commit and held grip activation consume auto-open before focusout frame; release opens and later polls respect collapse',()=>{
  for(const type of ['mouse','touch']){const f=mobileWiring();vm.runInContext('openCoursesForOrigins(planningSession.origins)',f.c);assert.equal(f.panel.hidden,true);assert.equal(f.c.automaticCoursesKey,null);
    f.send('pointerdown',{pointerType:type});assert.equal(f.c.automaticCoursesKey,JSON.stringify(f.c.planningSession.origins));assert.equal(f.captured(),1);assert.ok(f.frames.length);f.frames.shift()();assert.equal(f.panel.hidden,true);
    f.send('pointerup',{pointerType:type});f.send('click');assert.equal(f.panel.hidden,false);assert.equal(f.grip.attributes['aria-expanded'],'true');assert.ok(Math.abs(Number.parseFloat(f.shell.style.height)-489.52)<1e-6);assert.equal(f.shell.style.width,'100%');f.send('click');assert.equal(f.panel.hidden,true);
    f.c.document.activeElement={};f.frames.splice(0).forEach(fn=>fn());vm.runInContext('openCoursesForOrigins(planningSession.origins)',f.c);assert.equal(f.panel.hidden,true);assert.equal(f.shell.style.height,'0px');
  }
});
test('actual mobile grip keyboard and cancellation also cancel deferred auto-open without an extra toggle',()=>{
  const focused=mobileWiring();focused.grip.focus();focused.send('focus');focused.frames.shift()();assert.equal(focused.panel.hidden,true);focused.send('click',{detail:0});assert.equal(focused.panel.hidden,false);
  for(const key of ['Enter',' ','ArrowUp','Home','End']){const f=mobileWiring();f.send('keydown',{key,detail:0});assert.equal(f.c.automaticCoursesKey,JSON.stringify(f.c.planningSession.origins));if(['Enter',' '].includes(key))f.send('click',{detail:0});assert.equal(f.panel.hidden,key==='End');}
  const f=mobileWiring();f.send('pointerdown');f.frames.shift()();f.send('pointercancel');f.c.document.activeElement={};vm.runInContext('openCoursesForOrigins(planningSession.origins)',f.c);assert.equal(f.panel.hidden,true);f.send('click',{detail:0});assert.equal(f.panel.hidden,false);
});


test('actual hidden-help CSS bounds its clipped box inside the viewport even at zero drawer width, preserving its accessible description',()=>{
  const css=readFileSync(new URL('../src/fairway/static/styles.css',import.meta.url),'utf8'),html=readFileSync(new URL('../src/fairway/static/index.html',import.meta.url),'utf8');
  const declarations=selector=>{
    const escaped=selector.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),body=css.match(new RegExp(escaped+'\\s*\\{([^}]+)\\}'))?.[1]||'';
    return Object.fromEntries(body.split(';').map(s=>s.trim().split(/:\s*/)).filter(x=>x.length===2));
  };
  const hidden=declarations('.visually-hidden'),anchor=declarations('#courses-grip-help');
  assert.equal(hidden.position,'absolute');assert.equal(hidden.width,'1px');assert.equal(hidden.overflow,'hidden');assert.ok(hidden.clip||hidden['clip-path']);
  assert.notEqual(anchor.right,undefined,'The zero-width shell must give hidden help an explicit trailing inset');assert.equal(Number.parseFloat(anchor.right),0);assert.equal(anchor.bottom,'0');assert.notEqual(anchor.display,'none');assert.notEqual(anchor.visibility,'hidden');
  const help=html.match(/<span id="courses-grip-help"[^>]*>([^<]+)<\/span>/);assert.ok(help);assert.match(help[1],/Enter or Space/);assert.doesNotMatch(help[0],/aria-hidden|\shidden[\s>]/);assert.match(html,/aria-describedby="courses-grip-help"/);
  for(const viewport of [320,390,800,1440]){const f=harness(viewport);for(const open of [false,true]){if(open)f.send('click');const shellWidth=f.shell.style.width==='100%'?viewport:Number.parseFloat(f.shell.style.width),shellLeft=viewport-shellWidth;const helpRight=shellLeft+shellWidth-Number.parseFloat(anchor.right),helpLeft=helpRight-Number.parseFloat(hidden.width);assert.ok(helpRight<=viewport);assert.ok(helpLeft>=0);}}
});


test('breakpoint and orientation preserve independent sizes and cancel an in-flight drag before release',()=>{
  const f=harness(801,900);f.send('click');f.send('pointerdown',{clientX:500});f.send('pointermove',{clientX:400});f.send('pointerup');f.send('click');assert.equal(f.shell.style.width,'460px');
  f.viewport(800,844);assert.equal(f.shell.dataset.mode,'sheet');assert.equal(f.shell.style.width,'100%');assert.equal(f.shell.style.height,'489.52px');
  f.send('pointerdown',{clientY:500});f.send('pointermove',{clientY:400});f.send('pointerup');f.send('click');assert.equal(f.shell.style.height,'589.52px');
  f.viewport(740,390);assert.equal(Number.parseFloat(f.shell.style.height),sheetLimits(390).maximum);f.viewport(390,844);assert.equal(f.shell.style.height,'589.52px');
  f.send('pointerdown');assert.equal(f.captured(),1);f.viewport(801,900);assert.equal(f.captured(),null);assert.equal(f.shell.style.width,'460px');assert.equal(f.shell.style.height,'');f.send('pointermove',{clientX:0,clientY:0});f.send('pointerup');f.send('click');assert.equal(f.panel.hidden,false);assert.equal(f.shell.style.width,'460px');
  f.viewport(390,844);f.send('pointerdown');f.viewport(740,390);assert.equal(f.captured(),null);f.send('pointerup');f.send('click');assert.equal(f.panel.hidden,false);
  f.send('keydown',{key:'ArrowLeft'});assert.equal(Number.parseFloat(f.shell.style.height),sheetLimits(390).maximum);f.send('keydown',{key:'End'});f.viewport(390,844);assert.equal(f.shell.style.height,'0px');
});
test('course scrolling and off-grip pointer motion never begin resizing or capture input',()=>{
  const handlers=[],panel={hidden:false,addEventListener(){assert.fail('Scrolling content must not acquire drag handlers');}},shell={style:{},dataset:{},addEventListener(){assert.fail('Sheet body must not acquire drag handlers');}};
  const grip={setAttribute(){},addEventListener(type){handlers.push(type);}};
  bindCoursesDrawer({shell,panel,grip,viewport:()=>390,viewportHeight:()=>844,setOpen(){assert.fail('Content scroll must not toggle');}});
  assert.ok(handlers.includes('pointerdown'));assert.ok(!handlers.includes('wheel'));assert.ok(!handlers.includes('touchmove'));
  const f=harness(390);f.send('click');const size=f.shell.style.height;const move=f.send('pointermove',{clientY:0,pointerType:'touch'});assert.equal(move.prevented,undefined);assert.equal(f.captured(),null);assert.equal(f.shell.style.height,size);
  const css=readFileSync(new URL('../src/fairway/static/styles.css',import.meta.url),'utf8');assert.match(css,/\.results\s*\{[^}]*overflow-y:\s*auto/s);assert.match(css,/\.courses-grip\s*\{[^}]*touch-action:\s*none/s);assert.doesNotMatch(css,/\.(?:courses-drawer|results|results-panel)\s*\{[^}]*touch-action:\s*none/s);
});
test('uniform adjacent count and filter pills retain tooltip and centered decreasing strokes',()=>{
  const html=readFileSync(new URL('../src/fairway/static/index.html',import.meta.url),'utf8'),css=readFileSync(new URL('../src/fairway/static/styles.css',import.meta.url),'utf8');
  assert.match(html,/<span id="result-count"[^>]*>0<\/span>\s*<button id="filter-toggle"/);
  const button=html.match(/<button id="filter-toggle"[^>]*>([\s\S]*?)<\/button>/)[1],segments=[...button.matchAll(/M(\d+) (\d+)h(\d+)/g)].map(m=>m.slice(1).map(Number));assert.equal(segments.length,3);assert.deepEqual(segments.map(([x,y,length])=>x+length/2),[16,16,16]);assert.ok(segments[0][2]>segments[1][2]&&segments[1][2]>segments[2][2]);
  const count=css.match(/\.courses-drawer \.result-count\s*\{([^}]+)\}/)[1],filter=[...css.matchAll(/\.course-filter-button\s*\{([^}]+)\}/g)].map(m=>m[1]).join(';');
  for(const body of [count,filter])assert.match(body,/height:\s*28px/);assert.match(filter,/margin-left:\s*0/);assert.match(filter,/border-radius:\s*999px/);assert.match(filter,/background:\s*#e9eee7/);assert.match(css,/\.result-count\s*\{[^}]*border-radius:\s*999px;[^}]*background:\s*#e9eee7/s);
  assert.match(css,/\.courses-drawer \.courses-grip\s*\{[^}]*top:-44px;[^}]*left:50%/);assert.match(css,/\.courses-drawer\[data-open="true"\] \.courses-grip\s*\{[^}]*top:0/);
});
test('actual map fit padding follows resized sheet while retaining a positive exposed map region',()=>{
  const plan={hidden:true,getBoundingClientRect:()=>({height:489.52})},panel={hidden:false,getBoundingClientRect:()=>({height:604,width:390})};
  const context=vm.createContext({mobile:()=>true,$:()=>plan,view:{resultsPanel:panel},window:{innerHeight:844},Math});vm.runInContext(extract('fitPadding'),context);
  for(const [height,sheet] of [[844,489.52],[844,604],[390,234],[320,192]]){context.window.innerHeight=height;panel.getBoundingClientRect=()=>({height:sheet});const padding=vm.runInContext('fitPadding()',context);assert.equal(padding.paddingBottomRight[1],sheet+20);assert.ok(height-padding.paddingTopLeft[1]-padding.paddingBottomRight[1]>=64);}
  panel.hidden=true;assert.equal(vm.runInContext('fitPadding().paddingBottomRight[1]',context),75);plan.hidden=false;context.window.innerHeight=844;assert.equal(vm.runInContext('fitPadding().paddingBottomRight[1]',context),509.52);
});


test('actual open mobile grip paints above the opaque sibling panel inside the drawer stacking context',()=>{
  const css=readFileSync(new URL('../src/fairway/static/styles.css',import.meta.url),'utf8'),html=readFileSync(new URL('../src/fairway/static/index.html',import.meta.url),'utf8');
  const rules=[...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(m=>({selectors:m[1].trim(),declarations:Object.fromEntries(m[2].split(';').map(s=>s.trim().split(/:\s*/)).filter(s=>s.length===2))}));
  const matching=end=>rules.filter(r=>r.selectors.split(',').some(s=>s.trim().endsWith(end))),panelZ=matching('.results-panel').map(r=>r.declarations['z-index']).filter(Boolean).at(-1),gripZ=matching('.courses-grip').map(r=>r.declarations['z-index']).filter(Boolean).at(-1);
  assert.ok(Number.isFinite(Number(panelZ)));assert.ok(Number.isFinite(Number(gripZ)));assert.ok(Number(gripZ)>Number(panelZ),'The overlapping grip must be above the opaque panel, irrespective of earlier DOM order');
  const f=harness(390);f.send('click');assert.equal(f.shell.dataset.open,'true');assert.equal(rules.find(r=>r.selectors==='.courses-drawer[data-open="true"] .courses-grip').declarations.top,'0');assert.equal(rules.find(r=>r.selectors==='.courses-drawer > .results-panel').declarations.inset,'0');assert.ok(html.indexOf('id="courses-grip"')<html.indexOf('id="results-panel"'));
});
