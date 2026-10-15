import {readFileSync} from 'node:fs';
export const fixtureBytes=readFileSync(new URL('./fixtures/native5-ui/transport.json',import.meta.url));
export function fixture(){
  const value=JSON.parse(fixtureBytes);
  const manifest={...Object.fromEntries(['format_version','schema','revision','catalog_release_key'].map(k=>[k,value[k]])),counts:Object.fromEntries(['facilities','courses','destinations'].map(k=>[k,value[k].length]))};
  return {value,manifest};
}
export class Element{
  constructor(tag){this.tag=tag;this.children=[];this.value='';this.dataset={};this.open=false;this.listeners=new Map();}
  addEventListener(type,listener){const handlers=this.listeners.get(type)||[];handlers.push(listener);this.listeners.set(type,handlers);}
  dispatchEvent(event){for(const listener of this.listeners.get(event.type)||[])listener.call(this,event);return true;}
  append(...nodes){this.children.push(...nodes);}
  set textContent(value){this.value=String(value);this.children=[];}
  get textContent(){return this.value+this.children.map(n=>typeof n==='string'?n:n.textContent).join(' ');}
}
export const document={createElement:tag=>new Element(tag)};

export function expand(element){element.open=true;element.dispatchEvent({type:'toggle'});return element;}
