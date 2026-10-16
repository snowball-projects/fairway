import test from 'node:test';
import assert from 'node:assert/strict';
import {rejectRawEvidence} from '../src/fairway/static/optional-facts.mjs';

for(const text of [
  'https://operator.example/fees?%41PI%5FKEY=TEST_ONLY',
  'https://operator.example/fees?api_\nkey=TEST_ONLY',
  'https:\tTEST_ONLY_USER:TEST_ONLY_PASSWORD@operator.example',
  'https://operator.example/fees?%61ccess%5Ftoken=TEST_ONLY',
])test(`credential normalization remains enforced: ${JSON.stringify(text)}`,()=>{
  assert.throws(()=>rejectRawEvidence({facilities:[{name:text}]}),/Private path/);
});
for(const text of [
  'Public golf.\nDated source only.',
  'https://operator.example/fees?course=%41&date=2026-10-15',
  'Recorded 50% price observation; conditions unchanged.',
])test(`public normalization control remains exact: ${JSON.stringify(text)}`,()=>{
  const value={facilities:[{name:text}]},before=structuredClone(value);
  assert.doesNotThrow(()=>rejectRawEvidence(value));assert.deepEqual(value,before);
});

test('repeated keys never suppress validation of a later private value',()=>{
  const rows=Array.from({length:100},()=>({name:'Public name',booking_conditions:'Dated source only.'}));
  rows.push({name:'Public name',booking_conditions:'Files kept in /tmp for review.'});
  assert.throws(()=>rejectRawEvidence({facilities:rows}),/Private path/);
});
test('an operational value never grants a later property key an operational role',()=>{
  const value={facilities:[{name:'/membership-info/'}],metadata:{'/membership-info/':'public'}};
  assert.throws(()=>rejectRawEvidence(value),/Private path/);
});
test('known keys remain subject to each record public projection boundary',()=>{
  assert.throws(()=>rejectRawEvidence({facilities:[{surprise:null}],source_licenses:[{surprise:null}]}),/nonpublic source-license/);
  assert.throws(()=>rejectRawEvidence({facilities:[{status:'retained'}],provenance:{notes:[{id:'note-id',status:'retained'}]}}),/IDs only/);
});
