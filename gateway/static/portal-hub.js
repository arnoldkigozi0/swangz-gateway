"use strict";
(() => {
  const P=SWP,H=HubUI,{el,icon,fmt,toast}=SUI;
  const set=(key,value)=>{const q=new URLSearchParams(location.hash.split('?')[1]||'');value?q.set(key,value):q.delete(key);if(key!=="offset")q.delete("offset");location.hash=location.hash.split('?')[0]+"?"+q;};
  function pagination(data){return el("div",{class:"hub-pagination"},el("span",{class:"muted small"},`${data.total} records · ${Math.min(data.offset+1,data.total)}–${Math.min(data.offset+data.limit,data.total)}`),
    el("div",{class:"hub-actions"},el("button",{class:"btn btn--small",disabled:!data.offset,onclick:()=>set('offset',String(Math.max(0,data.offset-data.limit)))},"Previous"),el("button",{class:"btn btn--small",disabled:data.offset+data.limit>=data.total,onclick:()=>set('offset',String(data.offset+data.limit))},"Next")));}
  const open=id=>{const q=new URLSearchParams(location.hash.split('?')[1]||'');q.set('report',id);q.delete('step');location.hash='#/weekly?'+q;};
  async function list(params,kind,state){const q=new URLSearchParams({kind,limit:'30',offset:params.get('offset')||'0'});if(state)q.set('state',state);for(const k of ['week','q'])if(params.get(k))q.set(k,params.get(k));const data=await P.api('GET','/hub/reports?'+q);return el('div',null,H.reportRows(data,open),pagination(data));}
  async function weekly(params){
    const holder=el('div',{class:'hub-content'});const rid=params.get('report');
    P.frame('Weekly reports',el('section',{class:'hub-page'},el('div',{class:'shell narrow'},P.sectionHead('Accountability','Weekly reports','Monday–Sunday in the company time zone. A submitted report clears its reporting requirement.'),holder)));
    if(rid){
      await SUI.load(holder,async()=>{const r=await P.api('GET','/hub/reports/'+encodeURIComponent(rid));
        const back=el('a',{class:'btn btn--small',href:'#/weekly?view='+(r.kind==='adoption'?'adoption':'pending')},icon('chevronLeft'),'All reports');
        const heading=el('div',{class:'spread'},el('div',null,el('h2',null,r.tool_name),el('p',{class:'muted small'},r.period?`${r.period.week_start} – ${r.period.week_end} · due ${fmt.stamp(r.period.ends)} · ${r.period.timezone}`:'Adoption and business impact report')),H.status(r.state));
        if(['draft','returned'].includes(r.state))return el('div',{class:'hub-content'},back,heading,H.wizard(r,P.api,{params,onDone:async()=>{P.S.me=await P.api('GET','/me');P.render();}}));
        const views=P.viewTabs('#/weekly',params,[['summary','Declaration',()=>H.declaration(r)],['evidence','System evidence',()=>H.evidence(r.evidence)],['history','Versions & review',()=>H.history(r)]],'Report details');
        const tool=P.S.me.catalog.find(t=>t.id===r.tool_id);const others=(P.S.me.weekly_reports||[]).filter(p=>p.tool_id===r.tool_id);
        return el('div',{class:'hub-content'},back,heading,r.kind==='weekly'?el('div',{class:'notice ok',role:'status'},others.length?`${others.length} other report(s) still need completion for this tool.`:'This report is submitted. Its reporting requirement is cleared.',
          tool?.state==='enabled'&&!others.length?el('a',{class:'btn btn--small',href:P.gurl('/go/'+r.tool_id),target:'_blank',rel:'noopener'},'Open tool'):null):null,views.node);
      },SUI.skeleton('rows',4));return;
    }
    const toolbar=el('form',{class:'hub-toolbar',onsubmit:e=>{e.preventDefault();set('q',search.value);}},
      el('label',{class:'field'},el('span',null,'Search reports'),el('input',{class:'input',id:'hub-staff-search',type:'search',value:params.get('q')||''})),
      el('label',{class:'field'},el('span',null,'Week beginning Monday'),el('input',{class:'input',type:'date',value:params.get('week')||'',onchange:e=>set('week',e.target.value)})),el('button',{class:'btn',type:'submit'},'Search'));
    const search=toolbar.querySelector('input[type=search]');
    const views=P.viewTabs('#/weekly',params,[['pending','Pending & returned',()=>list(params,'weekly','pending')],['completed','Submitted',()=>list(params,'weekly','completed')],['adoption','Adoption & impact',async()=>{
      const select=el('select',{class:'input','aria-label':'Tool for adoption report'},el('option',{value:''},'Choose a catalogue tool'),...P.S.me.catalog.map(t=>el('option',{value:t.id},t.name)));
      const add=el('button',{class:'btn btn--solid',onclick:async()=>{if(!select.value){toast('Choose a tool.',true);return;}add.disabled=true;try{const r=await P.api('POST','/hub/adoption',{tool_id:select.value});open(r.id);}catch(e){toast(e.message,true);add.disabled=false;}}},'File adoption report');
      return el('div',{class:'hub-content'},el('div',{class:'hub-toolbar'},select,add),await list(params,'adoption'));}]],'Report views');
    holder.append(toolbar,views.node);
  }
  async function procurement(){const params=new URLSearchParams(location.hash.split('?')[1]||'');const data=await P.api('GET','/hub/procurement?offset='+encodeURIComponent(params.get('offset')||'0'));const section=el('div',{class:'hub-content'});
    section.append(el('details',null,el('summary',null,'Propose a tool, subscription or credits'),H.procurementForm(P.api,()=>P.render())),data.items.length?SUI.table({caption:'Your procurement requests',columns:[{key:'tool_name',label:'Tool',lead:true},{key:'purchase_type',label:'Purchase',render:r=>H.stateLabel(r.purchase_type)},
      {key:'state',label:'Status',render:r=>H.status(r.state)},{key:'admin_note',label:'Admin note'},{key:'created',label:'Submitted',render:r=>fmt.stamp(r.created)}],rows:data.items}):SUI.stateBox({title:'No procurement requests',text:'Use this workflow for a new purchase. Access to an existing tool stays in Access requests.'}),pagination(data));return section;}
  async function notes(){const data=await P.api('GET','/hub/notifications');return data.items.length?el('ul',{class:'notices'},data.items.map(n=>el('li',null,el('a',{href:n.href,onclick:()=>P.api('POST','/hub/notifications/'+n.id+'/read').catch(()=>{})},n.title),el('span',{class:'muted small'},' · '+fmt.ago(n.created)+' · email '+n.email_state)))):el('p',{class:'muted'},"You’re all caught up. Reporting and procurement decisions appear here.");}
  async function activity(params){const holder=el('div',{class:'hub-content'});P.frame('Activity',el('section',{class:'hub-page'},el('div',{class:'shell'},P.sectionHead(null,'My activity','Your recorded API and access events. Website opens do not confirm AI work; costs are estimates.'),holder)));
    await SUI.load(holder,async()=>{const q=new URLSearchParams({offset:params.get('offset')||'0',source:params.get('source')||'all'});const data=await P.api('GET','/hub/activity?'+q);return el('div',null,
      el('label',{class:'field'},el('span',null,'Evidence source'),el('select',{class:'input',onchange:e=>set('source',e.target.value)},...['all','api','launch','website'].map(v=>el('option',{value:v,selected:v===q.get('source')},v)))),
      data.items.length?SUI.table({caption:'Your recorded activity',columns:[{key:'ts',label:'When',render:r=>fmt.stamp(r.ts)},{key:'tool',label:'Tool'},{key:'source',label:'Source'},{key:'outcome',label:'Outcome'},{key:'model',label:'Model',hideSm:true},{key:'estimated_cost',label:'Estimated cost',render:r=>fmt.money(r.estimated_cost)}],rows:data.items}):SUI.stateBox({title:'No observed activity',text:'Unconnected browsers and retained-data limits can leave gaps.'}),pagination(data));},SUI.skeleton('rows',4));}
  P.hubProcurement=procurement;P.hubNotes=notes;P.page(/^#\/weekly$/,weekly);P.page(/^#\/activity$/,activity);
})();
