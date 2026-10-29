import {OPTIONAL_SCHEMA,OPTIONAL_DOMAINS} from './optional-schema.mjs';
export {OPTIONAL_DOMAINS};
const SUBJECTS=['facility_id','course_id','component_id','round_id'];
const META=new Set(['id','observation_id',...SUBJECTS,'source_id','source_url','source_license','source_attribution','collected_on','observed_on','effective_from','effective_to','status','conflict','qualification']);
const LABELS={physical_characteristics:'Physical characteristics',amenity_observation:'Amenities',practice_observation:'Practice',service_observation:'Services',policy_observation:'Policies',operating_period:'Operating periods',accessibility_observation:'Accessibility',price_observation:'Dated price observations',architecture_event:'Design and architecture',quality_rating:'Quality ratings'};
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
