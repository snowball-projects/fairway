import {PreparationPages,preparationCards,canonicalRequest,preparationRequestKey} from './preparation-dto.mjs';
// Browser display lifecycle only. Server-owned selection, matrix batching,
// destination reuse, scoring and native admission are never implemented here.
export class PreparationSession {
  constructor({adapter,notify=()=>{}}) {
    if(adapter.fixtureOnly!==true || typeof adapter.replay!=='function')throw new Error('Validated fixture adapter required');
    this.adapter=adapter;this.notify=notify;this.origins=[];this.objective='maximum';this.holes=[9,18];
    this.radiusKilometers=32.18688;this.accessPolicy='nonmember';this.generation=0;this.active=null;this.pending=null;
    this.limited=false;this.areaSearchComplete=null;this.key=null;this.areas=[];this.cards=[];this.phase='entry';this.error=null;this.blocked=false;
  }
  invalidate(origins=this.origins) {
    this.generation++;this.origins=structuredClone(origins);this.pending=null;this.key=null;this.cards=[];this.areas=[];this.limited=false;this.areaSearchComplete=null;
    this.phase=this.blocked?'error':'entry';if(!this.blocked)this.error=null;this.notify(this);
  }
  update(origins,objective=this.objective,holes=this.holes) {
    if(origins.length>8 || new Set(origins.map(o=>o.id)).size!==origins.length || origins.some(o=>!o.id || !Array.isArray(o.coordinate) || o.coordinate.length!==2 || !o.coordinate.every(Number.isFinite) || Math.abs(o.coordinate[0])>90 || Math.abs(o.coordinate[1])>180) ||
      !['maximum','combined'].includes(objective) || !holes.length || holes.some(h=>![9,18].includes(h)))throw new Error('Invalid committed planning input');
    const request={origins:structuredClone(origins),objective,radius_km:this.radiusKilometers,access_policy:this.accessPolicy,round_holes:holes.length===1?holes[0]:null};
    const key=canonicalRequest(request);if(key===this.key)return false;
    this.invalidate(origins);this.key=key;this.objective=objective;this.holes=[...holes];
    if(!origins.length || this.blocked)return false;
    this.phase=origins.length>1?'area':'matrix';this.pending={generation:this.generation,request,key,sequence:0,snapshotSequence:0,backendGeneration:null,fixtureTerminal:false,collection:null};
    this.notify(this);this.drain();return true;
  }
  radiusChanged(radius) {if(!Number.isFinite(radius)||radius<=0||radius>160)throw new Error('Invalid radius');this.radiusKilometers=radius;return this.update(this.origins);}
  accessChanged(policy) {if(!['nonmember','all','public','private','restricted','unknown'].includes(policy))throw new Error('Invalid access policy');this.accessPolicy=policy;return this.update(this.origins);}
  courseCards() {return this.cards;}
  revokeScores() {
    this.cards=this.cards.map(card=>({...card,maximum_seconds:null,combined_seconds:null,
      travel_times_seconds:card.travel_times_seconds.map(()=>null),travel_time_reasons:card.travel_times_seconds.map(()=>"error"),reason:"error",status:"error"}));
  }
  receive(job,frame) {
    if(this.active!==job || job.generation!==this.generation)return;
    if(frame.request_key!==job.requestKey || canonicalRequest(frame.request)!==job.key || !Number.isSafeInteger(frame.sequence) || frame.sequence<=job.sequence ||
      !Number.isSafeInteger(frame.snapshot_sequence) || frame.snapshot_sequence<job.snapshotSequence ||
      (job.backendGeneration!==null && frame.generation!==job.backendGeneration))throw new Error('Invalid fixture frame binding');
    job.sequence=frame.sequence;job.snapshotSequence=frame.snapshot_sequence;job.backendGeneration=frame.generation;
    if(frame.type==='planning.snapshot') {
      const snapshot=frame.snapshot;
      if(snapshot.snapshot_sequence!==frame.snapshot_sequence || snapshot.generation!==frame.generation || snapshot.catalog_revision!==frame.catalog_revision)throw new Error('Snapshot envelope mismatch');
      if(!job.collection || job.collection.snapshotSequence!==snapshot.snapshot_sequence)job.collection=new PreparationPages(frame.generation,job.request,job.requestKey);
      job.collection.accept(snapshot);
      // Never replace a complete pool with an isolated first page.
      if(job.collection.completeRead) {
        this.cards=preparationCards(job.collection);this.areas=snapshot.areas;
        this.limited=snapshot.preparation_limited===true;this.areaSearchComplete=snapshot.area_search_complete??null;
        this.blocked=snapshot.blocked;this.error=snapshot.error?{code:snapshot.error,retryable:false}:null;
        if(this.error||this.blocked)this.revokeScores();
        this.phase=this.error?'error':snapshot.ranking_complete?'complete':this.origins.length>1&&!this.areas.length?'area':'matrix';
        this.notify(this);
      }
    } else if(frame.type==='area.ready') {
      if(!Array.isArray(frame.areas) || frame.areas.some(area=>area.geometry?.type!=='Point' || !area.qualification || area.geometry.coordinates[0]!==area.center[1] || area.geometry.coordinates[1]!==area.center[0]))throw new Error('Invalid qualified fixture area');
      this.areas=structuredClone(frame.areas);this.phase='matrix';this.notify(this);
    } else if(frame.type==='operation.terminal') {
      if(frame.fixture_complete!==true || frame.evidence?.basis!=='literal-fixture-completion' || frame.evidence.native_admission_released!==false)throw new Error('Invalid fixture-only terminal evidence');
      job.fixtureTerminal=true;
    } else if(frame.type==='preparation.limited') {
      if(frame.preparation_limited!==true || typeof frame.area_search_complete!=='boolean')throw new Error('Invalid limited fixture status');
      this.limited=true;this.areaSearchComplete=frame.area_search_complete;this.phase='partial';this.notify(this);
    } else if(frame.type==='preparation.error') {
      this.error={code:frame.code,retryable:false};this.blocked=frame.code==='upstream_outcome_unknown';this.revokeScores();this.phase='error';this.notify(this);
    }
  }
  async drain() {
    if(this.active || !this.pending || this.blocked)return;
    const job=this.pending;this.pending=null;this.active=job;
    let outcome;
    try {job.requestKey=await preparationRequestKey(job.request);outcome=await this.adapter.replay(job.request,frame=>this.receive(job,frame));}
    catch(error) {outcome=error.neverStarted===true?{neverStarted:true,error:error.code}:{fixture_complete:false};}
    const completed=outcome?.fixture_complete===true && outcome.evidence?.basis==='literal-fixture-completion' && outcome.evidence.native_admission_released===false;
    if(!completed && outcome?.neverStarted!==true) {
      this.blocked=true;this.pending=null;this.error={code:'upstream_outcome_unknown',retryable:false};this.phase='error';
      this.revokeScores();
    } else if(job.generation===this.generation) {
      if(outcome.neverStarted)this.error={code:outcome.error,retryable:false};
      else if (!job.collection?.completeRead) {
        this.error={code:'preparation_read_incomplete',retryable:false};
        this.revokeScores();
      }
      if(this.error)this.phase='error';else if(this.phase!=='complete')this.phase='partial';
    }
    // This is a local fixture slot. It confers no native admission release.
    if(completed || outcome?.neverStarted===true)this.active=null;
    this.notify(this);this.drain();
  }
}
