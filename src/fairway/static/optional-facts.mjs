import {OPTIONAL_SCHEMA,OPTIONAL_DOMAINS,RELATIONSHIP_SCHEMA} from './optional-schema.mjs';
export {OPTIONAL_DOMAINS};
const SUBJECTS=['facility_id','course_id','component_id','round_id'];
const META=new Set(['id','observation_id',...SUBJECTS,'source_id','source_url','source_license','source_attribution','collected_on','observed_on','effective_from','effective_to','status','conflict','qualification']);
const LABELS={physical_characteristics:'Physical characteristics',amenity_observation:'Amenities',practice_observation:'Practice',service_observation:'Services',policy_observation:'Policies',operating_period:'Operating periods',accessibility_observation:'Accessibility',price_observation:'Dated price observations',architecture_event:'Design and architecture',quality_rating:'Quality ratings'};
const ENVELOPE=['source_id','source_url','source_license','source_attribution','collected_on','observed_on','effective_from','effective_to','status','conflict','qualification'];
const CREDIT={id:'text',party_id:'text',name:'text',party_kind:'text',role:'text'};
const fail=message=>{throw new Error(message);};
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
export function sameValue(a,b){
  if(a===b)return true;
  if(Array.isArray(a)&&Array.isArray(b))return a.length===b.length&&a.every((x,i)=>sameValue(x,b[i]));
  if(!object(a)||!object(b))return false;
  const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>Object.hasOwn(b,k)&&sameValue(a[k],b[k]));
}
function typed(value,type){
  if(value===null)return true;
  return type==='text'?typeof value==='string'&&!value.includes('\0'):type==='boolean'?typeof value==='boolean':type==='integer'?Number.isSafeInteger(value):type==='real'?typeof value==='number'&&Number.isFinite(value):false;
}
function rowShape(row,schema){
  if(!object(row)||Object.keys(row).length!==Object.keys(schema).length||Object.keys(schema).some(k=>!Object.hasOwn(row,k)))fail('Unknown or missing canonical column');
  for(const [key,type] of Object.entries(schema))if(type!=='credits'&&!typed(row[key],type))fail('Invalid canonical column type');
  if(typeof row.id!=='string'||!row.id)fail('Missing canonical row identity');
}
function unique(rows,key='id'){
  if(!Array.isArray(rows))fail('Expected canonical row array');
  const map=new Map();for(const row of rows){if(!object(row)||typeof row[key]!=='string'||!row[key]||map.has(row[key]))fail('Duplicate or missing canonical identity');map.set(row[key],row);}return map;
}
function rawMatches(record,raw,schema){return Object.keys(schema).every(key=>Object.hasOwn(record,key)&&sameValue(record[key],raw[key]));}
function assertIds(actual,expected){if(!Array.isArray(actual)||new Set(actual).size!==actual.length||actual.length!==expected.length||actual.some(id=>!expected.includes(id)))fail('Changed canonical relationship membership');}
// Shared explicit scan policy. Only the validation copy is normalized.
const SCAN_SPACE=/[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]/g;
function validationScan(text){return text.replace(SCAN_SPACE,' ').replace(/[A-Z]/g,letter=>letter.toLowerCase());}
const HTTP_TOKEN=/(^|[\x00-\x2f\x3a-\x40\x5b-\x5e\x60\x7b-\x7f“”‘’«»])(https?:\/\/[^ <>"'`“”‘’«»]+)/g;
const CREDENTIAL_URL_KEYS=new Set(["access_token", "access-token", "api_key", "api-key", "apikey", "authorization", "client_secret", "client-secret", "credential", "password", "passwd", "secret", "token"]);
function credentialSyntax(text){
 for(const view of [text,text.replace(/[\t\n\r]/g,'')]){
  const scan=validationScan(validationScan(view).replace(/%([0-9a-f]{2})/g,(whole,hex)=>{const c=String.fromCharCode(parseInt(hex,16));return /^[a-zA-Z0-9._~-]$/.test(c)?c:whole;}));
  if(/https?:[\/\\]*[^\/\\?#]*(?:@|%40)/.test(scan))return true;
  const keys=[...CREDENTIAL_URL_KEYS].join('|');
  if(new RegExp('(?:^|[^a-z0-9_])(?:'+keys+') *=').test(scan))return true;
 }
 return false;
}
// Public SQL roles and private serialization boundaries, never notation grammars.
const PRIVATE_KEYS=new Set(["access_token","api_key","authorization","capture_path","controls_reference","credential","fact_groups","local_path","password","payload","retained_document","retained_evidence","retained_pointer","secret"]);
for(const key of CREDENTIAL_URL_KEYS)PRIVATE_KEYS.add(key);
const PUBLIC_LICENSE_FIELDS=new Set(["applies_to","attribution","changes","collected_on","kind","license","license_url","policy_capture_sha256","policy_url","scope","source","source_id","source_url"]);
const PUBLIC_DOMAIN_TEXT={"accessibility_observation":["qualification"],"amenity_observation":["qualification"],"architecture_event":["event_kind","project_state","qualification","target_area"],"operating_period":["aerification_method","affected_area","maintenance_kind","period_kind","qualification"],"physical_characteristics":["elevation_unit","fairway_grass_name","greens_grass_name","landscape","playing_surface","qualification","rough_grass_name","tee_grass_name","terrain"],"policy_observation":["arrival_access_condition","audience","cancellation_charge_basis","cancellation_charge_currency","qualification","season"],"practice_observation":["driving_range_details","driving_range_length_unit","putting_green_details","qualification","range_technology_name"],"price_observation":["amount_kind","audience","billing_basis","conditions","currency","fee_kind","product_name","qualification","residency","residency_area_name","season"],"quality_rating":["dimension","issuer_name","qualification"],"service_observation":["pro_shop_details","qualification","rental_details"]};
const CORE_TEXT=new Set(["access_qualification","address_city","address_postal_code","address_region","address_street_line1","address_street_line2","address_text","arrival_reference","booking_conditions","country","county","description","facility_name","location_note","name","rated_category","state"]);
const CHILD_ROWS=new Set(["aliases","components","course_inventory","round_options","tee_sets"]);
const POSIX_PATH=new RegExp("(?:^|[ \"'`(\\[={:;,<>|!?“”‘’«»])/+[^ /]");
const EXPLICIT_PATH=new RegExp("file://|[a-zİıſK]:[\\\\/]|\\\\{2}");
const LOCAL_ROOT=new RegExp("(?:^|[ \"'`(\\[={:;,<>|!?\u201c\u201d\u2018\u2019\u00ab\u00bb])/+(?:home|users|root|tmp|var|private|mnt|media|volumes|workspace|workspaces|task|tasks|srv|opt|etc|usr|proc|sys|dev|run)(?=$|[ /\\\\?&#;=,:'\"`()<>\\[\\]{}|!?\u201c\u201d\u2018\u2019\u00ab\u00bb]|\\.+(?=$|[ /\\\\?&#;=,:'\"`()<>\\[\\]{}|!?\u201c\u201d\u2018\u2019\u00ab\u00bb]))");
const PRIVATE_COMPONENT=new RegExp("(?:[/\\\\?&#;=]|%2f)(?:private|secret|evidence|capture|retained|recovery)(?=$|[-._]|[ /\\\\?&#;=,:'\"`()<>\\[\\]{}|!?\u201c\u201d\u2018\u2019\u00ab\u00bb])");
const PRIVATE_DECLARATION=new RegExp("(?:^|[^a-z0-9_])(?:private +(?:copy|file|capture|path|directory|folder)|local +(?:copy|file|directory|folder)|evidence +(?:copy|file|directory|folder)|capture +(?:file|path)|capture *:|recovery +(?:sql|dump|file))(?=$|[^a-z0-9_])");
function operationalTextPath(path){
  if(path.length===4&&path[0]==='relationships')return ['component','round_option','tee_set','alias'].includes(path[1])&&Number.isInteger(path[2])&&CORE_TEXT.has(path[3]);
  if(path.length<3||!['facilities','courses'].includes(path[0])||!Number.isInteger(path[1]))return false;
  let parents=path.slice(2,-1);const field=path.at(-1);
  while(parents.length>=2&&CHILD_ROWS.has(parents[0])&&Number.isInteger(parents[1]))parents=parents.slice(2);
  if(!parents.length)return CORE_TEXT.has(field);
  if(parents.length===1&&parents[0]==='address')return ['text','street_line1','street_line2','city','region','postal_code','country'].includes(field);
  if(parents.length===1&&parents[0]==='arrival')return field==='reference';
  if(parents.length>=3&&parents[0]==='optional'&&Object.hasOwn(PUBLIC_DOMAIN_TEXT,parents[1])&&Number.isInteger(parents[2])){
    if(parents.length===3)return PUBLIC_DOMAIN_TEXT[parents[1]].includes(field);
    return parents.length===5&&parents[1]==='architecture_event'&&parents[3]==='credits'&&Number.isInteger(parents[4])&&field==='name';
  }
  return false;
}
function hasPrivatePath(text,operational=false){
  if(credentialSyntax(text))return true;
  const scan=validationScan(text).replace(HTTP_TOKEN,'$1');
  if(EXPLICIT_PATH.test(scan))return true;
  if(!operational)return POSIX_PATH.test(scan);
  return LOCAL_ROOT.test(scan)||(POSIX_PATH.test(scan)&&(PRIVATE_COMPONENT.test(scan)||PRIVATE_DECLARATION.test(scan)));
}
function projectionRecord(value,path){
  if(path.length===2&&path[0]==='source_licenses'&&Number.isInteger(path[1])&&(!object(value)||Object.keys(value).some(key=>!PUBLIC_LICENSE_FIELDS.has(key))||Object.values(value).some(v=>v!==null&&typeof v!=='string')))fail('Unknown or nonpublic source-license material');
  if(path.length===3&&path[0]==='provenance'&&path[1]==='notes'&&Number.isInteger(path[2])&&(!object(value)||Object.keys(value).length!==1||typeof value.id!=='string'||!value.id))fail('Public notes contain IDs only');
}
export function rejectRawEvidence(value,path=[]){
  projectionRecord(value,path);
  if(Array.isArray(value)){value.forEach((row,index)=>rejectRawEvidence(row,[...path,index]));return;}
  if(object(value)){for(const [key,child] of Object.entries(value)){if(PRIVATE_KEYS.has(validationScan(key)))fail('Raw evidence is not operational transport');rejectRawEvidence(key);rejectRawEvidence(child,[...path,key]);}return;}
  if(typeof value==='string'&&(value.includes('\0')||hasPrivatePath(value,operationalTextPath(path))))fail('Private path in public transport');
}
export function validateScopedOptional(value){
  rejectRawEvidence(value);
  const provenance=value.provenance;if(!object(provenance)||!Array.isArray(provenance.sources)||!Array.isArray(provenance.notes)||!Array.isArray(provenance.intake)||!Array.isArray(value.source_licenses))fail('Missing public SQL provenance');
  const sources=unique(provenance.sources);unique(provenance.notes);
  for(const note of provenance.notes)if(Object.keys(note).length!==1||!Object.hasOwn(note,'id'))fail('Public notes contain IDs only');
  const facilities=unique(value.facilities,'facility_id'),courses=unique(value.courses,'course_id');
  const relationships=value.relationships;
  if(!object(relationships)||!sameValue(Object.keys(relationships).sort(),Object.keys(RELATIONSHIP_SCHEMA).sort()))fail('Missing canonical relationship tables');
  const maps={};for(const [kind,schema] of Object.entries(RELATIONSHIP_SCHEMA)){maps[kind]=unique(relationships[kind]);for(const row of maps[kind].values())rowShape(row,schema);}
  const facilityForCourse=id=>courses.get(id)?.facility_id;
  const componentFacility=id=>facilityForCourse(maps.component.get(id)?.course_id);
  const roundFacility=row=>row.facility_id??facilityForCourse(row.course_id);
  for(const part of maps.component.values())if(!courses.has(part.course_id))fail('Orphan component');
  for(const round of maps.round_option.values())if((round.facility_id!==null)===(round.course_id!==null)||!facilities.has(roundFacility(round)))fail('Invalid round owner');
  const members=new Map(),tees=new Map(),ordinals=new Set();
  for(const member of maps.round_component.values()){
    const round=maps.round_option.get(member.round_id);
    const memberCourse=member.course_id??maps.component.get(member.component_id)?.course_id;
    const facility=facilityForCourse(memberCourse);
    if(!round||(member.component_id!==null)===(member.course_id!==null)||!facility||roundFacility(round)!==facility||
      (round.course_id!==null&&round.course_id!==memberCourse)||
      !Number.isSafeInteger(member.ordinal)||member.ordinal<0||!Number.isSafeInteger(member.repetitions)||member.repetitions<1||
      ordinals.has(`${member.round_id}:${member.ordinal}`))fail('Invalid round component membership');
    ordinals.add(`${member.round_id}:${member.ordinal}`);const rows=members.get(member.round_id)||[];rows.push(member);members.set(member.round_id,rows);
  }
  for(const tee of maps.tee_set.values()){
    if((tee.course_id!==null)===(tee.round_id!==null)||tee.course_id!==null&&!courses.has(tee.course_id)||tee.round_id!==null&&!maps.round_option.has(tee.round_id))fail('Invalid tee subject');
    const key=tee.round_id??tee.course_id,rows=tees.get(key)||[];rows.push(tee);tees.set(key,rows);
  }
  for(const alias of maps.alias.values())if((alias.facility_id!==null)===(alias.course_id!==null)||alias.facility_id!==null&&!facilities.has(alias.facility_id)||alias.course_id!==null&&!courses.has(alias.course_id))fail('Invalid alias subject');
  // Build each owner lookup once; retain the same raw rows and membership checks.
  const append=(map,key,row)=>{const rows=map.get(key)||[];rows.push(row);map.set(key,rows);};
  const group=(rows,key)=>{const map=new Map();for(const row of rows)append(map,row[key],row);return map;};
  const coursesByFacility=group(courses.values(),'facility_id'),partsByCourse=group(maps.component.values(),'course_id');
  const roundsByFacility=group(maps.round_option.values(),'facility_id'),roundsByCourse=new Map();
  const aliasesByFacility=group(maps.alias.values(),'facility_id'),aliasesByCourse=group(maps.alias.values(),'course_id');
  for(const round of maps.round_option.values()){
    const owners=new Set();if(round.course_id!==null)owners.add(round.course_id);
    for(const member of members.get(round.id)||[])owners.add(member.course_id??maps.component.get(member.component_id)?.course_id);
    for(const owner of owners)append(roundsByCourse,owner,round);
  }
  const observations=new Map(),envelopes=new Map(),roundViews=new Map(),parties=new Map();
  function optional(subject,column,id){
    const groups=subject.optional;
    if(!object(groups)||!sameValue(Object.keys(groups).sort(),[...OPTIONAL_DOMAINS].sort()))fail('Missing exact optional domain arrays');
    for(const domain of OPTIONAL_DOMAINS){
      const rows=groups[domain];unique(rows);
      if(domain==='quality_rating'&&rows.length)fail('Quality rating population is not approved');
      for(const row of rows){
        rowShape(row,OPTIONAL_SCHEMA[domain]);
        if(!Object.hasOwn(OPTIONAL_SCHEMA[domain],column)||row[column]!==id||SUBJECTS.some(key=>key!==column&&Object.hasOwn(row,key)&&row[key]!==null))fail('Optional observation has wrong subject scope');
        if(typeof row.observation_id!=='string'||!row.observation_id||typeof row.conflict!=='boolean'||!['retained','extracted','confirmed'].includes(row.status))fail('Invalid observation envelope');
        const source=row.source_id===null?null:sources.get(row.source_id);
        if(row.source_id!==null&&!source||row.source_url!==(source?.url??null)||row.source_license!==(source?.license??null)||row.source_attribution!==(source?.attribution??null))fail('Changed observation source binding');
        const envelope=Object.fromEntries(ENVELOPE.map(k=>[k,row[k]]));
        if(envelopes.has(row.observation_id)&&!sameValue(envelopes.get(row.observation_id),envelope))fail('Changed immutable source observation envelope');
        envelopes.set(row.observation_id,envelope);
        if(domain==='architecture_event'){
          unique(row.credits);for(const credit of row.credits){rowShape(credit,CREDIT);if(!credit.party_id||!credit.name)fail('Missing architecture party');const party={name:credit.name,party_kind:credit.party_kind};if(parties.has(credit.party_id)&&!sameValue(parties.get(credit.party_id),party))fail('Changed architecture party identity');parties.set(credit.party_id,party);}
        }
        const key=domain+':'+row.id;if(observations.has(key)&&!sameValue(observations.get(key),row))fail('Changed shared observation identity');observations.set(key,row);
      }
    }
  }
  function childRows(actual,expected,schema){const rows=unique(actual);assertIds([...rows.keys()],expected.map(r=>r.id));for(const row of rows.values())if(!rawMatches(row,expected.find(r=>r.id===row.id),schema))fail('Changed nested relationship row');}
  function rounds(subject,expected){
    const views=unique(subject.round_options);assertIds([...views.keys()],expected.map(r=>r.id));
    for(const round of views.values()){
      const raw=maps.round_option.get(round.id);if(!rawMatches(round,raw,RELATIONSHIP_SCHEMA.round_option)||round.scope!==(raw.facility_id!==null?'facility':'course'))fail('Changed round ownership');
      childRows(round.members,members.get(round.id)||[],RELATIONSHIP_SCHEMA.round_component);childRows(round.tee_sets,tees.get(round.id)||[],RELATIONSHIP_SCHEMA.tee_set);optional(round,'round_id',round.id);
      if(roundViews.has(round.id)&&!sameValue(roundViews.get(round.id),round))fail('Changed shared round view');roundViews.set(round.id,round);
    }
  }
  for(const facility of facilities.values()){
    if(![null,'public','private','restricted'].includes(facility.access))fail('Invalid nullable facility access');
    optional(facility,'facility_id',facility.facility_id);
    const own=coursesByFacility.get(facility.facility_id)||[];assertIds(facility.course_ids,own.map(c=>c.course_id));
    const inventory=unique(facility.course_inventory,'course_id');assertIds([...inventory.keys()],own.map(c=>c.course_id));
    for(const row of inventory.values()){const course=courses.get(row.course_id);for(const key of ['name','physical_holes','identity_status','access','nonmember_bookable'])if(row[key]!==course[key])fail('Changed facility inventory view');}
    rounds(facility,roundsByFacility.get(facility.facility_id)||[]);
    childRows(facility.aliases,aliasesByFacility.get(facility.facility_id)||[],RELATIONSHIP_SCHEMA.alias);
  }
  for(const course of courses.values()){
    if(![null,'public','private','restricted'].includes(course.access))fail('Invalid nullable course access');
    const facility=facilities.get(course.facility_id);if(!facility||course.facility_access!==facility.access||course.facility_name!==facility.name||course.state!==facility.state)fail('Changed course facility binding');
    optional(course,'course_id',course.course_id);
    const parts=partsByCourse.get(course.course_id)||[];childRows(course.components,parts,RELATIONSHIP_SCHEMA.component);for(const part of course.components)optional(part,'component_id',part.id);
    rounds(course,roundsByCourse.get(course.course_id)||[]);
    childRows(course.tee_sets,tees.get(course.course_id)||[],RELATIONSHIP_SCHEMA.tee_set);childRows(course.aliases,aliasesByCourse.get(course.course_id)||[],RELATIONSHIP_SCHEMA.alias);
  }
  return observations;
}
const label=key=>key.replace(/^physical_holes/, 'holes').replaceAll('_',' ');
function scalar(value){return value===null?'Unconfirmed':typeof value==='boolean'?(value?'Yes':'No'):String(value);}
export function renderOptional(optional,{subjectLabel,document=globalThis.document}={}){
  const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const holder=el('section');holder.className='typed-observations';holder.append(el('h4',subjectLabel));
  let count=0;
  for(const domain of OPTIONAL_DOMAINS){for(const row of optional[domain]){
    count++;const details=el('details');details.dataset.observationId=row.id;details.dataset.subject=subjectLabel;
    details.append(el('summary',`${LABELS[domain]}${row.conflict?' · conflicting observations':''}${domain==='price_observation'&&row.historical===true?' · historical':''}`));
    details.append(el('p',`Scope: ${subjectLabel}. Observed ${row.observed_on??'date unknown'}; collected ${row.collected_on??'date unknown'}; effective ${row.effective_from??'unknown'} to ${row.effective_to??'unknown'}; status ${row.status??'unconfirmed'}.`));
    if(row.qualification!==null)details.append(el('p',row.qualification));
    const fields=el('dl');fields.className='observation-fields';
    for(const key of Object.keys(OPTIONAL_SCHEMA[domain]))if(!META.has(key)&&key!=='credits')fields.append(el('dt',label(key)),el('dd',scalar(row[key])));
    details.append(fields);
    if(domain==='architecture_event')for(const credit of row.credits)details.append(el('p',`${credit.name} · ${credit.party_kind??'party type unconfirmed'} · role: ${credit.role??'unconfirmed'}`));
    if(domain==='price_observation')details.append(el('p','Dated observation, not a current quote or booking offer. All recorded conditions apply.'));
    details.append(el('p',`Source license: ${row.source_license??'not recorded'} · attribution: ${row.source_attribution??'not recorded'}`));
    if(row.source_url!==null){try{const u=new URL(row.source_url);if(['http:','https:'].includes(u.protocol)){const link=el('a','Source');link.href=u.href;link.target='_blank';link.rel='noopener noreferrer';details.append(link);}}catch{}}
    holder.append(details);
  }}
  if(!count)holder.append(el('p','No optional observations recorded for this scope. Unknown values are not evidence of absence.'));
  return holder;
}

// Popups show recorded values only; canonical data retains the source envelope and unknowns.
export function renderKnownOptional(optional,{subjectLabel,document=globalThis.document}={}){
  const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const holder=el('section');holder.className='typed-observations';
  let count=0;
  for(const domain of OPTIONAL_DOMAINS)for(const row of optional?.[domain]||[]){
    const keys=Object.keys(OPTIONAL_SCHEMA[domain]).filter(key=>!META.has(key)&&key!=='credits'&&row[key]!==null&&row[key]!==undefined);
    const credits=domain==='architecture_event'?row.credits||[]:[];
    if(!keys.length&&!credits.length&&!row.qualification)continue;
    if(!count++)holder.append(el('h4',subjectLabel));
    const details=el('details');
    details.append(el('summary',`${LABELS[domain]}${row.conflict?' · conflicting observations':''}${domain==='price_observation'&&row.historical===true?' · historical':''}`));
    const dates=[row.observed_on?`Observed ${row.observed_on}`:null,row.effective_from?`From ${row.effective_from}`:null,row.effective_to?`Through ${row.effective_to}`:null].filter(Boolean);
    if(dates.length)details.append(el('p',dates.join(' · ')));
    if(row.qualification)details.append(el('p',row.qualification));
    const fields=el('dl');fields.className='observation-fields';
    for(const key of keys)fields.append(el('dt',label(key)),el('dd',scalar(row[key])));
    if(keys.length)details.append(fields);
    for(const credit of credits)details.append(el('p',[credit.name,credit.party_kind,credit.role].filter(Boolean).join(' · ')));
    holder.append(details);
  }
  if(!count)return null;
  return holder;
}
