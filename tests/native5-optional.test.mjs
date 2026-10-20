import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fixture,fixtureBytes,document} from './native5-fixture.mjs';
import {OPTIONAL_DOMAINS,validateScopedOptional,renderOptional,rejectRawEvidence} from '../src/fairway/static/optional-facts.mjs';
import {OPTIONAL_SCHEMA} from '../src/fairway/static/optional-schema.mjs';
import {validatePublicCatalog} from '../src/fairway/static/public-catalog.mjs';
import {accessLabel,browseCard,courseMatches,cityLabel,displayAddress} from '../src/fairway/static/catalog-read.mjs';
const main=v=>v.courses.find(c=>c.plan_eligible===true);
const facility=v=>v.facilities.find(f=>f.facility_id===main(v).facility_id);
test('literal synthetic producer fixture remains exact and covers four independent subject scopes',()=>{
  assert.equal(createHash('sha256').update(fixtureBytes).digest('hex'),'af80563e815aaedda424b24eeeb42b985e6edd8b746306a8804fca6bc3454bef');
  const {value,manifest}=fixture(),model=validatePublicCatalog(value,manifest);
  assert.equal(model.optionalObservations.size,6);assert.equal(model.courses.length,3);assert.equal(model.facilities.length,3);assert.equal(model.destinations.size,2);
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
for(const domain of OPTIONAL_DOMAINS.filter(d=>d!=='quality_rating'))test(`explicit ${domain} rows retain nullable SQL columns and source envelope`,()=>{
  const {value}=fixture(),f=facility(value),schema=OPTIONAL_SCHEMA[domain];
  // Independent synthetic all-null operational cells exercise each domain shape; not an actual catalog claim.
  const row=Object.fromEntries(Object.keys(schema).map(k=>[k,null]));
  Object.assign(row,{id:'synthetic-domain-'+domain,observation_id:'synthetic-observation',facility_id:f.facility_id,status:'retained',conflict:false});
  if(domain==='architecture_event')row.credits=[];
  f.optional[domain].push(row);assert.ok(validateScopedOptional(value).has(domain+':'+row.id));
  assert.match(renderOptional(f.optional,{subjectLabel:'Facility',document}).textContent,/Unconfirmed/);
});
const mutations={
  'missing optional domain':v=>delete main(v).optional.practice_observation,
  'unknown optional alias':v=>main(v).optional.raw_prices=[],
  'wrong subject':v=>main(v).optional.practice_observation[0].course_id=v.courses[0].course_id,
  'mixed subjects':v=>main(v).optional.practice_observation[0].facility_id=facility(v).facility_id,
  'numeric boolean':v=>main(v).optional.practice_observation[0].driving_range_lighted=0,
  'unknown canonical column':v=>main(v).optional.practice_observation[0].range_lighting_alias=false,
  'missing canonical column':v=>delete main(v).optional.practice_observation[0].driving_range_available,
  'source URL mismatch':v=>main(v).optional.practice_observation[0].source_url='https://other.example/',
  'source license mismatch':v=>main(v).optional.practice_observation[0].source_license=null,
  'orphan source':v=>main(v).optional.practice_observation[0].source_id='missing',
  'duplicate observation':v=>main(v).optional.practice_observation.push(structuredClone(main(v).optional.practice_observation[0])),
  'quality population':v=>facility(v).optional.quality_rating.push({id:'not-approved'}),
  'changed shared round':v=>main(v).round_options[0].optional.price_observation[0].amount_min=1,
  'changed nested member':v=>main(v).round_options[0].members[0].repetitions=2,
  'missing member view':v=>main(v).round_options[0].members.pop(),
  'orphan component':v=>v.relationships.component[0].course_id='c-missing',
  'moved round owner':v=>v.relationships.round_option[0].course_id=main(v).course_id,
  'inventory access drift':v=>facility(v).course_inventory[0].access='restricted',
  'legacy raw evidence':v=>main(v).fact_groups=[],
  'note body':v=>v.provenance.notes=[{id:'note-public-id',text:'Raw evidence must remain private'}],
  'duplicate note ID':v=>v.provenance.notes=[{id:'note-id'},{id:'note-id'}],
};
for(const [name,mutate] of Object.entries(mutations))test(`fail closed on ${name}`,()=>{const {value,manifest}=fixture();mutate(value);assert.throws(()=>validatePublicCatalog(value,manifest));});
test('public provenance allows exact note IDs without exposing bodies',()=>{const {value,manifest}=fixture();value.provenance.notes=[{id:'preserved-note-id'}];const model=validatePublicCatalog(value,manifest);assert.deepEqual(model.provenance.notes,[{id:'preserved-note-id'}]);});
for(const path of ['/opt/private','/etc/passwd','//server/share','C:/private','Z:\\hidden','\\\\server\\share','file:///private','known (/var/secret)','key=/mnt/data'])test(`private token rejects in public values and keys: ${path}`,()=>{
  assert.throws(()=>rejectRawEvidence({innocent:path}),/Private path/);assert.throws(()=>rejectRawEvidence({[path]:'innocent'}),/Private path/);
});
test('text is rendered as textContent, without HTML or unsafe source URL links',()=>{
  const {value}=fixture(),optional=main(value).optional,row=optional.practice_observation[0];row.qualification='<img src=x onerror=alert(1)>';row.source_url='javascript:alert(1)';
  const output=renderOptional(optional,{subjectLabel:'Course',document});assert.ok(output.textContent.includes(row.qualification));assert.ok(output.children.every(n=>n.tag!=='img'));assert.ok(output.children[1].children.every(n=>n.tag!=='a'));
});

for(const prefix of [':',';',',','<','>','|','!','?','“','”','‘','’','«','»','`'])test(`punctuation-prefixed absolute path rejects: ${prefix}`,()=>{
  assert.throws(()=>rejectRawEvidence('label'+prefix+'/private/evidence'),/Private path/);
});
test('URL tokens and ordinary slash-compound text remain unchanged',()=>{
  for(const text of ['clubhouse/range', 'https://official.example/path?next=/course', 'Source: https://official.example/golf/course; practice/range'])assert.doesNotThrow(()=>rejectRawEvidence(text));
  assert.throws(()=>rejectRawEvidence('https://official.example/path then:/private/evidence'),/Private path/);
});

function visit(value,fn){if(Array.isArray(value))value.forEach(v=>visit(v,fn));else if(value&&typeof value==='object'){fn(value);Object.values(value).forEach(v=>visit(v,fn));}}
for(const status of ['retained','extracted','confirmed'])test(`all exact SQL observation statuses accept consistent shared envelopes: ${status}`,()=>{
  const {value,manifest}=fixture();visit(value,row=>{if(Object.hasOwn(row,'observation_id'))row.status=status;});
  assert.equal(validatePublicCatalog(value,manifest).optionalObservations.size,6);
});
test('retained observations can preserve a completely unknown public source/date envelope',()=>{
  const {value,manifest}=fixture();visit(value,row=>{if(Object.hasOwn(row,'observation_id'))Object.assign(row,{source_id:null,source_url:null,source_license:null,source_attribution:null,collected_on:null,observed_on:null,effective_from:null,effective_to:null,status:'retained',conflict:true,qualification:'Original qualification retained'});});
  const model=validatePublicCatalog(value,manifest);assert.equal(model.optionalObservations.size,6);assert.ok([...model.optionalObservations.values()].every(r=>r.source_id===null&&r.status==='retained'));
});
for(const status of [null,'unknown','documented',''])test(`reject invalid or missing SQL observation status ${status}`,()=>{
  const {value,manifest}=fixture();main(value).optional.practice_observation[0].status=status;assert.throws(()=>validatePublicCatalog(value,manifest),/envelope/);
});
for(const [key,changed] of Object.entries({collected_on:'2026-10-14',observed_on:'2099-01-01',effective_from:'2026-01-01',effective_to:'2027-01-01',status:'confirmed',conflict:false,qualification:'Different qualification'}))test(`one immutable observation cannot disagree across domains: ${key}`,()=>{
  const {value,manifest}=fixture();main(value).optional.practice_observation[0][key]=changed;assert.throws(()=>validatePublicCatalog(value,manifest),/immutable source observation/);
});
test('changing a source consistently on one row still rejects drift of a shared observation ID',()=>{
  const {value,manifest}=fixture(),row=main(value).optional.practice_observation[0];
  value.provenance.sources.push({id:'other-source',url:'https://other.example/source',license:'Other license',attribution:'Other attribution'});
  Object.assign(row,{source_id:'other-source',source_url:'https://other.example/source',source_license:'Other license',source_attribution:'Other attribution'});
  assert.throws(()=>validatePublicCatalog(value,manifest),/immutable source observation/);
});
function courseOwnedRound(value,{keepForeignMember=false}={}){
  const owner=main(value),raw=value.relationships.round_option[0],round=structuredClone(owner.round_options[0]);
  raw.facility_id=null;raw.course_id=owner.course_id;Object.assign(round,{facility_id:null,course_id:owner.course_id,scope:'course'});
  if(!keepForeignMember){value.relationships.round_component=value.relationships.round_component.filter(m=>m.course_id===owner.course_id||owner.components.some(p=>p.id===m.component_id));round.members=structuredClone(value.relationships.round_component);}
  for(const f of value.facilities)f.round_options=[];
  for(const c of value.courses)c.round_options=(c.course_id===owner.course_id||keepForeignMember&&c.facility_id===owner.facility_id)?[structuredClone(round)]:[];
}
test('valid course-owned round keeps only its own course/component membership',()=>{
  const {value,manifest}=fixture();courseOwnedRound(value);assert.equal(validatePublicCatalog(value,manifest).optionalObservations.size,6);
});
for(const foreign of ['course','component'])test(`course-owned round rejects another ${foreign} even at the same facility`,()=>{
  const {value,manifest}=fixture();courseOwnedRound(value,{keepForeignMember:true});
  if(foreign==='component'){
    const other=value.courses.find(c=>c.plan_eligible===false),component={...value.relationships.component[0],id:'p-foreign',course_id:other.course_id};
    value.relationships.component.push(component);other.components.push({...component,optional:structuredClone(Object.fromEntries(OPTIONAL_DOMAINS.map(k=>[k,[]])))});
    const member=value.relationships.round_component.find(m=>m.course_id!==null);member.component_id=component.id;member.course_id=null;for(const c of value.courses)if(c.round_options.length)c.round_options[0].members=structuredClone(value.relationships.round_component);
  }
  assert.throws(()=>validatePublicCatalog(value,manifest),/round component membership/);
});

test('one shared round can reach the same course through both a course member and its component',()=>{
  const {value,manifest}=fixture(),owner=main(value),raw=value.relationships.round_component;
  raw.push({...raw[0],id:'l-additional-direct-member',course_id:owner.course_id,ordinal:2});
  for(const subject of [...value.facilities,...value.courses])for(const round of subject.round_options)round.members=structuredClone(raw);
  const before=structuredClone(value),model=validatePublicCatalog(value,manifest);
  assert.equal(model.optionalObservations.size,6);assert.equal(model.courseById.get(owner.course_id).round_options.length,1);
  assert.deepEqual(value,before);
  owner.round_options=[];assert.throws(()=>validatePublicCatalog(value,manifest),/relationship membership/);
});
test('owner-specific aliases remain separate when names match and reject a switched nested subject',()=>{
  const {value,manifest}=fixture(),course=main(value),f=facility(value);
  const fa={id:'a-facility',name:'Shared alias',facility_id:f.facility_id,course_id:null},ca={id:'a-course',name:'Shared alias',facility_id:null,course_id:course.course_id};
  value.relationships.alias.push(fa,ca);f.aliases=[structuredClone(fa)];course.aliases=[structuredClone(ca)];
  const model=validatePublicCatalog(value,manifest);assert.deepEqual(model.facilityById.get(f.facility_id).aliases,[fa]);assert.deepEqual(model.courseById.get(course.course_id).aliases,[ca]);
  course.aliases=[structuredClone(fa)];assert.throws(()=>validatePublicCatalog(value,manifest),/relationship membership/);
});
test('valid relationship and subject ordering is retained without changing membership or input',()=>{
  const {value,manifest}=fixture();value.facilities.reverse();value.courses.reverse();
  for(const rows of Object.values(value.relationships))rows.reverse();
  for(const subject of [...value.facilities,...value.courses]){
    subject.course_ids?.reverse();subject.course_inventory?.reverse();subject.components?.reverse();subject.aliases.reverse();subject.tee_sets?.reverse();subject.round_options.reverse();
    for(const round of subject.round_options){round.members.reverse();round.tee_sets.reverse();}
  }
  const before=structuredClone(value),model=validatePublicCatalog(value,manifest);
  assert.deepEqual(model.courses.map(c=>c.course_id),value.courses.map(c=>c.course_id));assert.equal(model.optionalObservations.size,6);assert.deepEqual(value,before);
});


test('core citations work without an import ledger and preserve source and date',()=>{
  const {value,manifest}=fixture();delete value.provenance.intake;
  const citation={entity_type:'course',entity_id:main(value).course_id,source_id:value.provenance.sources[0].id,collected_on:'2026-10-15',status:'extracted'};
  value.provenance.citations=[citation];
  assert.deepEqual(validatePublicCatalog(value,manifest).provenance.citations,[citation]);
  assert.equal(Object.hasOwn(validatePublicCatalog(value,manifest).provenance,'intake'),false);
});
for(const [label,change] of Object.entries({orphan:c=>c.entity_id='missing',source:c=>c.source_id='missing',date:c=>c.collected_on='2026-02-30',status:c=>c.status='imported',process:c=>c.batch_id='old-run',kind:c=>c.entity_type='toString'}))test(`invalid core citation rejects: ${label}`,()=>{
  const {value,manifest}=fixture();value.provenance.citations=[{entity_type:'course',entity_id:main(value).course_id,source_id:value.provenance.sources[0].id,collected_on:null,status:'confirmed'}];change(value.provenance.citations[0]);
  assert.throws(()=>validatePublicCatalog(value,manifest),/core citation/);
});
test('duplicate core citation rejects',()=>{
  const {value,manifest}=fixture(),citation={entity_type:'course',entity_id:main(value).course_id,source_id:null,collected_on:null,status:'extracted'};value.provenance.citations=[citation,{...citation}];
  assert.throws(()=>validatePublicCatalog(value,manifest),/Duplicate core citation/);
});
