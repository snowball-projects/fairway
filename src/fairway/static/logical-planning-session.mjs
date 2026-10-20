import {canonicalRequest,preparationCards} from './preparation-dto.mjs';
import {LogicalError,validateInput} from './logical-transport.mjs';
// Display/controller lifecycle for one pinned fake protocol adapter only.
// A POST changes input within the same logical ownership. It is never a
// browser dispatch, trusted retry, cancel or budget reset.
export class LogicalPlanningSession {
  constructor({transport,notify=()=>{},sleep=ms=>new Promise(r=>setTimeout(r,ms))}) {
    if(transport?.protocol!=='immutable-plan-07a6806'||transport.offlineOnly!==true)throw new Error('Pinned offline logical transport required');
    this.transport=transport;this.adapter=transport.adapter;this.notify=notify;this.sleep=sleep;this.origins=[];this.objective='maximum';this.holes=[9,18];this.radiusKilometers=32.18688;this.accessPolicy='nonmember';
    this.epoch=0;this.origins=[];this.cards=[];this.areas=[];this.phase='entry';this.error=null;this.blocked=false;this.limited=false;this.areaSearchComplete=null;this.active=null;this.pending=null;this.posting=false;this.polling=false;this.key=null;this.displayEnabled=false;this.owned=false;this.logicalStopped=false;this.lastView=null;this.operationActive=false;this.upstreamStarted=null;this.logicalBudget=null;
  }
  get hasAdmitted(){return this.transport.identity!==null;}
  courseCards(){return this.cards;}
  invalidate(origins=this.origins) {this.epoch++;this.origins=structuredClone(origins);this.displayEnabled=false;this.pending=null;this.key=null;this.cards=[];this.areas=[];this.limited=false;this.areaSearchComplete=null;this.phase=this.blocked?'error':'entry';if(!this.blocked)this.error=null;this.notify(this);}
  update(origins,objective=this.objective,holes=this.holes) {
    if(!Array.isArray(holes)||!holes.length||holes.length>2||new Set(holes).size!==holes.length||holes.some(h=>![9,18].includes(h)))throw new LogicalError('invalid_input');
    const request={origins:structuredClone(origins),objective,radius_km:this.radiusKilometers,access_policy:this.accessPolicy,round_holes:holes.length===1?holes[0]:null};
    const same=this.transport.current&&canonicalRequest(this.transport.current.request)===canonicalRequest(request),generation=same?this.transport.current.generation:(this.transport.current?.generation??0)+1;
    validateInput(request,generation);const key=canonicalRequest(request);if(this.displayEnabled&&this.key===key)return false;
    this.invalidate(origins);this.key=key;this.objective=objective;this.holes=[...holes];this.displayEnabled=true;
    if(this.blocked)return false;if(!origins.length&&!this.hasAdmitted&&!this.posting)return false;
    this.pending={request,generation,epoch:this.epoch};this.phase=origins.length>1?'area':origins.length?'matrix':'clearing';this.notify(this);this.drainPosts();return true;
  }
  radiusChanged(radius){validateInput({origins:this.origins,objective:this.objective,radius_km:radius,access_policy:this.accessPolicy,round_holes:this.holes.length===1?this.holes[0]:null},1);this.radiusKilometers=radius;return this.update(this.origins);}
  accessChanged(policy){validateInput({origins:this.origins,objective:this.objective,radius_km:this.radiusKilometers,access_policy:policy,round_holes:this.holes.length===1?this.holes[0]:null},1);this.accessPolicy=policy;return this.update(this.origins);}
  revoke(){this.cards=this.cards.map(c=>({...c,maximum_seconds:null,combined_seconds:null,travel_times_seconds:c.travel_times_seconds.map(()=>null),travel_time_reasons:c.travel_times_seconds.map(()=>'error'),reason:'error',status:'error'}));}
  fail(error){this.error={code:error.code||'unknown_plan_failure',retryable:false};this.blocked=error.neverStarted!==true;if(this.blocked){this.logicalStopped=false;if(this.owned)this.active={logical:true};}this.pending=null;this.phase='error';this.revoke();this.notify(this);}
  async drainPosts() {
    if(this.posting||!this.pending||this.blocked)return;this.posting=true;
    while(this.pending&&!this.blocked){const job=this.pending;this.pending=null;
      try {const same=this.transport.current&&canonicalRequest(this.transport.current.request)===canonicalRequest(job.request);job.generation=same?this.transport.current.generation:(this.transport.current?.generation??0)+1;await this.transport.update(job.request,job.generation);this.owned=true;this.logicalStopped=false;this.active={logical:true};
        if(job.epoch===this.epoch&&!this.blocked){this.error=null;this.key=canonicalRequest(job.request);}this.startPolling();
      }catch(error){if(job.epoch===this.epoch||error.neverStarted!==true)this.fail(error);}
    }
    this.posting=false;this.notify(this);
  }
  receive(view) {
    this.lastView=view;this.operationActive=view.operationActive;this.upstreamStarted=view.upstreamStarted;this.logicalBudget=view.logicalBudget;
    this.logicalStopped=Boolean(view.logicalStopped);this.active=this.logicalStopped?null:{logical:true};
    if(!this.displayEnabled||this.pending||canonicalRequest(view.request)!==this.key)return;
    this.cards=preparationCards({rows:()=>view.rows});this.areas=view.areas;this.limited=view.preparationLimited;this.areaSearchComplete=view.areaSearchComplete;
    this.error=null;this.phase=view.logicalStopped?.status==='cleared'?'cleared':!view.request.origins.length?'clearing':this.limited?'partial':view.summary.ranking_complete?'complete':this.origins.length>1&&!view.areas.length?'area':'matrix';this.notify(this);
  }
  async startPolling() {
    if(this.polling||this.blocked)return;this.polling=true;
    try {
      do {const result=await this.transport.read(view=>this.receive(view));if(this.blocked)break;
        if(result.stale){await this.sleep(250);continue;}
        if(result.logicalStopped&&!this.pending&&!this.posting)break;
        await this.sleep(250);
      }while(!this.blocked);
    }catch(error){this.fail(error);}finally{this.polling=false;this.notify(this);}
  }
}
