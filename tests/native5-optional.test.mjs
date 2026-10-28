import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fixture,fixtureBytes,document} from './native5-fixture.mjs';
import {OPTIONAL_DOMAINS,renderOptional} from '../src/fairway/static/optional-facts.mjs';
import {OPTIONAL_SCHEMA} from '../src/fairway/static/optional-schema.mjs';
import {CatalogRead} from '../src/fairway/static/catalog-read.mjs';
import {accessLabel,browseCard,courseMatches,cityLabel,displayAddress} from '../src/fairway/static/catalog-read.mjs';
const main=v=>v.courses.find(c=>c.plan_eligible===true);
const facility=v=>v.facilities.find(f=>f.facility_id===main(v).facility_id);
test('literal synthetic producer fixture remains exact and covers four independent subject scopes',()=>{
  assert.equal(createHash('sha256').update(fixtureBytes).digest('hex'),'af80563e815aaedda424b24eeeb42b985e6edd8b746306a8804fca6bc3454bef');
  const {value}=fixture(),model=new CatalogRead(value);
  assert.equal(model.courses.length,3);assert.equal(model.facilities.length,3);assert.equal(model.destinations.size,2);
  assert.deepEqual(OPTIONAL_DOMAINS,Object.keys(facility(value).optional).sort());
  const course=main(value),card=browseCard(course,model.destinations);
  assert.equal(card.nonmember_bookable,null);assert.equal(card.plan_eligible,true);assert.equal(card.planning_basis,'accepted_public_play_with_qualification');
  assert.equal(card.optional.amenity_observation.length,0);assert.equal(facility(value).optional.amenity_observation[0].restaurant_available,true);
  assert.equal(card.components[0].optional.physical_characteristics.length,1);assert.equal(card.round_options[0].optional.price_observation.length,1);
});

test('nullable access stays unconfirmed and never becomes restricted or confirmed booking',()=>{
  const {value}=fixture(),unknown=value.courses.find(c=>c.access===null);
  assert.equal(accessLabel(unknown.access),'Access unconfirmed');assert.equal(courseMatches(unknown,{access:'unknown'}),true);assert.equal(courseMatches(unknown,{access:'restricted'}),false);assert.equal(courseMatches(unknown,{access:'nonmember'}),false);
  assert.equal(cityLabel({address:{text:'Do not parse this, Chicago, IL'}}),null);
  assert.equal(displayAddress({street_line1:'1 Recorded Rd',city:'Recorded City',region:'IL',postal_code:'60000'}),'1 Recorded Rd, Recorded City, IL, 60000');
});

test('rendered false lighting preserves unknown range existence and scope without facility inheritance',()=>{
  const course=main(fixture().value),output=renderOptional(course.optional,{subjectLabel:'Course: synthetic',document});
  const text=output.textContent;
  assert.match(text,/driving range lighted No/);assert.match(text,/driving range available Unconfirmed/);assert.match(text,/putting green count 2/);assert.match(text,/Scope: Course: synthetic/);assert.doesNotMatch(text,/restaurant/);
});

test('price rendering retains every recorded condition and unknown cell, conflict and historical qualification',()=>{
  const round=main(fixture().value).round_options[0],row=round.optional.price_observation[0];
  const output=renderOptional(round.optional,{subjectLabel:'Round: paired 18',document}),text=output.textContent;
  for(const key of Object.keys(OPTIONAL_SCHEMA.price_observation).filter(k=>!['id','observation_id','facility_id','course_id','round_id','source_id','source_url','source_license','source_attribution','collected_on','observed_on','effective_from','effective_to','status','conflict','qualification'].includes(k)))assert.ok(text.includes(key.replaceAll('_',' ')),key);
  for(const marker of ['historical','conflicting observations','USD','nonresident','adult','weekday mask 31','25','45','per_person','Unconfirmed',row.qualification,'not a current quote or booking offer'])assert.ok(text.includes(marker),marker);
  assert.equal(output.children[1].children.at(-1).href,row.source_url);
});

test('architecture retains multiple credits, unknown role and unknown year rather than first-credit reduction',()=>{
  const part=main(fixture().value).components[0],output=renderOptional(part.optional,{subjectLabel:'Component',document}),text=output.textContent;
  for(const credit of part.optional.architecture_event[0].credits)assert.ok(text.includes(credit.name));
  assert.match(text,/role: unconfirmed/);assert.match(text,/event year Unconfirmed/);assert.match(text,/renovation/);
});

test('text is rendered as textContent, without HTML or unsafe source URL links',()=>{
  const {value}=fixture(),optional=main(value).optional,row=optional.practice_observation[0];row.qualification='<img src=x onerror=alert(1)>';row.source_url='javascript:alert(1)';
  const output=renderOptional(optional,{subjectLabel:'Course',document});assert.ok(output.textContent.includes(row.qualification));assert.ok(output.children.every(n=>n.tag!=='img'));assert.ok(output.children[1].children.every(n=>n.tag!=='a'));
});
