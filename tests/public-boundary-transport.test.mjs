import test from 'node:test';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
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
