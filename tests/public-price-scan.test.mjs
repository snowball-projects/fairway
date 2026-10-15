import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {rejectRawEvidence,renderKnownOptional} from '../src/fairway/static/optional-facts.mjs';
import {loadPublicCatalog,validatePublicCatalog} from '../src/fairway/static/public-catalog.mjs';
import {fixture,document} from './native5-fixture.mjs';

const cases=['per-each-guard.json','per-each-unicode-policy.json','public-url-termination.json'].flatMap(name=>JSON.parse(readFileSync(new URL('./fixtures/native5-ui/'+name,import.meta.url),'utf8')));
for(const item of cases)test('public financial scan: '+item.name,()=>{
 const value=structuredClone(item.value),before=structuredClone(value);
 if(item.accept)assert.doesNotThrow(()=>rejectRawEvidence(value));
 else assert.throws(()=>rejectRawEvidence(value),/Private path/);
 assert.deepEqual(value,before);
});
for(const conditions of ['Printed /ea with 2 riders per cart.','$25 /ea; dated printed amount only.'])test('complete typed transport and popup preserve exact financial claim: '+conditions,()=>{
 const {value,manifest}=fixture();
 function update(item){if(Array.isArray(item))item.forEach(update);else if(item&&typeof item==='object'){if(item.billing_basis==='per_person'&&Object.hasOwn(item,'conditions'))item.conditions=conditions;Object.values(item).forEach(update);}}
 update(value);const before=JSON.stringify(value),model=validatePublicCatalog(value,manifest),row=[...model.optionalObservations.values()].find(r=>r.conditions===conditions);assert.ok(row);
 const output=renderKnownOptional({price_observation:[row]},{subjectLabel:'Recorded price',document});assert.ok(output.textContent.includes(conditions));assert.equal(JSON.stringify(value),before);
});

for(const [conditions,accept] of [
 ['$25 /ea\u0085Dated only.',true],
 ['Printed /ea\ufeffwith 2 riders per cart.',true],
 ['$25 /ea then\u0085/private/evidence',false],
 ['$25 /ea then\ufeff/private/evidence',false],
])test('complete immutable two-GET load retains character policy: '+JSON.stringify(conditions),async()=>{
 const {value,manifest}=fixture();
 function update(item){if(Array.isArray(item))item.forEach(update);else if(item&&typeof item==='object'){if(item.billing_basis==='per_person'&&Object.hasOwn(item,'conditions'))item.conditions=conditions;Object.values(item).forEach(update);}}
 update(value);const raw=JSON.stringify(value),hash=createHash('sha256').update(raw).digest('hex');
 manifest.files={'catalog.json':{path:`native-catalog-${hash}.json`,sha256:hash,bytes:Buffer.byteLength(raw)}};
 const before=JSON.stringify({value,manifest}),calls=[];
 const fetcher=async(url,options)=>{calls.push({url:String(url),options});return new Response(calls.length===1?JSON.stringify(manifest):raw);};
 const pending=loadPublicCatalog('https://example.test/fairway/data/catalog-release.json',{fetcher});
 if(accept){
  const model=await pending,row=[...model.optionalObservations.values()].find(r=>r.conditions===conditions);assert.ok(row);
  const output=renderKnownOptional({price_observation:[row]},{subjectLabel:'Recorded price',document});assert.ok(output.textContent.includes(conditions));
 }else await assert.rejects(pending,/Private path/);
 assert.equal(calls.length,2);assert.ok(calls.every(c=>c.options.credentials==='omit'&&c.options.mode==='same-origin'&&!c.options.body));
 assert.equal(JSON.stringify({value,manifest}),before);
});

for(const [qualification,accept] of [
 ['See “https://official.example”/private/evidence',false],
 ['See ‘https://official.example’C:/private/evidence',false],
 ['See «https://official.example»\\\\server\\private',false],
 ['See “https://official.example/course” Dated source only.',true],
])test('complete synchronized qualification URL termination: '+qualification,async()=>{
 const {value,manifest}=fixture();let updated=0;
 function update(item){if(Array.isArray(item))item.forEach(update);else if(item&&typeof item==='object'){if(item.observation_id==='o-00000000-0000-4000-8000-000000000001'){item.qualification=qualification;updated++;}Object.values(item).forEach(update);}}
 update(value);assert.equal(updated,8);const before=JSON.stringify(value);
 if(accept)assert.doesNotThrow(()=>validatePublicCatalog(value,manifest));else assert.throws(()=>validatePublicCatalog(value,manifest),/Private path/);
 const raw=JSON.stringify(value),hash=createHash('sha256').update(raw).digest('hex');manifest.files={'catalog.json':{path:`native-catalog-${hash}.json`,sha256:hash,bytes:Buffer.byteLength(raw)}};
 let calls=0;const fetcher=async(url,options)=>{assert.equal(options.credentials,'omit');assert.ok(!options.body);assert.ok(++calls<=2);return new Response(calls===1?JSON.stringify(manifest):raw);};
 const pending=loadPublicCatalog('https://example.test/fairway/data/catalog-release.json',{fetcher});
 if(accept){const model=await pending;for(const [key,row] of model.optionalObservations)if(row.qualification===qualification){const domain=key.slice(0,key.indexOf(':'));assert.ok(renderKnownOptional({[domain]:[row]},{subjectLabel:'Known fact',document}).textContent.includes(qualification));}}else await assert.rejects(pending,/Private path/);
 assert.equal(calls,2);assert.equal(JSON.stringify(value),before);
});
