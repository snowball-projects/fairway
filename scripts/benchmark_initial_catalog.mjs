// PLAYWRIGHT_MODULE may point at an existing installation; no app dependency.
import {writeFileSync} from 'node:fs';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const [base='http://127.0.0.1:8767/',output='/tmp/fairway-catalog-benchmark.json']=process.argv.slice(2);
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,headless:true,chromiumSandbox:true});
const rows=[];
try{
 for(const mobile of [false,true]){
  const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},isMobile:mobile,deviceScaleFactor:mobile?3:1});
  const page=await context.newPage();
  const cdp=await context.newCDPSession(page);await cdp.send('Network.enable');
  await cdp.send('Network.setBlockedURLs',{urls:['*://tile.openstreetmap.org/*','*://photon.komoot.io/*']});
  await page.addInitScript(()=>{new MutationObserver(()=>{if(document.querySelector('#catalog-status')?.hidden&&!window.__pinsScheduled){window.__pinsScheduled=true;requestAnimationFrame(()=>requestAnimationFrame(()=>{window.__pinsTime=performance.now();}));}}).observe(document,{subtree:true,attributes:true,attributeFilter:['hidden']});});
  await cdp.send('Emulation.setCPUThrottlingRate',{rate:mobile?4:1});
  if(mobile)await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:40,downloadThroughput:1250000,uploadThroughput:625000});
  for(let i=0;i<4;i++){
   if(i===0)await cdp.send('Network.clearBrowserCache');
   await page.goto(base);
   await page.waitForFunction(()=>window.__pinsTime,{timeout:90000});
   const result=await page.evaluate(async()=>{
    const ready=performance.getEntriesByName('fairway-map-ready')[0]?.startTime;
    await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
    const pins=window.__pinsTime;
    const resources=performance.getEntriesByType('resource').filter(r=>/boundaries|catalog-release|native-catalog|initial-map/.test(r.name)).map(r=>({path:new URL(r.name).pathname,start:r.startTime,headers:r.responseStart-r.startTime,download_and_http_gzip:r.responseEnd-r.responseStart,duration:r.duration,transfer:r.transferSize,encoded:r.encodedBodySize,decoded:r.decodedBodySize}));
    const mod=await import('./public-catalog.mjs');const manifest=await (await fetch('./data/catalog-release.json')).json();
    const initial=Boolean(manifest.files['initial-map.json']),file=manifest.files[initial?'initial-map.json':'catalog.json'];
    const t=performance.now();const response=await fetch('./data/'+file.path+'?gzip-bytes',{cache:'no-cache'});const headers=performance.now();const packed=await response.arrayBuffer();const downloaded=performance.now();
    const stream=new Blob([packed]).stream().pipeThrough(new DecompressionStream('gzip'));
    const bytes=new Uint8Array(await new Response(stream).arrayBuffer());const inflated=performance.now();
    const raw=new TextDecoder('utf-8',{fatal:true}).decode(bytes);const decoded=performance.now();
    await crypto.subtle.digest('SHA-256',bytes);const hashed=performance.now();const value=JSON.parse(raw);const parsed=performance.now();
    const model=initial?mod.validateInitialMap(value,manifest):mod.validatePublicCatalog(value,manifest);const validated=performance.now();
    return {ready_ms:ready??null,first_pins_upper_bound_ms:pins,stages_ms:{headers:headers-t,download:downloaded-headers,gzip:inflated-downloaded,utf8:decoded-inflated,sha256:hashed-decoded,parse:parsed-hashed,validation:validated-parsed},facilities:model.facilities.length,resources};
   });
   rows.push({mobile,cold:i===0,run:i,...result});console.log(JSON.stringify(rows.at(-1)));
  }
  await context.close();
 }
}finally{await browser.close();}
writeFileSync(output,JSON.stringify({browser:browser.version(),conditions:{desktop:'i7-11800H, unthrottled CPU, loopback; 1440x1000',mobile:'same host, 4x CPU slowdown, 10 Mbps down / 5 Mbps up, 40 ms latency; 390x844 DPR3; simulation, not physical phone',cache:'cold: cleared HTTP cache; warm: same context reload, conditional no-cache manifest/assets; gzip probe is a separate URL; external tile/Photon requests blocked'},rows},null,2)+'\n');
