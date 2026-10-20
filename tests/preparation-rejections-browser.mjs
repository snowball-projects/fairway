import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin=process.env.REVIEW_ORIGIN || 'http://127.0.0.1:8876';
const output=process.env.REVIEW_OUTPUT || '/tmp/preparation-rejections';await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
const external=[],errors=[],results=[];
await context.route('**/*',route=>{if(!route.request().url().startsWith(origin+'/')){external.push(route.request().url());return route.abort();}return route.continue();});
await context.addInitScript(({origin})=>{
  if(location.origin!==origin)return;
  globalThis.__fairwayCatalogAdapter=import("/tests/fixtures/native-catalog-adapter.mjs").then(m=>m.loadNativeCatalogAdapter()).then(a=>{globalThis.__nativeCatalog=a;return a;});
  globalThis.__fairwayPlanningAdapter=Promise.all([import('/tests/fixtures/sqlite-preparation-adapter.mjs'),import('/tests/fixtures/sqlite-preparation-sequence.json',{with:{type:'json'}})]).then(([module,{default:fixture}])=>{
    const adapter=module.createPreparationFixtureAdapter(),repro=new URLSearchParams(location.search).get('repro');
    adapter.replay=async(request,emit)=>{
      const frame=structuredClone(fixture.steps[0].frames.find(f=>f.type==='planning.snapshot')),snapshot=frame.snapshot;
      if(repro==='counts'){snapshot.prepared_count=snapshot.total;snapshot.pending_count=0;snapshot.ranking_complete=true;emit(frame);}
      if(repro==='aliases'){
        const seen=new Set();for(const row of snapshot.courses){if(seen.has(row.routing_target.id)){row.routing_target.latitude+=1;break;}seen.add(row.routing_target.id);}emit(frame);
      }
      if(repro==='areas'||repro==='missing'){
        const last=structuredClone(frame);snapshot.limit=2;snapshot.courses=snapshot.courses.slice(0,2);snapshot.has_more=true;emit(frame);
        if(repro==='areas'){last.sequence++;last.snapshot.offset=2;last.snapshot.limit=2;last.snapshot.courses=last.snapshot.courses.slice(2);last.snapshot.has_more=false;
          last.snapshot.areas=[{id:'different',center:[42,-88],geometry:{type:'Point',coordinates:[-88,42]},qualification:'synthetic deliberately inconsistent page'}];emit(last);}
      }
      return {fixture_complete:true,evidence:{basis:'literal-fixture-completion',native_admission_released:false}};
    };return adapter;
  });
},{origin});
for(const repro of ['counts','aliases','areas','missing']) {
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.clock.install();
  await page.goto(`${origin}/src/fairway/static/index.html?repro=${repro}`);await page.waitForFunction(()=>document.querySelector('#catalog-status').textContent.includes('on map'));
  await page.locator('#plan-toggle').click();const input=page.getByRole('combobox',{name:'Golfer 1 origin'});
  await input.fill('333 Plum Grove Road, Elk Grove Village, IL 60007');await input.press('Enter');await page.clock.runFor(80);
  await page.waitForFunction(()=>document.querySelector('#preparation-status').dataset.error==='true');
  assert.equal(await page.locator('.course-card').count(),0);
  assert.equal(await page.locator('#preparation-status').isVisible(),true);
  const status=await page.locator('#preparation-status').innerText();assert.doesNotMatch(status,/courses compared/);
  if(repro==='missing')assert.match(status,/could not be read completely/);else assert.match(status,/blocked/);
  results.push({repro,status,cards:0});await page.screenshot({path:`${output}/rejected-${repro}.png`});await page.close();
}
assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
const receipt={status:'All four independent DTO rejection reproductions pass through existing UI',results,external_requests:external,page_errors:errors,real_provider_bound:false};
await writeFile(`${output}/rejections-browser-results.json`,JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt,null,2));await browser.close();
