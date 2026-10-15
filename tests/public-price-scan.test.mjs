import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {rejectRawEvidence,renderKnownOptional} from '../src/fairway/static/optional-facts.mjs';
import {validatePublicCatalog} from '../src/fairway/static/public-catalog.mjs';
import {fixture,document} from './native5-fixture.mjs';

const cases=JSON.parse(readFileSync(new URL('./fixtures/native5-ui/per-each-guard.json',import.meta.url),'utf8'));
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
