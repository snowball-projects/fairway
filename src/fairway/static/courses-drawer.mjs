// Local presentation only. No planning, catalog, transport or map mutations.
export function drawerLimits(viewportWidth) {
  const maximum = Math.max(0, Math.min(640, viewportWidth - 44));
  return {minimum:Math.min(280, maximum), maximum};
}
export function sheetLimits(viewportHeight) {
  const maximum = Math.max(0, viewportHeight - Math.min(240, viewportHeight*.4));
  return {minimum:Math.min(260, Math.max(160, viewportHeight*.3), maximum), maximum};
}
export function bindCoursesDrawer({shell, panel, grip, setOpen, viewport, viewportHeight=()=>844, onActivate=()=>{}}) {
  let width = Math.min(360, drawerLimits(viewport()).maximum);
  let height = null;
  let mode = viewport()<=800 ? 'sheet' : 'side';
  let drag = null, suppressClick = false;
  const clamp = (value,limits) => Math.max(limits.minimum, Math.min(limits.maximum, value));
  const limits = () => mode==='sheet' ? sheetLimits(viewportHeight()) : drawerLimits(viewport());
  const size = () => clamp(mode==='sheet'?(height??viewportHeight()*.58):width,limits());
  function cancelDrag(blockClick=false) {
    if (!drag) return;
    const id=drag.id;suppressClick=blockClick||drag.moved;drag=null;
    if (grip.hasPointerCapture(id)) grip.releasePointerCapture(id);
  }
  function sync(open) {
    const next=viewport()<=800?'sheet':'side';
    if (drag && (next!==mode || drag.viewportHeight!==viewportHeight() || drag.viewportWidth!==viewport())) cancelDrag(true);
    mode=next;
    shell.style.width=mode==='sheet'?'100%':open?`${size()}px`:'0px';
    shell.style.height=mode==='sheet'?(open?`${size()}px`:'0px'):'';
    shell.dataset.mode=mode;shell.dataset.open=String(open);
    grip.setAttribute('aria-expanded',String(open));
    grip.setAttribute('aria-label',open?'Collapse courses':'Open courses');
  }
  function resize(value) {
    if(value<=(mode==='sheet'?84:72)){setOpen(false);return;}
    if(mode==='sheet')height=clamp(value,limits());else width=clamp(value,limits());
    if(panel.hidden)setOpen(true);else sync(true);
  }
  grip.addEventListener('focus',onActivate);
  grip.addEventListener('click',event=>{
    event.stopPropagation();
    if(suppressClick && event.detail!==0){suppressClick=false;return;}
    suppressClick=false;onActivate();setOpen(panel.hidden);
  });
  grip.addEventListener('pointerdown',event=>{
    if(drag || event.isPrimary===false || event.button!==0)return;
    event.stopPropagation();suppressClick=false;
    drag={id:event.pointerId,x:event.clientX,y:event.clientY,size:panel.hidden?0:size(),mode,viewportHeight:viewportHeight(),viewportWidth:viewport(),moved:false};
    onActivate();grip.focus({preventScroll:true});grip.setPointerCapture(event.pointerId);
  });
  grip.addEventListener('pointermove',event=>{
    if(!drag || event.pointerId!==drag.id)return;
    event.stopPropagation();
    if(Math.hypot(event.clientX-drag.x,event.clientY-drag.y)>6)drag.moved=true;
    if(drag.moved){event.preventDefault();resize(drag.size+(drag.mode==='sheet'?drag.y-event.clientY:drag.x-event.clientX));}
  });
  function finish(event){
    if(!drag || event.pointerId!==drag.id)return;
    event.stopPropagation();cancelDrag();
  }
  grip.addEventListener('pointerup',finish);grip.addEventListener('pointercancel',finish);
  grip.addEventListener('lostpointercapture',event=>{if(drag?.id===event.pointerId){suppressClick=drag.moved;drag=null;}});
  grip.addEventListener('keydown',event=>{
    if(['Enter',' '].includes(event.key)){onActivate();return;}
    const increase=mode==='sheet'?'ArrowUp':'ArrowLeft',decrease=mode==='sheet'?'ArrowDown':'ArrowRight';
    if(![increase,decrease,'Home','End'].includes(event.key))return;
    event.preventDefault();event.stopPropagation();onActivate();
    if(event.key==='End')setOpen(false);
    else if(event.key==='Home')resize(limits().maximum);
    else if(event.key===increase)resize(panel.hidden?size():size()+24);
    else if(!panel.hidden){if(size()<=limits().minimum)setOpen(false);else resize(size()-24);}
  });
  sync(!panel.hidden);return {sync};
}
