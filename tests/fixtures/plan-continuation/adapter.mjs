import pinnedProtocol from './protocol.json' with {type:'json'};
import {PROTOCOL_SHA} from '../../../src/fairway/static/logical-transport.mjs';
import {canonicalRequest} from '../../../src/fairway/static/preparation-dto.mjs';
const casesFor={held:['admitted-without-upstream','held-chunk','clear-while-held','edit-while-held','clean-stale-chunk-not-logical-terminal','explicit-trusted-retry-complete'],pool:['full-pool-24-complete-76-pending','full-pool-complete-logical-terminal'],limited:['deadline-limited-retains-provisional-vectors'],area:['two-origins-clean-chunk-area-still-pending','two-origins-point-area-complete']};
const clone=structuredClone,pinnedCanonical=canonicalRequest(pinnedProtocol);
export function createProtocolAdapter(fixture,{scenario='held',autoAdvance=false}={}) {
  if(fixture.fixture_only!==true||canonicalRequest(fixture)!==pinnedCanonical||!casesFor[scenario])throw new Error('Pinned protocol fixture required');
  const cases=new Map(fixture.cases.map(c=>[c.case,c])),timeline=casesFor[scenario].map(n=>cases.get(n));let stage=0,admitted=false,body=null,timer=null;
  const metrics={posts:0,events:0,pages:0,catalog:0,resolutions:0,logicalSessionIds:new Set(),requests:[],nativeDispatches:0,hostAdvances:0};
  const initial=timeline[0].read.pages.flatMap(p=>p.courses),facilityRows=new Map(),destinations=new Map();
  for(const row of initial){const c=row.course;const f=facilityRows.get(c.facility_id)||{facility_id:c.facility_id,name:c.facility_name,state:c.state,country:c.country,county:null,physical_holes:c.facility_physical_holes,inventory_complete:c.inventory_complete,access:null,access_qualification:null,website:c.facility_website,website_status:null,website_checked_on:null,map_location:c.map_location,address:c.facility_address_text?{text:c.facility_address_text,purpose:c.facility_address_purpose,scope:'facility'}:null,course_inventory:[],course_ids:[],course_count:0,documented_course_ids:[],documented_course_count:0,fact_groups:[]};
    f.course_inventory.push({course_id:c.course_id,name:c.name,physical_holes:c.physical_holes,identity_status:c.identity_status,access:c.access,nonmember_bookable:c.nonmember_bookable});f.course_ids.push(c.course_id);f.course_count++;
    if(c.identity_status==='operator_defined'){f.documented_course_ids.push(c.course_id);f.documented_course_count++;}facilityRows.set(c.facility_id,f);if(row.routing_target)destinations.set(row.routing_target.id,row.routing_target);
  }
  const qualification='Synthetic browse projection of the frozen07a6806 native course DTO context, selected offline test window only; no certified facility inventory or national coverage.';
  const release=timeline[0].read.events_response.catalog_release_key,revision=timeline[0].read.events_response.catalog_revision;
  const adapter={fixtureOnly:true,protocolSha:PROTOCOL_SHA,protocol:'immutable-plan-07a6806',policy:{label:'literal synthetic logical-plan fixture'},metrics,
    supportsInput(request,generation){return timeline.some(c=>c.post&&canonicalRequest(c.post.body)===canonicalRequest({...request,generation}));},
    requestKeyFor(request,generation){return timeline.find(c=>c.post&&canonicalRequest(c.post.body)===canonicalRequest({...request,generation}))?.post.response.request_key;},
    attestAdmission(reply,request,generation){const original=timeline.find(c=>c.post&&canonicalRequest(c.post.body)===canonicalRequest({...request,generation}))?.post.response;return Boolean(original&&['session_id','generation','request_key','catalog_revision','catalog_release_key'].every(k=>original[k]===reply[k]));},
    attestLogicalStop(result){return timeline.some(c=>c.read.events_response.terminal&&canonicalRequest(c.read.events_response.terminal)===canonicalRequest(result.terminal)&&['session_id','generation','request_key','catalog_revision','catalog_release_key','snapshot_sequence','operation_active','upstream_started'].every(k=>c.read.events_response[k]===result[k]));},
    onSessionReady(session){adapter.sessionForReview=session;},offlineMap(L,map){adapter.map=map;},async resolveOrigin(){metrics.resolutions++;return {features:[]};},
    advance(name){const index=timeline.findIndex(c=>c.case===name);if(index<stage||index<0)throw new Error('Invalid fixture host advance');if(timeline[index].post&&index!==stage)throw new Error('Fixture input must be posted');clearTimeout(timer);stage=index;metrics.hostAdvances++;},
    stop(){clearTimeout(timer);},
    async fetcher(path,options){
      metrics.requests.push({path,method:options.method});const url=new URL(path,'https://reserved.invalid');
      const fail=(code,status=409,latest=null,recovery='none')=>Response.json({status,code,message:'Offline fixture operation unavailable',retryable:false,operation_started:admitted?true:null,engine_unknown:null,latest,recovery},{status});
      if(options.authorization?.allowed!==true||options.authorization?.caller!=='offline-reviewer')return fail('unauthorized',401);
      if(url.pathname.startsWith('/api/v1/catalog/')){
        metrics.catalog++;const kind=url.pathname.split('/').at(-1),rows=kind==='courses'?initial.map(r=>r.course):kind==='facilities'?[...facilityRows.values()]:null;
        if(!rows)return fail('invalid_catalog_kind',400);
        if((url.searchParams.has('expected_revision')&&Number(url.searchParams.get('expected_revision'))!==revision)||(url.searchParams.has('expected_release_key')&&url.searchParams.get('expected_release_key')!==release))return fail('catalog_release_changed');
        const offset=Number(url.searchParams.get('offset')),limit=Number(url.searchParams.get('limit'));
        return Response.json({revision,catalog_release_key:release,[kind]:clone(rows.slice(offset,offset+limit)),destinations:kind==='courses'?clone([...destinations.values()]):[],offset,limit,total:rows.length,has_more:offset+limit<rows.length,qualification});
      }
      if(options.method==='POST'){
        const incoming=JSON.parse(options.body);let index=timeline.findIndex(c=>c.post&&canonicalRequest(c.post.body)===canonicalRequest(incoming));
        if(admitted&&canonicalRequest(incoming)===canonicalRequest(body))return Response.json(clone(timeline[stage].read.events_response));
        if(index<0||index<stage)return fail('fixture_request_unavailable',400);
        if(admitted&&incoming.generation<=body.generation)return fail('generation_conflict');
        stage=index;body=clone(incoming);admitted=true;metrics.posts++;metrics.logicalSessionIds.add(timeline[stage].post.response.session_id);
        if(autoAdvance){clearTimeout(timer);const next=index===0&&scenario==='held'?1:scenario==='pool'||scenario==='area'?1:index===3&&scenario==='held'?4:null;
          if(next!==null)timer=setTimeout(()=>{if(stage<next){stage=next;metrics.hostAdvances++;}},800);}
        return Response.json(clone(timeline[stage].post.response));
      }
      if(!admitted)return fail('session_not_found',404);
      const read=timeline[stage].read,pointer=clone(read.events_response),query=url.searchParams;
      if(url.pathname!==`/api/v1/preparations/${pointer.session_id}/events`&&url.pathname!==`/api/v1/preparations/${pointer.session_id}/snapshot`)return fail('session_not_found',404);
      const generation=Number(query.get(url.pathname.endsWith('/events')?'generation':'expected_generation')),key=query.get(url.pathname.endsWith('/events')?'request_key':'expected_request_key');
      if(generation!==pointer.generation||key!==pointer.request_key)return fail('generation_conflict',409,pointer,'restart-current-reads');
      if(url.pathname.endsWith('/events')){
        metrics.events++;const after=Number(query.get('after')),limit=Number(query.get('limit'));
        if(!Number.isSafeInteger(after)||after<0||after>pointer.snapshot_sequence||!Number.isSafeInteger(limit)||limit<1||limit>64)return fail('invalid_cursor',400);
        pointer.events=pointer.events.filter(e=>e.cursor>after).slice(0,limit);pointer.cursor=pointer.events.at(-1)?.cursor??after;return Response.json(pointer);
      }
      metrics.pages++;
      if(Number(query.get('expected_snapshot_sequence'))!==pointer.snapshot_sequence||Number(query.get('expected_catalog_revision'))!==revision||query.get('expected_catalog_release_key')!==release)return fail('snapshot_changed',409,pointer,'restart-current-reads');
      const offset=Number(query.get('offset')),limit=Number(query.get('limit')),all=read.pages.flatMap(p=>p.courses),page=clone(read.pages[0]);
      Object.assign(page,{offset,limit,courses:clone(all.slice(offset,offset+limit)),has_more:offset+limit<all.length});return Response.json(page);
    },
  };return adapter;
}
export async function loadProtocolAdapter(options={}) {
  const response=await fetch(new URL('./protocol.json',import.meta.url));if(!response.ok)throw new Error('Protocol fixture unavailable');const text=await response.text();
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));if([...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('')!==PROTOCOL_SHA)throw new Error('Changed frozen protocol fixture');
  return createProtocolAdapter(JSON.parse(text),options);
}
