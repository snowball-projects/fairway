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
