import test from 'node:test';
import assert from 'node:assert/strict';
import corica from './fixtures/catalog-native/course-corica-research21-example.json' with {type:'json'};
import {courseMatches,sortCourses,comparablePrice,browseCard} from '../src/fairway/static/catalog-read.mjs';
const source=corica.courses[0];
const group=(amount,extra={})=>({id:'test-observation',course_id:'c-test',module:'prices',observed_on:'2026-10-14',collected_on:'2026-10-14',source_url:'https://example.invalid/test-source',status:'extracted',conflict:false,payload:{currency:'USD',basis:'18-hole-walking-adult',amount,current_rate:true,unconditional:true,...extra}});
test('physical course length and documented rounds stay distinct, with unknown styles and all access browse',()=>{
  const nine={...source,physical_holes:9,round_options:[{round_holes:18,scope:'facility',members:[{course_id:source.course_id}]}],access:'private',plan_eligible:false};
  assert.equal(courseMatches(nine),true);assert.equal(courseMatches(nine,{holes:'18'}),false);assert.equal(courseMatches(nine,{roundHoles:'18'}),true);
  assert.equal(courseMatches(nine,{access:'nonmember'}),false);assert.equal(courseMatches(nine,{style:'par_3'}),false);assert.equal(courseMatches(nine,{style:'unknown'}),true);
});
test('price unknown, historical ranges, conditions, conflicting observations and differing bases never sort as current comparable fees',()=>{
  const row={...source,course_id:'c-test',fact_groups:[]},context={currency:'USD',basis:'18-hole-walking-adult'};
  assert.equal(comparablePrice(row,context),null);
  for(const payload of [{historical:true},{current_rate:false},{unconditional:false},{basis:'9-hole-riding'},{amount:null,green_fee_low:15,green_fee_high:30}]){
    row.fact_groups=[group(20,payload)];assert.equal(comparablePrice(row,context),null);
  }
  row.fact_groups=[group(0)];assert.equal(comparablePrice(row,context),0);
  row.fact_groups=[group(20),group(25)];assert.equal(comparablePrice(row,context),null);
  row.fact_groups=[{...group(20),conflict:true}];assert.equal(comparablePrice(row,context),null);
});
test('missing map/arrival and explicit suppressed address stay honest, facility point does not become entrance',()=>{
  const row={...source,map_location:null,arrival:null,address:null,destination_id:null};const card=browseCard(row,new Map());
  assert.equal(card.coordinate,null);assert.equal(card.arrival,null);assert.equal(card.routing_target,null);assert.equal(card.maximum_seconds,null);assert.equal(card.address,'Address not recorded');
});
test('native unnamed IDs remain distinct; unknown hole counts sort after known physical length',()=>{
  const a={...source,name:null,physical_holes:null,course_id:'c-a'},b={...source,name:null,physical_holes:9,course_id:'c-b'};
  assert.deepEqual(sortCourses([a,b],'holes').map(c=>c.course_id),['c-b','c-a']);
});

test('a newer or equally latest conflicting comparable observation prevents resurrection of an older fee',()=>{
  const context={currency:'USD',basis:'18-hole-walking-adult'},row={...source,course_id:'c-test'};
  const older={...group(20),observed_on:'2026-10-13'},newer={...group(30),conflict:true};
  for(const groups of [[older,newer],[newer,older],[older,{...group(20),conflict:true}]]){
    row.fact_groups=groups;assert.equal(comparablePrice(row,context),null);
  }
  row.fact_groups=[{...older,conflict:true},group(30)];assert.equal(comparablePrice(row,context),30);
  row.fact_groups=[older,{...newer,payload:{...newer.payload,basis:'9-hole-riding'}}];assert.equal(comparablePrice(row,context),20);
  row.fact_groups=[older,{...newer,course_id:'c-another'}];assert.equal(comparablePrice(row,context),20);
});
