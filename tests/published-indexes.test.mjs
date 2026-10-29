import test from 'node:test';
import assert from 'node:assert/strict';
import {CatalogRead} from '../src/fairway/static/catalog-read.mjs';
import {catalogIndexes} from '../scripts/catalog-indexes.mjs';

test('published orders and sibling indexes are read without sorting or relabeling records',()=>{
 const facilities=[{facility_id:'f-one',name:'Facility'},{facility_id:'f-alone',name:'Álone'}];
 const courses=[
  {course_id:'c-z',facility_id:'f-one',name:'Zulu',physical_holes:null},
  {course_id:'c-a',facility_id:'f-one',name:'alpha',physical_holes:9},
  {course_id:'c-i',facility_id:null,name:'Independent',physical_holes:18},
 ];
 const destinations=[{id:'d-one'}],value={facilities,courses,destinations},indexes=catalogIndexes(value);
 const compare=String.prototype.localeCompare,sort=Array.prototype.sort;
 let model;
 try {
  String.prototype.localeCompare=()=>assert.fail('runtime collation');
  Array.prototype.sort=()=>assert.fail('runtime sort');
  model=new CatalogRead({...value,indexes:JSON.parse(JSON.stringify(indexes))});
 } finally {String.prototype.localeCompare=compare;Array.prototype.sort=sort;}
 assert.deepEqual(model.browseEntries.name,[facilities[1],courses[1],courses[2],courses[0]]);
 assert.deepEqual(model.browseEntries.holes,[courses[1],courses[2],facilities[1],courses[0]]);
 assert.deepEqual(model.browseGroup('f-one','name'),[courses[1],courses[0]]);
 assert.deepEqual(model.facilityCourses(null),[courses[2]]);
 assert.equal(model.courseById.get('c-i'),courses[2]);
 assert.equal(model.facilityById.get('f-alone'),facilities[1]);
 assert.equal(model.destinations.get('d-one'),destinations[0]);
 assert.equal(model.mapRecordById.get('c-i').record_kind,'course');
 assert.equal(model.browseIndependent.name[0],courses[2]);
});
