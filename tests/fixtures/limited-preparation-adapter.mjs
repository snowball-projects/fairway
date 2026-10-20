import fixture from './sqlite-preparation-sequence.json' with {type:'json'};
import {canonicalRequest} from '../../src/fairway/static/preparation-dto.mjs';
import {createPreparationFixtureAdapter} from './sqlite-preparation-adapter.mjs';
// New test-only status seam over the frozen partial DTO. It is not an API-owner
// bridge output, a native terminal claim or an invented routing continuation.
export function createLimitedPreparationFixtureAdapter({fatal=false,sleep=ms=>new Promise(r=>setTimeout(r,ms))}={}) {
  const adapter=createPreparationFixtureAdapter({sleep}),source=fixture.large_pool.partial_24_scored;
  adapter.policy={identity:'offline-finite-limit-status-seam',label:'synthetic finite-limit fixture'};
  adapter.replay=async(request,emit)=>{
    if(canonicalRequest(request)!==canonicalRequest(source.request)){const error=new Error('Fixture scope mismatch');error.neverStarted=true;error.code='fixture_request_unavailable';throw error;}
    adapter.metrics.operations++;adapter.metrics.active++;adapter.metrics.maxActive=Math.max(adapter.metrics.maxActive,adapter.metrics.active);
    try {
      await sleep(400);
      const binding={generation:source.generation,request:source.request,request_key:source.request_key,catalog_revision:source.catalog_revision,snapshot_sequence:source.snapshot_sequence};
      emit({...binding,sequence:1,type:'planning.snapshot',snapshot:structuredClone(source)});
      emit({...binding,sequence:2,...(fatal?{type:'preparation.error',code:'provider_unavailable'}:{type:'preparation.limited',preparation_limited:true,area_search_complete:false})});
      return {fixture_complete:true,evidence:{basis:'literal-fixture-completion',native_admission_released:false}};
    }finally{adapter.metrics.active--;}
  };
  return adapter;
}
