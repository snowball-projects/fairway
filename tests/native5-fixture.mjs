import {readFileSync} from 'node:fs';
export const fixtureBytes=readFileSync(new URL('./fixtures/native5-ui/transport.json',import.meta.url));
export function fixture(){
  const value=JSON.parse(fixtureBytes);
  const manifest={...Object.fromEntries(['format_version','schema','revision','catalog_release_key'].map(k=>[k,value[k]])),counts:Object.fromEntries(['facilities','courses','destinations'].map(k=>[k,value[k].length]))};
  return {value,manifest};
}
export class Element{
  constructor(tag){this.tag=tag;this.children=[];this.value='';this.dataset={};}
  addEventListener(){}
  append(...nodes){this.children.push(...nodes);}
  set textContent(value){this.value=String(value);this.children=[];}
  get textContent(){return this.value+this.children.map(n=>typeof n==='string'?n:n.textContent).join(' ');}
}
export const document={createElement:tag=>new Element(tag)};
