import {PrivateTransport} from '../../src/fairway/static/private-transport.mjs';
// Pinned native read examples only. This assembled demonstration window is not
// a national catalog snapshot or an editable authority. No HTTP API exists.
export function createNativeCatalogAdapter({facilityExamples,courseExample}) {
  const revision=courseExample.revision;
  if(facilityExamples.some(p=>p.revision!==revision))throw new Error('Mixed example revisions');
  const facilities=facilityExamples.flatMap(p=>p.facilities),courses=courseExample.courses;
  const metrics={reads:0,posts:0};
  const authorization={allowed:true,caller:'offline-reviewer'};
  const fetcher=async(path,options)=>{
    const url=new URL(path,'https://reserved.invalid');
    if(options.authorization?.caller!==authorization.caller||!options.authorization?.allowed)return Response.json({code:'unauthorized'},{status:401});
    if(options.method!=='GET'){metrics.posts++;return Response.json({code:'unimplemented_offline_route',operation_started:false},{status:404});}
    metrics.reads++;
    const kind=url.pathname.split('/').at(-1),rows=kind==='facilities'?facilities:kind==='courses'?courses:null;
    if(!rows)return Response.json({code:'unimplemented_offline_route'},{status:404});
    if(url.searchParams.has('expected_revision')&&Number(url.searchParams.get('expected_revision'))!==revision)return Response.json({code:'catalog_revision_changed'},{status:409});
    const offset=Number(url.searchParams.get('offset')),limit=Number(url.searchParams.get('limit'));
    return Response.json({revision,[kind]:rows.slice(offset,offset+limit),destinations:kind==='courses'?courseExample.destinations:[],
      offset,limit,total:rows.length,has_more:offset+limit<rows.length,
      qualification:'Pinned read-only Corica and Cog Hill examples; selected demonstration window, not national coverage.'});
  };
  return {transport:new PrivateTransport({mode:'offline-deterministic',fetcher,authorization}),metrics};
}
export async function loadNativeCatalogAdapter() {
  const base=new URL('./catalog-native/',import.meta.url);
  const names=['facility-corica-example.json','facility-empty-cog-hill-example.json','course-corica-research21-example.json'];
  const examples=await Promise.all(names.map(async name=>{const response=await fetch(new URL(name,base));if(!response.ok)throw new Error('Native example unavailable');return response.json();}));
  return createNativeCatalogAdapter({facilityExamples:examples.slice(0,2),courseExample:examples[2]});
}
