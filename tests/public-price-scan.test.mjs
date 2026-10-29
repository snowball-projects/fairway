import test from 'node:test';
import assert from 'node:assert/strict';
import {renderKnownOptional} from '../src/fairway/static/optional-facts.mjs';
import {fixture,document} from './native5-fixture.mjs';
for(const conditions of ['Printed /ea with 2 riders per cart.','$25 /ea; dated printed amount only.'])test('complete typed transport and popup preserve exact financial claim: '+conditions,()=>{
 const {value}=fixture();
 function update(item){if(Array.isArray(item))item.forEach(update);else if(item&&typeof item==='object'){if(item.billing_basis==='per_person'&&Object.hasOwn(item,'conditions'))item.conditions=conditions;Object.values(item).forEach(update);}}
 update(value);const before=JSON.stringify(value),row=value.courses.flatMap(c=>c.round_options).flatMap(r=>r.optional.price_observation).find(r=>r.conditions===conditions);assert.ok(row);
 const output=renderKnownOptional({price_observation:[row]},{subjectLabel:'Recorded price',document});assert.ok(output.textContent.includes(conditions));assert.equal(JSON.stringify(value),before);
});
