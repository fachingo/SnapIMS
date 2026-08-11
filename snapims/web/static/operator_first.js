(()=>{
  const q=(s,r=document)=>r.querySelector(s);
  const qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const csrf=q('meta[name="csrf-token"]')?.content||q('meta[name="snapims-csrf"]')?.content||'';
  if(csrf){qa('form[method="post" i]').forEach(form=>{if(!form.querySelector('input[name="csrf_token"]')){const i=document.createElement('input');i.type='hidden';i.name='csrf_token';i.value=csrf;form.prepend(i);}});}

  const palette=q('#command-palette');
  const paletteQuery=q('#command-search');
  const paletteResults=q('#operator-palette-results');
  const helpDialog=q('#operator-help-dialog');
  const helpContent=q('#operator-help-content');
  let lastHelp='';
  let lastHelpElement=null;
  let paletteAbort=null;

  async function paletteSearch(){
    if(!paletteResults||!paletteQuery)return;
    paletteAbort?.abort(); paletteAbort=new AbortController();
    try{
      const r=await fetch('/api/operator-first/palette?q='+encodeURIComponent(paletteQuery.value||''),{signal:paletteAbort.signal});
      if(!r.ok)return;
      const data=await r.json(); let html='';
      for(const group of data.groups||[]){
        if(!group.results?.length)continue;
        html+=`<section class="operator-palette-group"><h3>${esc(group.label)}</h3>`;
        for(const row of group.results){
          if(row.help_key){
            html+=`<button type="button" class="operator-palette-result" data-palette-help="${esc(row.help_key)}">${esc(row.label)}${row.detail?`<small> · ${esc(row.detail)}</small>`:''}</button>`;
          }else{
            html+=`<a class="operator-palette-result" href="${esc(row.url)}">${esc(row.label)}${row.detail?`<small> · ${esc(row.detail)}</small>`:''}</a>`;
          }
        }
        html+='</section>';
      }
      paletteResults.innerHTML=html||'<p class="muted">No matches.</p>';
    }catch(e){if(e.name!=='AbortError')console.warn('SnapIMS palette search failed',e);}
  }

  function openPalette(){if(!palette)return;palette.showModal();if(paletteQuery){paletteQuery.focus();paletteQuery.select();paletteSearch();}}
  function interactive(el){return el?.closest?.('button,input:not([type=hidden]),select,textarea,a[href],summary,[data-help-key]')||null;}
  function controlLabel(el){
    if(!el)return'';
    const id=el.id;
    const lab=id?document.querySelector(`label[for="${CSS.escape(id)}"]`):null;
    const parent=el.closest('label');
    return (el.getAttribute('aria-label')||el.title||lab?.innerText||parent?.innerText||el.innerText||el.name||el.getAttribute('href')||el.tagName||'Control').replace(/\s+/g,' ').trim().slice(0,160);
  }
  function autoHelpUrl(el){
    const form=el?.closest?.('form');
    const kind=(el?.type||el?.tagName||'control').toLowerCase();
    const p=new URLSearchParams({label:controlLabel(el),kind,name:el?.name||'',form_action:form?.getAttribute('action')||'',href:el?.getAttribute?.('href')||''});
    return '/api/operator-first/help-auto?'+p.toString();
  }
  async function openHelp(key,el){
    key=key||lastHelp; el=el||lastHelpElement;
    if(!helpDialog||!helpContent)return;
    const url=key?'/api/operator-first/help/'+encodeURIComponent(key):(el?autoHelpUrl(el):'');
    if(!url){helpContent.innerHTML='<h2>Contextual Help</h2><p>Focus any button, field, menu, link, or control and press F1, or right-click it.</p>';helpDialog.showModal();return;}
    const r=await fetch(url); if(!r.ok)return;
    const t=await r.json();
    helpContent.innerHTML=`<h2>${esc(t.title)}</h2><p>${esc(t.purpose)}</p><dl class="operator-help-grid"><dt>When to use</dt><dd>${esc(t.when_to_use)}</dd><dt>Effect</dt><dd>${esc(t.effect)}</dd>${t.warnings?`<dt>Warnings</dt><dd>${esc(t.warnings)}</dd>`:''}${t.example?`<dt>Example</dt><dd>${esc(t.example)}</dd>`:''}${t.related?.length?`<dt>Related</dt><dd>${esc(t.related.join(', '))}</dd>`:''}</dl>`;
    helpDialog.showModal();
  }

  document.addEventListener('focusin',e=>{const el=interactive(e.target);if(el){lastHelpElement=el;lastHelp=el.dataset?.helpKey||'';}});
  document.addEventListener('contextmenu',e=>{const el=interactive(e.target);if(el){e.preventDefault();lastHelpElement=el;lastHelp=el.dataset?.helpKey||'';openHelp(lastHelp,el);}});
  document.addEventListener('keydown',e=>{
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openPalette();return;}
    if((e.ctrlKey||e.metaKey)&&e.shiftKey&&e.key.toLowerCase()==='f'){e.preventDefault();location.href='/search';return;}
    if(e.key==='F1'){const el=interactive(document.activeElement);if(el){e.preventDefault();lastHelpElement=el;lastHelp=el.dataset?.helpKey||'';openHelp(lastHelp,el);}}
  });
  document.addEventListener('click',e=>{const b=e.target.closest?.('[data-palette-help]');if(b){e.preventDefault();palette?.close();openHelp(b.dataset.paletteHelp);}});
  paletteQuery?.addEventListener('input',paletteSearch);
  q('#operator-search-open')?.addEventListener('click',()=>{location.href='/search';});
  q('#operator-help-open')?.addEventListener('click',()=>openHelp());
  q('#operator-help-close')?.addEventListener('click',()=>helpDialog?.close());

  // Guard repeated Enter/double-submit without changing the expected Enter=Approve semantics.
  const review=q('#operator-review-form');
  if(review){let submitted=false;review.addEventListener('submit',e=>{if(submitted){e.preventDefault();return;}submitted=true;qa('button',review).forEach(b=>b.disabled=true);});}

  const bulkThreshold=q('#operator-bulk-threshold'), bulkCount=q('#operator-bulk-count'), bulkForm=q('#operator-bulk-confidence');
  let bulkTimer=null;
  async function refreshBulkCount(){if(!bulkThreshold||!bulkCount||!bulkForm)return;const batch=q('input[name="batch_id"]',bulkForm)?.value||'';if(!batch)return;const endpoint=bulkForm.dataset.operatorBulkPreview;const r=await fetch(endpoint+'?batch_id='+encodeURIComponent(batch)+'&threshold_percent='+encodeURIComponent(bulkThreshold.value||95));if(!r.ok)return;const data=await r.json();bulkCount.textContent=String(data.eligible_count??0);}
  bulkThreshold?.addEventListener('input',()=>{clearTimeout(bulkTimer);bulkTimer=setTimeout(refreshBulkCount,180);});
  refreshBulkCount();
})();
