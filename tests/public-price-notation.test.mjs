import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {renderKnownOptional} from '../src/fairway/static/optional-facts.mjs';
import {loadPublicCatalog,validatePublicCatalog} from '../src/fairway/static/public-catalog.mjs';
import {fixture,document} from './native5-fixture.mjs';
const cases=JSON.parse(readFileSync(new URL('./fixtures/native5-ui/public-boundary-legacy-decisions.json',import.meta.url),'utf8')).complete_transport_fixture.cases;
for(const item of cases){test('complete notation transport: '+item.name,async()=>{
 const {value,manifest}=fixture();let changed=0;
 function update(v){if(Array.isArray(v))v.forEach(update);else if(v&&typeof v==='object'){if(v.id==='n-00000000-0000-4000-8000-000000000004'){Object.assign(v,{observation_id:'o-00000000-0000-4000-8000-000000000991',historical:true,billing_basis:null,currency:null,quantity:null,[item.field]:item.text});changed++;}Object.values(v).forEach(update);}}
 update(value);assert.ok(changed);const before=JSON.stringify(value);
 if(item.accept)assert.doesNotThrow(()=>validatePublicCatalog(value,manifest));else assert.throws(()=>validatePublicCatalog(value,manifest),/Private path/);
 const raw=JSON.stringify(value),hash=createHash('sha256').update(raw).digest('hex');manifest.files={'catalog.json':{path:`native-catalog-${hash}.json`,sha256:hash,bytes:Buffer.byteLength(raw)}};
 let calls=0;const fetcher=async(url,options)=>{assert.equal(options.credentials,'omit');assert.equal(options.mode,'same-origin');assert.ok(!options.body);assert.ok(++calls<=2);return new Response(calls===1?JSON.stringify(manifest):raw);};
 const pending=loadPublicCatalog('https://example.test/fairway/data/catalog-release.json',{fetcher});
 if(item.accept){const model=await pending,row=[...model.optionalObservations.values()].find(r=>r[item.field]===item.text);assert.ok(row);assert.equal(row.billing_basis,null);assert.equal(row.currency,null);assert.equal(row.quantity,null);assert.ok(renderKnownOptional({price_observation:[row]},{subjectLabel:'Dated price',document}).textContent.includes(item.text));}else await assert.rejects(pending,/Private path/);
 assert.equal(calls,2);assert.equal(JSON.stringify(value),before);
});}

