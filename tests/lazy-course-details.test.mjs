import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {fixture,document,expand} from './native5-fixture.mjs';
import {renderOptional} from '../src/fairway/static/optional-facts.mjs';
const source=readFileSync(new URL('../src/fairway/static/app.js',import.meta.url),'utf8');
function harness(){
  const calls=[],context={URL,STYLES:{regulation:'Regulation'},document,renderOptional:(optional,options)=>{calls.push(options.subjectLabel);return renderOptional(optional,{...options,document});}};
  vm.createContext(context);vm.runInContext(source.slice(source.indexOf('function node('),source.indexOf('function mobile('))+source.slice(source.indexOf('function courseMetadata('),source.indexOf('function renderRanking(')),context);
  return {make:course=>context.courseMetadata(course),calls};
}
test('ordinary collapsed course details do not read or construct optional observations',()=>{
  const h=harness(),course=fixture().value.courses.find(c=>c.plan_eligible===true),optional=course.optional;
  let reads=0;Object.defineProperty(course,'optional',{get(){reads++;return optional;}});
  const details=h.make(course);assert.equal(details.tag,'details');assert.equal(details.open,false);assert.equal(details.children.length,1);assert.equal(details.children[0].tag,'summary');assert.equal(details.textContent,'Course details');assert.equal(reads,0);assert.equal(h.calls.length,0);
  details.dispatchEvent({type:'toggle'});assert.equal(reads,0);assert.equal(h.calls.length,0);
  expand(details);assert.equal(reads,1);assert.equal(h.calls.length,3);assert.match(details.textContent,/Preliminary public-play eligibility/);assert.match(details.textContent,/not a current quote/);assert.match(details.textContent,/role: unconfirmed/);
});
test('first native expansion keeps summary/focus targets and close-reopen retains all populated node identities',()=>{
  const h=harness(),course=fixture().value.courses.find(c=>c.plan_eligible===true),before=JSON.stringify(course),details=h.make(course),summary=details.children[0];
  expand(details);const children=[...details.children],calls=h.calls.length,text=details.textContent;
  details.open=false;details.dispatchEvent({type:'toggle'});expand(details);details.dispatchEvent({type:'toggle'});
  assert.equal(details.children[0],summary);assert.deepEqual(details.children,children);assert.equal(details.textContent,text);assert.equal(h.calls.length,calls);assert.equal(JSON.stringify(course),before);
  assert.deepEqual([...details.listeners.keys()],['toggle']);assert.equal(summary.tag,'summary');
});
test('expanding one card constructs only that card and keeps independent scoped data',()=>{
  const h=harness(),courses=fixture().value.courses.filter(c=>c.round_options.length),one=h.make(courses[0]),two=h.make(courses[1]);
  assert.equal(h.calls.length,0);expand(one);const firstCalls=h.calls.length;assert.ok(firstCalls>0);assert.equal(two.textContent,'Course details');
  const firstChildren=[...one.children];expand(two);assert.ok(h.calls.length>firstCalls);assert.deepEqual(one.children,firstChildren);assert.equal(one.open,true);assert.equal(two.open,true);
  assert.match(two.textContent,/Ordinary nonmember booking unavailable/);assert.doesNotMatch(one.textContent,/restaurant available/);
});
