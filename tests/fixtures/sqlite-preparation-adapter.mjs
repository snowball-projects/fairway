import fixture from './sqlite-preparation-sequence.json' with {type:'json'};
import {canonicalRequest} from '../../src/fairway/static/preparation-dto.mjs';
// Replay exact API-owner DTO bytes. No locally invented course vectors,
// objective/radius substitutions, geocoder, router, database or provider bridge.
export function createPreparationFixtureAdapter({sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms)),largePool=false}={}) {
  const metrics={resolutions:0,operations:0,active:0,maxActive:0,cells:0,batches:0};
  const adapter={fixtureOnly:true,policy:{identity:'api-fixture-e8d66be',label:'synthetic SQLite preparation fixture'},metrics,
    async resolveOrigin(query) {
      metrics.resolutions++;await sleep(40);const origin=fixture.origin_labels.find(o=>o.label.toLowerCase()===query.trim().toLowerCase());
      return {features:origin?[{properties:{name:origin.label},geometry:{coordinates:[origin.coordinate[1],origin.coordinate[0]]}}]:[]};
    },
    offlineMap(L,map){adapter.map=map;},
    async replay(request,emit) {
      const step=fixture.steps.find(step=>canonicalRequest(step.request)===canonicalRequest(request));
      if(!step || (largePool && request.origins.length!==1)) {
        const error=new Error('No validated fixture for this request');error.code='fixture_request_unavailable';error.neverStarted=true;throw error;
      }
      metrics.operations++;metrics.active++;metrics.maxActive=Math.max(metrics.maxActive,metrics.active);
      try {
        for(const original of step.frames) {
          if(original.type==='matrix.batch') {await sleep(400);metrics.batches++;metrics.cells+=original.cells.length;}
          if(original.type==='area.ready')await sleep(800);
          if(!largePool)emit(structuredClone(original));
        }
        if(largePool) {
          let sequence=1;
          for(const snapshot of Object.values(fixture.large_pool)) {
            metrics.cells=snapshot.submitted_fixture_cells;metrics.batches=snapshot.fixture_attempts;
            emit({type:'planning.snapshot',provider:'deterministic-fixture',generation:snapshot.generation,sequence:sequence++,snapshot_sequence:snapshot.snapshot_sequence,
              catalog_revision:snapshot.catalog_revision,request:snapshot.request,request_key:snapshot.request_key,snapshot:structuredClone(snapshot)});
            await sleep(800);
          }
        }
        return {fixture_complete:true,evidence:{basis:'literal-fixture-completion',native_admission_released:false}};
      } finally {metrics.active--;}
    },
  };return adapter;
}
