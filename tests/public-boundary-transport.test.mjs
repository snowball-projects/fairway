import test from 'node:test';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fixture} from './native5-fixture.mjs';
import {validatePublicCatalog,loadPublicCatalog} from '../src/fairway/static/public-catalog.mjs';
const cases=JSON.parse(readFileSync(new URL('./fixtures/native5-ui/public-boundary-dto.json',import.meta.url),'utf8'));
const rawCases=JSON.parse(readFileSync(new URL('./fixtures/native5-ui/public-boundary-raw-url-controls.json',import.meta.url),'utf8'));
const decisions=new Map(JSON.parse(readFileSync(new URL('./fixtures/native5-ui/public-boundary-conservative-decisions.json',import.meta.url),'utf8')).map(c=>[c.name,c.accept]));
const syntaxCases=JSON.parse(readFileSync(new URL('./fixtures/native5-ui/public-boundary-credential-syntax.json',import.meta.url),'utf8'));
for(const item of [...cases,...rawCases,...syntaxCases,...JSON.parse(readFileSync(new URL('./fixtures/native5-ui/public-boundary-scheme-userinfo.json',import.meta.url),'utf8'))].map(c=>({...c,accept:decisions.get(c.name)??c.accept})))test('complete credential/path boundary and twoGET: '+item.target+' '+item.text,async()=>{
 const {value,manifest}=fixture();
 if(item.target==='license')value.source_licenses.push({source_url:item.text,license:'CC BY-SA'});else {const column=item.target==='website'?'website':'booking_conditions',subject=value.courses[0].course_id;function update(v){if(Array.isArray(v))v.forEach(update);else if(v&&typeof v==='object'){if(v.course_id===subject&&Object.hasOwn(v,column))v[column]=item.text;Object.values(v).forEach(update);}}update(value);}
 const before=JSON.stringify(value);
 if(item.accept)assert.doesNotThrow(()=>validatePublicCatalog(value,manifest));else assert.throws(()=>validatePublicCatalog(value,manifest));
 const hash=createHash('sha256').update(before).digest('hex');manifest.files={'catalog.json':{path:`native-catalog-${hash}.json`,bytes:Buffer.byteLength(before),sha256:hash}};
 let calls=0;const fetcher=async(url,options)=>{assert.equal(options.credentials,'omit');assert.equal(options.mode,'same-origin');assert.ok(!options.body);assert.ok(++calls<=2);return new Response(calls===1?JSON.stringify(manifest):before);};
 const pending=loadPublicCatalog('https://offline.invalid/data/catalog-release.json',{fetcher});
 if(item.accept){const model=await pending;if(item.target!=='license')assert.equal(model.courseById.get(value.courses[0].course_id)[item.target==='website'?'website':'booking_conditions'],item.text);}else await assert.rejects(pending);
 assert.equal(calls,2);assert.equal(JSON.stringify(value),before);
});

test('shipped link normalization makes scheme-only userinfo a credential-bearing href',()=>{
 const app=readFileSync(new URL('../src/fairway/static/app.js',import.meta.url),'utf8');
 const start=app.indexOf('function knownLink('),end=app.indexOf('\nfunction knownAddress(',start);
 assert.ok(start>=0&&end>start);
 for(const scheme of ['http','https']){
  const text=scheme+':review-user:TEST_ONLY_PASSWORD@operator.example/fees';
  const container={children:[],append(n){this.children.push(n);}},context={URL,node:(tag,label)=>({tag,label})};
  vm.createContext(context);vm.runInContext(app.slice(start,end),context);context.knownLink(container,text,'Official website');
  assert.equal(container.children.length,1);const normalized=new URL(container.children[0].href);
  assert.equal(normalized.username,'review-user');assert.equal(normalized.password,'TEST_ONLY_PASSWORD');
 }
});
