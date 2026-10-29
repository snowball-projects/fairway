import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {renderKnownOptional} from '../src/fairway/static/optional-facts.mjs';
import {fixture,document} from './native5-fixture.mjs';
const cases=JSON.parse(readFileSync(new URL('./fixtures/native5-ui/public-boundary-legacy-decisions.json',import.meta.url),'utf8')).complete_transport_fixture.cases;
for(const item of cases.filter(item=>item.accept))test('popup preserves exact notation: '+item.name,()=>{
 const {value}=fixture();const row=value.courses.flatMap(c=>c.round_options).flatMap(r=>r.optional.price_observation).find(r=>r.id==='n-00000000-0000-4000-8000-000000000004');
 Object.assign(row,{historical:true,billing_basis:null,currency:null,quantity:null,[item.field]:item.text});
 assert.ok(renderKnownOptional({price_observation:[row]},{subjectLabel:'Dated price',document}).textContent.includes(item.text));
});
