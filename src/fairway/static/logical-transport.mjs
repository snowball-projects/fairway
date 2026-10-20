import {CatalogRead} from './catalog-read.mjs';
import {PreparationPages,canonicalRequest} from './preparation-dto.mjs';
export const PROTOCOL_SHA='2e9bbbc646bea399935538b9ebbbb634486be5e90e6508b983027a5ff234cca3';
const ownershipErrors=new Set(['upstream_outcome_unknown','work_completion_unconfirmed','deadline','worker_unavailable','durability_unconfirmed','transport_outcome_unknown']);
const ROOT='/api/v1',MAX_BYTES=4*1024*1024;
const integer=(v,min=0,max=Number.MAX_SAFE_INTEGER)=>Number.isSafeInteger(v)&&v>=min&&v<=max;
const locator=v=>typeof v==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(v);
const fields=['origins','objective','radius_km','access_policy','round_holes'];
export class LogicalError extends Error {constructor(code,details={}){super(code);this.code=code;this.retryable=false;Object.assign(this,details);}}
export function validateInput(request,generation) {
  if(!request||!integer(generation,1,2147483647)||canonicalRequest(Object.keys(request).sort())!==canonicalRequest([...fields].sort())||
    !Array.isArray(request.origins)||request.origins.length>8||request.origins.some(o=>!o||canonicalRequest(Object.keys(o).sort())!==canonicalRequest(['coordinate','id'])||typeof o.id!=='string'||!o.id||o.id.length>128||!Array.isArray(o.coordinate)||o.coordinate.length!==2||!o.coordinate.every(Number.isFinite)||o.coordinate[0]<24||o.coordinate[0]>50||o.coordinate[1]<-125||o.coordinate[1]>-66)||
    new Set(request.origins.map(o=>o.id)).size!==request.origins.length||!['maximum','combined'].includes(request.objective)||!Number.isFinite(request.radius_km)||request.radius_km<=0||request.radius_km>160||![null,9,18].includes(request.round_holes)||!['nonmember','all','public','private','restricted','unknown'].includes(request.access_policy)||new TextEncoder().encode(JSON.stringify({...request,generation})).length>4096)throw new LogicalError('invalid_preparation_request',{neverStarted:true});
}
const bindingFields=['session_id','generation','request_key','catalog_revision','catalog_release_key'];
function checkPointer(value,expected=null) {
  if(!value||!locator(value.session_id)||!integer(value.generation,1,2147483647)||typeof value.request_key!=='string'||! /^[a-f0-9]{64}$/.test(value.request_key)||!integer(value.catalog_revision)||!locator(value.catalog_release_key)||!integer(value.snapshot_sequence)||!integer(value.cursor)||value.operation_started!==true||typeof value.operation_active!=='boolean'||(value.operation_active&&value.upstream_started!==null)||![false,true,null].includes(value.upstream_started)||![true,null].includes(value.engine_unknown))throw new LogicalError('invalid_plan_binding',{unknown:true});
  if(expected&&bindingFields.some(k=>value[k]!==expected[k]))throw new LogicalError('changed_plan_binding',{unknown:true});
}
function budget(value) {
  if(!value||value.request_limit!==32||value.cell_limit!==4096||value.target_limit!==256||value.deadline_milliseconds!==30000||!integer(value.provider_requests,0,32)||!integer(value.matrix_cells,0,4096)||!integer(value.distinct_historical_targets,0,256)||!integer(value.remaining_milliseconds_at_snapshot,0,30000))throw new LogicalError('invalid_logical_budget',{unknown:true});
  return structuredClone(value);
}
export class LogicalPages {
  constructor(context) {this.context=context;this.base=new PreparationPages(context.generation,context.request,context.request_key);this.metadata=null;this.inspectionReceipt=null;}
  accept(page) {
    if(page.catalog_release_key!==this.context.catalog_release_key||page.catalog_revision!==this.context.catalog_revision||page.snapshot_sequence!==this.context.snapshot_sequence)throw new LogicalError('changed_snapshot_binding',{unknown:true});
    const b=budget(page.logical_budget);
    if(typeof page.preparation_limited!=='boolean'||typeof page.area_search_complete!=='boolean'||typeof page.operation_active!=='boolean'||(page.operation_active?!integer(page.active_work_id,1):page.active_work_id!==null)||page.total>4096||(page.ranking_complete&&(page.preparation_limited||!page.area_search_complete||page.operation_active))||
      (page.terminal!==null&&(!page.terminal||page.terminal.native_admission_released!==false)))throw new LogicalError('invalid_plan_snapshot',{unknown:true});
    const meta={logical_budget:b,preparation_limited:page.preparation_limited,area_search_complete:page.area_search_complete,operation_active:page.operation_active,active_work_id:page.active_work_id,provider_policy_key:page.provider_policy_key,routing_metadata:page.routing_metadata,qualification:page.qualification,terminal:page.terminal};
    if(this.metadata&&canonicalRequest(this.metadata)!==canonicalRequest(meta))throw new LogicalError('mixed_logical_snapshot',{unknown:true});
    if(!this.base.accept(page))throw new LogicalError('changed_snapshot_generation',{unknown:true});
    this.metadata=structuredClone(meta);return true;
  }
  get completeRead(){return this.base.completeRead;}
  get summary(){return this.base.summary;}
  get snapshotSequence(){return this.base.snapshotSequence;}
  rows(){return this.base.rows();}
  get areas(){return this.base.areas;}
  get preparationLimited(){return this.metadata.preparation_limited;}
  get areaSearchComplete(){return this.metadata.area_search_complete;}
  get operationActive(){return this.metadata.operation_active;}
  get logicalBudget(){return structuredClone(this.metadata.logical_budget);}
  // This raw source chunk receipt is inspect-only and never establishes stop,
  // native proof or admission release. It is not sent to the UI observer.
  inspectWorkReceipt(){return structuredClone(this.metadata.terminal);}
}
export class LogicalTransport {
  constructor({adapter,authorization}) {
    if(adapter?.fixtureOnly!==true||adapter.protocolSha!==PROTOCOL_SHA||typeof adapter.fetcher!=='function'||typeof adapter.attestLogicalStop!=='function'||typeof adapter.requestKeyFor!=='function'||typeof adapter.attestAdmission!=='function')throw new Error('Pinned fake-only logical adapter required; real binding unavailable');
    if(authorization?.allowed!==true||!authorization.caller)throw new LogicalError('unauthorized',{neverStarted:true});
    this.adapter=adapter;this.authorization=authorization;this.offlineOnly=true;this.protocol='immutable-plan-07a6806';this.identity=null;this.current=null;this.lastBudget=null;this.budgetSequence=-1;this.lastCursor=0;this.lastSequence=0;this.polls=0;this.snapshotReads=0;this.catalogReads=0;this.catalogBinding=null;this.postActive=false;this.postDesired=null;
  }
  async json(path,{method='GET',query={},body=null}={}) {
    if(!path.startsWith(ROOT+'/')||path.includes('..')||path.includes('://'))throw new LogicalError('invalid_reserved_path');
    let response;try{response=await this.adapter.fetcher(path+(Object.keys(query).length?'?'+new URLSearchParams(Object.entries(query).map(([k,v])=>[k,String(v)])):''),{method,body:body===null?undefined:JSON.stringify(body),authorization:this.authorization});}catch{throw new LogicalError('transport_outcome_unknown',{unknown:true,ownershipUnknown:true});}
    let text;try{text=await response.text();}catch{throw new LogicalError('transport_outcome_unknown',{unknown:true,ownershipUnknown:true});}
    if(new TextEncoder().encode(text).length>MAX_BYTES)throw new LogicalError('response_too_large',{unknown:true});
    let value;try{value=JSON.parse(text);}catch{throw new LogicalError('invalid_response',{unknown:true});}
    if(!response.ok)throw new LogicalError(typeof value.code==='string'?value.code:'request_failed',{status:response.status,unknown:value.engine_unknown===true||ownershipErrors.has(value.code),ownershipUnknown:value.engine_unknown===true||ownershipErrors.has(value.code),latest:value.latest,recovery:value.recovery,neverStarted:false});
    return value;
  }
  async catalogPages(kind,expected=null) {
    const rows=[],ids=new Set(),targets=new Map();let offset=0,pair=expected,total=null,qualification=null;
    while(this.catalogReads++<64) {
      const query={limit:1000,offset};if(pair){query.expected_revision=pair.revision;query.expected_release_key=pair.releaseKey;}
      const page=await this.json(`${ROOT}/catalog/${kind}`,{query}),list=page[kind];
      if(!integer(page.revision)||!locator(page.catalog_release_key)||(pair&&(page.revision!==pair.revision||page.catalog_release_key!==pair.releaseKey)))throw new LogicalError('catalog_release_changed',{unknown:true});
      pair={revision:page.revision,releaseKey:page.catalog_release_key};
      if(!integer(page.total)||!Array.isArray(list)||page.limit!==1000||page.offset!==offset||list.length!==Math.min(1000,Math.max(0,page.total-offset))||(total!==null&&total!==page.total)||page.has_more!==(offset+1000<page.total))throw new LogicalError('invalid_catalog_page');
      total=page.total;qualification??=page.qualification;
      if(page.qualification!==qualification)throw new LogicalError('changed_catalog_qualification');
      for(const row of list){const id=row[kind==='courses'?'course_id':'facility_id'];if(typeof id!=='string'||ids.has(id))throw new LogicalError('duplicate_catalog_identity');ids.add(id);rows.push(row);}
      if(page.destinations!==undefined&&!Array.isArray(page.destinations))throw new LogicalError('invalid_catalog_targets');
      for(const target of page.destinations||[]){if(!locator(target.id)||(targets.has(target.id)&&canonicalRequest(target)!==canonicalRequest(targets.get(target.id))))throw new LogicalError('changed_catalog_target');targets.set(target.id,target);}
      if(!page.has_more)return {...pair,rows,destinations:[...targets.values()],qualification};offset+=list.length;
    }
    throw new LogicalError('catalog_read_limit');
  }
  async readCatalog() {
    const facilities=await this.catalogPages('facilities'),courses=await this.catalogPages('courses',facilities);
    if(this.identity&&(courses.revision!==this.identity.catalog_revision||courses.releaseKey!==this.identity.catalog_release_key))throw new LogicalError('catalog_release_changed',{unknown:true});
    const view=new CatalogRead({revision:courses.revision,facilities:facilities.rows,courses:courses.rows,destinations:courses.destinations,qualification:facilities.qualification});
    view.catalogReleaseKey=courses.releaseKey;this.catalogBinding={catalog_revision:courses.revision,catalog_release_key:courses.releaseKey};return view;
  }
  async update(request,generation) {
    validateInput(request,generation);
    if(this.adapter.supportsInput?.(request,generation)===false)throw new LogicalError("fixture_request_unavailable",{neverStarted:true});
    if(this.postActive)throw new LogicalError('concurrent_input_post',{unknown:true});
    if(this.current&&generation===this.current.generation&&canonicalRequest(request)===canonicalRequest(this.current.request))return this.current;
    if(this.current&&generation<=this.current.generation)throw new LogicalError('generation_not_advanced',{neverStarted:true});
    this.postActive=true;
    try {
      const key=this.adapter.requestKeyFor(request,generation);this.postDesired={generation,request_key:key};const reply=await this.json(`${ROOT}/preparations`,{method:'POST',body:{...request,generation}});checkPointer(reply);
      if(reply.generation!==generation||reply.request_key!==key||this.adapter.attestAdmission(reply,request,generation)!==true||(this.identity&&['session_id','catalog_revision','catalog_release_key'].some(k=>reply[k]!==this.identity[k]))||(this.catalogBinding&&['catalog_revision','catalog_release_key'].some(k=>reply[k]!==this.catalogBinding[k]))||reply.snapshot_sequence<this.lastSequence||reply.cursor<this.lastCursor)throw new LogicalError('changed_plan_binding',{unknown:true});
      this.identity??=Object.fromEntries(['session_id','catalog_revision','catalog_release_key'].map(k=>[k,reply[k]]));
      this.current={...reply,request:structuredClone(request)};this.lastSequence=Math.max(this.lastSequence,reply.snapshot_sequence);return this.current;
    }finally{this.postActive=false;this.postDesired=null;}
  }
  ownUpdateConflict(error,context) {
    const p=error.latest;return this.postActive&&this.postDesired&&error.code==='generation_conflict'&&p&&p.generation===this.postDesired.generation&&p.request_key===this.postDesired.request_key&&['session_id','catalog_revision','catalog_release_key'].every(k=>p[k]===context[k]);
  }
  recover(error,context) {
    if(error.status!==409||error.recovery!=='restart-current-reads'||!['snapshot_changed','generation_conflict','cursor_expired'].includes(error.code))throw error;
    checkPointer(error.latest,context);
    if(error.latest.snapshot_sequence<context.snapshot_sequence||error.latest.cursor<this.lastCursor)throw new LogicalError('invalid_read_recovery',{unknown:true});
    return {...context,...error.latest,request:context.request};
  }
  async snapshot(context) {
    let binding=context;
    for(let retry=0;retry<3;retry++) {
      const view=new LogicalPages(binding);let offset=0,limit=25;
      try {
        for(let pages=0;pages<512;pages++) {
          if(this.snapshotReads++>=512)throw new LogicalError('snapshot_read_limit',{unknown:true});
          const page=await this.json(`${ROOT}/preparations/${binding.session_id}/snapshot`,{query:{expected_snapshot_sequence:binding.snapshot_sequence,expected_generation:binding.generation,expected_request_key:binding.request_key,expected_catalog_revision:binding.catalog_revision,expected_catalog_release_key:binding.catalog_release_key,limit,offset}});
          if(page.offset!==offset||page.limit!==limit)throw new LogicalError('invalid_snapshot_page');
          view.accept(page);
          if(!page.has_more){if(!view.completeRead)throw new LogicalError('preparation_read_incomplete',{unknown:true});return view;}
          if(!page.courses.length)throw new LogicalError('preparation_read_incomplete',{unknown:true});offset+=page.courses.length;
        }
      }catch(error){if(this.ownUpdateConflict(error,binding))throw new LogicalError('stale_read',{stale:true});if(retry===2)throw error;binding=this.recover(error,binding);}
    }
    throw new LogicalError('preparation_read_incomplete',{unknown:true});
  }
  validateStop(result,view) {
    if(result.terminal===null)return null;
    const stop=result.terminal;
    if(!stop||stop.scope!=='logical-plan'||stop.logical_operation_complete!==true||stop.native_admission_released!==false||!['complete','limited','cleared'].includes(stop.status)||result.operation_active||bindingFields.filter(k=>k!=='session_id').some(k=>stop[k]!==result[k])||stop.snapshot_sequence!==result.snapshot_sequence||stop.snapshot_sequence!==view.snapshotSequence||
      (stop.status==='complete'&&!view.summary.ranking_complete)||(stop.status==='limited'&&!view.preparationLimited)||(stop.status==='cleared'&&(view.summary.total!==0||view.context.request.origins.length!==0))||stop.last_work_receipt?.native_admission_released===true||this.adapter.attestLogicalStop(result)!==true)throw new LogicalError('logical_stop_unconfirmed',{unknown:true});
    // Only a fixture-witnessed polling stop. Raw native receipts are discarded.
    return {status:stop.status,scope:'logical-plan',logical_operation_complete:true,native_admission_released:false,fixture_only:true};
  }
  async read(onView=()=>{},readRestarts=0) {
    if(!this.current)throw new LogicalError('preparation_not_admitted');
    const current=this.current;let context={...current},result;
    for(let retry=0;retry<3;retry++) {
      try {
        if(this.polls++>=256)throw new LogicalError('event_read_limit',{unknown:true});
        result=await this.json(`${ROOT}/preparations/${context.session_id}/events`,{query:{generation:context.generation,request_key:context.request_key,after:this.lastCursor,limit:64}});checkPointer(result,current);
        if(result.snapshot_sequence<this.lastSequence||result.cursor<this.lastCursor||!Array.isArray(result.events)||result.events.length>64||result.poll_after_ms!==250||result.engine_unknown===true)throw new LogicalError('invalid_current_events',{unknown:true});
        let cursor=this.lastCursor;
        for(const event of result.events){if(event.type!=='planning.snapshot'||!integer(event.cursor)||event.cursor<=cursor||event.cursor>result.cursor||event.snapshot_sequence!==event.cursor||event.snapshot_sequence>result.snapshot_sequence||['generation','request_key','catalog_revision','catalog_release_key'].some(k=>event[k]!==current[k]))throw new LogicalError('mixed_event_generation',{unknown:true});cursor=event.cursor;}
        context={...context,...result};break;
      }catch(error){if(!error.ownershipUnknown&&(this.current!==current||this.ownUpdateConflict(error,current)))return {stale:true};if(retry===2)throw error;context=this.recover(error,context);this.lastCursor=context.cursor;}
    }
    let view;try {view=await this.snapshot(context);}catch(error){if(!error.ownershipUnknown&&(this.current!==current||error.stale))return {stale:true};throw error;}
    if(this.current!==current)return {stale:true};
    if(view.snapshotSequence!==result.snapshot_sequence){if(readRestarts<2)return this.read(onView,readRestarts+1);throw new LogicalError('event_snapshot_changed',{unknown:true});}
    const stopped=this.validateStop(result,view),b=view.logicalBudget;
    if(view.operationActive!==result.operation_active||view.summary.blocked||view.summary.error)throw new LogicalError('failed_plan_snapshot',{unknown:true});
    if(this.lastBudget&&view.snapshotSequence>=this.budgetSequence&&(['provider_requests','matrix_cells','distinct_historical_targets'].some(k=>b[k]<this.lastBudget[k])||b.remaining_milliseconds_at_snapshot>this.lastBudget.remaining_milliseconds_at_snapshot))throw new LogicalError('logical_budget_reset',{unknown:true});
    const display={generation:context.generation,request:structuredClone(current.request),requestKey:current.request_key,catalogRevision:current.catalog_revision,catalogReleaseKey:current.catalog_release_key,snapshotSequence:view.snapshotSequence,summary:structuredClone(view.summary),rows:view.rows(),areas:structuredClone(view.areas),operationActive:view.operationActive,upstreamStarted:result.upstream_started,logicalBudget:b,preparationLimited:view.preparationLimited,areaSearchComplete:view.areaSearchComplete,logicalStopped:stopped,workReceiptPresent:view.inspectWorkReceipt()!==null};
    this.lastCursor=result.cursor;this.lastSequence=view.snapshotSequence;this.lastBudget=b;this.budgetSequence=view.snapshotSequence;
    try {onView(display);}catch{throw new LogicalError('observer_failed',{unknown:true});}
    return display;
  }
}
