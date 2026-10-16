import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {rejectRawEvidence} from '../src/fairway/static/optional-facts.mjs';
const load=name=>JSON.parse(readFileSync(new URL('./fixtures/native5-ui/'+name,import.meta.url),'utf8'));
const decisions=new Map(load('public-boundary-conservative-decisions.json').map(c=>[c.name,c.accept]));
const cases=[...load('public-boundary.json'),...load('public-boundary-credential-path.json'),...load('public-boundary-raw-url-controls.json'),...load('public-boundary-credential-syntax.json'),...load('public-boundary-scheme-userinfo.json')].map(c=>({...c,accept:decisions.get(c.name)??c.accept}));
for(const item of cases)test('explicit serialization privacy boundary: '+item.name,()=>{
 const value=structuredClone(item.value),before=structuredClone(value);
 if(item.accept)assert.doesNotThrow(()=>rejectRawEvidence(value));else assert.throws(()=>rejectRawEvidence(value));
 assert.deepEqual(value,before);
});
for(const item of load('public-boundary-802.json').occurrences)test('actual802 literal row: '+item.id+' '+item.field,()=>{
 const before=structuredClone(item.context);assert.equal(before[item.field],item.text);
 assert.doesNotThrow(()=>rejectRawEvidence(item.text,item.path));
 const value={facilities:[{optional:{price_observation:[item.context]}}]};
 assert.doesNotThrow(()=>rejectRawEvidence(value));assert.deepEqual(item.context,before);
});
