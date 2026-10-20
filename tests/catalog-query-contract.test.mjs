// Generated read-only SQLite transport fixtures, never catalog authority.
import test from 'node:test';
import assert from 'node:assert/strict';
import chicago from './fixtures/sqlite-query/chicago-query.json' with {type:'json'};
import corica from './fixtures/sqlite-query/corica-query.json' with {type:'json'};
test('Chicago query retains unknown names and booking eligibility while exposing eight canonical arrivals',()=>{
  assert.equal(chicago.courses.length,8);assert.equal(chicago.destinations.length,8);
  assert.ok(chicago.courses.every(c=>c.name===null && c.nonmember_bookable===null && c.identity_status==='needs_review'));
  assert.ok(chicago.courses.every(c=>c.arrival?.kind==='reviewed_osm_point' && c.map_location && c.course_id!==c.facility_id));
  assert.equal(chicago.courses.filter(c=>c.nonmember_bookable===true).length,0);
  assert.ok(chicago.courses.every(c=>c.plan_eligible===true && c.planning_basis==='accepted_public_play_with_qualification' && c.booking_availability===null));
  for(const c of chicago.courses)assert.ok(chicago.destinations.some(d=>d.id===c.destination_id && d.scope==='course_arrival'));
});
test('Corica keeps three course identities, distinct physical lengths and one qualified facility routing target',()=>{
  assert.equal(corica.courses.length,3);assert.equal(corica.destinations.length,1);
  assert.equal(new Set(corica.courses.map(c=>c.course_id)).size,3);
  assert.deepEqual(corica.courses.map(c=>c.physical_holes).sort((a,b)=>a-b),[9,18,18]);
  assert.ok(corica.courses.every(c=>c.facility_physical_holes===45 && c.round_options.length===0 && c.arrival===null));
  assert.ok(corica.courses.every(c=>c.destination_id===corica.destinations[0].id));
  assert.equal(corica.destinations[0].scope,'facility_estimate');assert.ok(corica.destinations[0].qualification);
  // A routing adapter needs one vector per shared target, not three requests.
  assert.equal(new Set(corica.courses.map(c=>c.destination_id)).size,1);
});
test('paged query fixtures carry snapshot revision and complete-page metadata',()=>{
  for(const page of [chicago,corica]) {
    assert.equal(page.revision,1);assert.equal(page.has_more,false);
    assert.ok(page.total>=page.courses.length && page.limit>=page.courses.length && page.offset===0);
  }
});
