import {CatalogRead} from './catalog-read.mjs';
import {PreparationPages,canonicalRequest,preparationRequestKey} from './preparation-dto.mjs';
const ROOT='/api/v1',MAX_PAGES=64,MAX_POLLS=256,MAX_BYTES=4*1024*1024;
const requestFields=new Set(['origins','objective','radius_km','access_policy','round_holes']);
export class TransportError extends Error {
  constructor(code,details={}){super(code);this.code=code;Object.assign(this,details);}
}
export class PrivateTransport {
  constructor({fetcher,mode,authorization,sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))}) {
    if(mode!=='offline-deterministic' || typeof fetcher!=='function')throw new Error('Real private transport binding is not reviewed');
    if(!authorization?.allowed || !authorization.caller)throw new TransportError('unauthorized');
    this.fetcher=fetcher;this.authorization=authorization;this.sleep=sleep;this.offlineOnly=true;
  }
  async json(path,{method='GET',query={},body=null}={}) {
    if(!path.startsWith(ROOT+'/') || path.includes('..') || path.includes('://'))throw new Error('Invalid reserved API path');
    const url=path+(Object.keys(query).length?'?'+new URLSearchParams(Object.entries(query).map(([k,v])=>[k,String(v)])):'');
    let response;
    try {response=await this.fetcher(url,{method,body:body===null?undefined:JSON.stringify(body),headers:{'Content-Type':'application/json'},credentials:'same-origin',authorization:this.authorization});}
    catch {throw new TransportError('transport_outcome_unknown',{unknown:true});}
    const text=await response.text();if(new TextEncoder().encode(text).length>MAX_BYTES)throw new TransportError('response_too_large',{unknown:method==='POST'});
    let value;try{value=JSON.parse(text);}catch{throw new TransportError('invalid_response',{unknown:true});}
    if(!response.ok) {
      const code=typeof value.code==='string'?value.code:'request_failed',unknown=value.engine_unknown===true || ['upstream_outcome_unknown','deadline','worker_unavailable','durability_unconfirmed','transport_outcome_unknown'].includes(code);
      const retryAfter=Number(response.headers.get('Retry-After'));
      const safeRetry=!unknown && value.engine_unknown===false && ['busy','rate_limited'].includes(code) && [429,503].includes(response.status) && value.operation_started===false && value.retryable===true && Number.isSafeInteger(retryAfter) && retryAfter>=10 && retryAfter<=600;
      throw new TransportError(code,{status:response.status,unknown,neverStarted:value.operation_started===false&&value.engine_unknown===false&&!unknown,retryable:safeRetry,retryAfter:safeRetry?retryAfter:null,latest:value.latest});
    }
    return value;
  }
  async pages(kind,revision=null) {
    const rows=[],destinations=new Map(),ids=new Set();let offset=0,expected=revision,total=null;
    for(let count=0;count<MAX_PAGES;count++) {
      const query={limit:1000,offset};if(expected!==null)query.expected_revision=expected;
      const page=await this.json(`${ROOT}/catalog/${kind}`,{query}),list=page[kind];
      if(!Number.isSafeInteger(page.revision)||page.revision<0 || (expected!==null&&page.revision!==expected))throw new TransportError('catalog_revision_changed',{status:409});
      expected=page.revision;
      if(!Array.isArray(list)||list.length>1000||page.offset!==offset || page.limit!==1000 || !Number.isSafeInteger(page.total)||page.total<0 ||
        (total!==null&&page.total!==total) || typeof page.has_more!=='boolean' || page.has_more!==(offset+page.limit<page.total) || list.length!==Math.min(page.limit,Math.max(0,page.total-offset)))throw new TransportError('invalid_catalog_page');
      total=page.total;
      for(const row of list){const id=row[kind==='courses'?'course_id':'facility_id'];if(!id||ids.has(id))throw new TransportError('duplicate_catalog_identity');ids.add(id);rows.push(row);}
      for(const target of page.destinations||[]) {
        if(destinations.has(target.id)&&canonicalRequest(destinations.get(target.id))!==canonicalRequest(target))throw new TransportError('changed_catalog_destination');destinations.set(target.id,target);
      }
      if(!page.has_more){if(rows.length!==total)throw new TransportError('incomplete_catalog_read');return {revision:expected,rows,destinations:[...destinations.values()],qualification:page.qualification};}
      if(!list.length)throw new TransportError('incomplete_catalog_read');offset+=list.length;
    }
    throw new TransportError('catalog_read_limit');
  }
  async readCatalog() {
    for(let attempt=0;attempt<3;attempt++)try {
      const facilities=await this.pages('facilities'),courses=await this.pages('courses',facilities.revision);
      return new CatalogRead({revision:facilities.revision,facilities:facilities.rows,courses:courses.rows,destinations:courses.destinations,qualification:facilities.qualification});
    }catch(error){if(error.code!=='catalog_revision_changed'||attempt===2)throw error;}
  }
  async snapshot(session,context) {
    if(!Number.isSafeInteger(context.snapshot_sequence)||context.snapshot_sequence<0)throw new TransportError("invalid_snapshot_binding",{unknown:true});
    let binding={...context};
    for(let retry=0;retry<3;retry++) {
      const view=new PreparationPages(binding.generation,binding.request,binding.request_key);let offset=0,operationStatus=null;
      try {
        for(let count=0;count<MAX_PAGES;count++) {
          const page=await this.json(`${ROOT}/preparations/${session}/snapshot`,{query:{expected_snapshot_sequence:binding.snapshot_sequence,expected_catalog_revision:binding.catalog_revision,
            expected_generation:binding.generation,expected_request_key:binding.request_key,limit:1000,offset}});
          if(page.catalog_revision!==binding.catalog_revision||page.snapshot_sequence!==binding.snapshot_sequence)throw new TransportError('snapshot_changed',{status:409});
          const status={limited:page.preparation_limited,areaComplete:page.area_search_complete};
          if(typeof status.limited!=='boolean'||typeof status.areaComplete!=='boolean'||(page.ranking_complete&&(status.limited||!status.areaComplete)) ||
              (operationStatus&&canonicalRequest(operationStatus)!==canonicalRequest(status)))throw new TransportError('invalid_operation_status');
          if(!view.accept(page))throw new TransportError('snapshot_generation_changed');
          operationStatus=status;view.preparationLimited=status.limited;view.areaSearchComplete=status.areaComplete;
          if(!page.has_more){if(!view.completeRead)throw new TransportError('preparation_read_incomplete');return view;}
          if(!page.courses.length)throw new TransportError('preparation_read_incomplete');offset+=page.courses.length;
        }
        throw new TransportError('preparation_read_limit');
      }catch(error){
        if(error.code!=='snapshot_changed'||retry===2)throw error;
        if(!error.latest || error.latest.generation!==context.generation || error.latest.request_key!==context.request_key || error.latest.catalog_revision!==context.catalog_revision || !Number.isSafeInteger(error.latest.snapshot_sequence)||error.latest.snapshot_sequence<0||error.latest.snapshot_sequence<binding.snapshot_sequence)throw new TransportError('invalid_snapshot_restart',{unknown:true});
        binding={...binding,snapshot_sequence:error.latest.snapshot_sequence};
      }
    }
  }
  async prepare(request,generation,onRead) {
    if(!request || !Number.isSafeInteger(generation)||generation<0 || Object.keys(request).length!==requestFields.size || Object.keys(request).some(k=>!requestFields.has(k)) ||
      !Array.isArray(request.origins)||request.origins.length<1||request.origins.length>8||new Set(request.origins.map(o=>o.id)).size!==request.origins.length||
      request.origins.some(o=>!o || Object.keys(o).length!==2||typeof o.id!=='string'||!o.id||o.id.length>128||!Array.isArray(o.coordinate)||o.coordinate.length!==2||!o.coordinate.every(Number.isFinite)||o.coordinate[0]<24||o.coordinate[0]>50||o.coordinate[1]<-125||o.coordinate[1]>-66)||
      !['maximum','combined'].includes(request.objective)||!Number.isFinite(request.radius_km)||request.radius_km<=0||request.radius_km>160||
      !['nonmember','all','public','private','restricted','unknown'].includes(request.access_policy)||![null,9,18].includes(request.round_holes)|| new TextEncoder().encode(JSON.stringify({...request,generation})).length>4096)throw new TransportError('invalid_preparation_request',{neverStarted:true});
    const key=await preparationRequestKey(request),created=await this.json(`${ROOT}/preparations`,{method:'POST',body:{...request,generation}});
    if(!/^[A-Za-z0-9_-]{16,128}$/.test(created.session_id)||created.generation!==generation||created.request_key!==key||!Number.isSafeInteger(created.catalog_revision)||created.catalog_revision<0||!Number.isSafeInteger(created.cursor)||created.cursor<0||created.operation_started!==true)throw new TransportError('invalid_session_binding',{unknown:true});
    const session=created.session_id,context={generation,request,request_key:key,catalog_revision:created.catalog_revision};let cursor=created.cursor,snapshotSequence=-1;
    for(let poll=0;poll<MAX_POLLS;poll++) {
      let result;
      try {result=await this.json(`${ROOT}/preparations/${session}/events`,{query:{after:cursor}});}
      catch(error){if(error.code!=='cursor_expired'||!error.latest)throw error;result=error.latest;}
      if(result.session_id!==session||result.generation!==generation||result.request_key!==key||result.catalog_revision!==context.catalog_revision||!Number.isSafeInteger(result.cursor)||result.cursor<cursor||!Number.isSafeInteger(result.snapshot_sequence)||result.snapshot_sequence<0||result.snapshot_sequence<snapshotSequence||!Array.isArray(result.events)||result.events.length>256)throw new TransportError('invalid_progress_binding',{unknown:true});
      let previous=cursor;
      for(const event of result.events){if(!Number.isSafeInteger(event.cursor)||event.cursor<=previous||event.cursor>result.cursor||event.generation!==generation||event.request_key!==key||event.catalog_revision!==context.catalog_revision)throw new TransportError('invalid_progress_cursor',{unknown:true});previous=event.cursor;}
      cursor=result.cursor;
      const completed=Boolean(result.terminal);
      if(completed) {
        const terminal=result.terminal;
        if(terminal.fairway_reservation_cleared!==true||terminal.native_admission_released!==false||terminal.evidence?.basis!=='offline-fake-clear')throw new TransportError('terminal_clear_unconfirmed',{unknown:true});
      } else if(!Number.isSafeInteger(result.poll_after_ms)||result.poll_after_ms<250||result.poll_after_ms>15000)throw new TransportError('invalid_poll_bound',{unknown:true});
      const view=await this.snapshot(session,{...context,snapshot_sequence:result.snapshot_sequence});
      snapshotSequence=Math.max(result.snapshot_sequence,view.snapshotSequence);
      if(typeof view.preparationLimited!=='boolean'||typeof view.areaSearchComplete!=='boolean')throw new TransportError('missing_operation_status',{unknown:true});
      try {onRead(view,result);}catch {throw new TransportError('observer_failed',{unknown:true});}
      if(completed)return {fairway_reservation_cleared:true,native_admission_released:false,offline_only:true};
      await this.sleep(result.poll_after_ms);
    }
    throw new TransportError('progress_read_limit',{unknown:true});
  }
}
