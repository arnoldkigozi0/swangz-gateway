"use strict";
/* Shared native reporting UI. All declarations arrive through text nodes and labelled controls. */
(() => {
  const { el, fmt, icon, toast } = SUI;
  const text = v => v === null || v === undefined || v === "" ? "Unknown / not provided" : String(v);
  const stateLabel = s => ({draft:"Pending / draft",submitted:"Submitted",resubmitted:"Resubmitted",reviewed:"Reviewed",confirmed:"Confirmed",returned:"Returned for correction"}[s] || s.replaceAll("_"," "));
  const status = s => SUI.status(["draft","returned","needs_review"].includes(s)?"waiting":"info",stateLabel(s),{plain:true});
  const caches = new Map(); let active = null; let purchaseDraft = {}; let purchaseDirty = false;
  function dirty() { return !!((active && active.dirty && document.querySelector(".hub-wizard")) || (purchaseDirty && document.querySelector(".hub-procurement-form"))); }
  function guard() { if (!dirty()) return true; if (!confirm("Leave this report without saving your latest changes? Your saved draft remains available.")) return false; if(active){caches.delete(active.id); active.dirty = false;}purchaseDirty=false;return true; }
  addEventListener("beforeunload",e=>{ if(dirty()){e.preventDefault();e.returnValue="";} });
  const fact = (label,value) => el("div",{class:"hub-fact"},el("dt",null,label),el("dd",null,text(value)));
  function evidence(e) {
    if(!e) return SUI.stateBox({title:"Adoption declaration",text:"This adoption entry has no weekly Gateway telemetry. It does not prove activity during any particular week."});
    return el("section",{class:"hub-evidence"},el("h3",null,"System observations"),
      el("p",{class:"muted small"},e.completeness === "access_only" ? "Access-level evidence. Opening a tool is not proof of AI work." : "API activity observed independently by the Hub."),
      el("dl",{class:"hub-facts hub-evidence-summary"},fact("API requests",e.api_requests),fact("Access events",e.launches+e.access_events),fact("Observed days",e.active_days)),
      el("details",null,el("summary",null,"More metrics, limits and source records"),
        el("dl",{class:"hub-facts"},fact("Successful / failed",`${e.api_success} / ${e.api_failed}`),fact("Tokens in / out",`${e.input_tokens} / ${e.output_tokens}`),
          fact("Estimated API cost",e.estimated_api_cost === null?null:fmt.money(e.estimated_api_cost)),fact("Recorded tab-open seconds",e.tab_open_seconds),fact("Shared occupancy seconds",e.shared_occupancy_seconds)),
        el("p",{class:"muted small"},e.limitations),
        SUI.table({caption:"Evidence source references",columns:[{key:"source",label:"Source"},{key:"source_id",label:"Record"},{key:"ts",label:"When",render:r=>fmt.stamp(r.ts)},
          {key:"outcome",label:"Outcome"},{key:"model",label:"Model",hideSm:true},{key:"cost_source",label:"Cost basis",hideSm:true}],rows:e.events || []})));
  }
  function declaration(r) {
    const fields=[['usage_confirmation','Usage confirmation'],['reason','Purpose / business problem'],['deliverables','Deliverables'],['quality','Quality'],['impact','Business impact'],
      ['manual_hours','Estimated manual work hours'],['ai_hours','Estimated AI-assisted work hours'],['manual_cost','Declared manual cost'],['ai_cost','Declared AI cost'],
      ['subscription_cost','Declared subscription cost'],['extra_credits','Declared credits'],['other_expenses','Other declared expenses'],['revenue','Estimated revenue contribution'],
      ['revenue_description','Revenue explanation'],['selected_plan','Declared plan'],['usage_amount','Declared metered quantity'],['usage_unit','Metered unit'],['usage_included','Declared included quantity'],['usage_unit_cost_usd','Declared unit price (USD)'],['usage_cost_usd','Tracker / staff-declared usage allocation (USD)'],['usage_flat_rate','Flat subscription pricing'],['pricing_source','Declared pricing basis'],['challenges','Challenges'],['issues','Privacy / quality concerns'],['next_steps','Next steps']];
    return el("section",null,r.import_provenance?el("aside",{class:"hub-reminder"},el("strong",null,"Imported history"),el("p",null,r.import_provenance.note),el("span",{class:"muted small"},"Source record: "+r.import_provenance.source_id)):null,el("p",{class:"muted small"},"Staff declarations and estimates; submission does not independently verify business value or vendor spend. Currency: "+r.currency),
      el("dl",{class:"hub-facts declaration"},fields.map(([k,label])=>fact(label,k==="usage_flat_rate"&&r[k]!==null?(r[k]?"Yes":"No"):r[k]))),
      el("h3",null,"Projects and supporting work"),r.projects?.length ? el("ul",{class:"hub-project-list"},r.projects.map(p=>el("li",null,el("strong",null,p.name),el("p",null,p.description),...[ ["Traditional approach",p.traditional],["AI-assisted approach",p.ai_way],["Benefit",p.benefit] ].filter(x=>x[1]).map(([label,v])=>el("p",null,el("strong",null,label+": "),v)),
        p.link?el("a",{href:p.link,target:"_blank",rel:"noopener noreferrer"},"Open supporting link",icon("open")):null))) : el("p",{class:"muted"},"No supporting projects provided."));
  }
  function history(r) {
    return el("div",null,el("h3",null,"Submission versions"),r.versions.length?el("div",{class:"hub-history"},r.versions.map(v=>el("details",null,
      el("summary",null,`Version ${v.version} · ${fmt.stamp(v.submitted)} · ${v.actor}`),declaration({...v.declaration,projects:v.declaration.projects||[]}),el("p",{class:"muted"},v.reconciliation_reason)))):el("p",{class:"muted"},"Not yet submitted."),
      el("h3",null,"Review history"),r.reviews.length?el("ul",{class:"hub-history"},r.reviews.map(v=>el("li",null,el("strong",null,`${stateLabel(v.action)} · ${v.actor}`),el("span",{class:"muted small"}," · "+fmt.stamp(v.ts)),el("p",null,v.note)))):el("p",{class:"muted"},"No review decisions yet."));
  }
  function reportRows(data,open,admin=false) {
    if(!data.items.length) return SUI.stateBox({icon:"report",title:"No reports in this view",text:"Weekly reports are created only for completed weeks with qualifying activity. You can also file an adoption report."});
    return SUI.table({caption:"Tool reports",columns:[{key:"tool_name",label:"Tool",lead:true,render:r=>el("button",{class:"btn btn--quiet",type:"button",onclick:()=>open(r.id)},r.tool_name)},
      ...(admin?[{key:"submitter_name",label:"Staff member"},{key:"department",label:"Department",hideSm:true}]:[]),
      {key:"week_start",label:"Period",render:r=>r.period?el("span",{class:"hub-period"},el("span",null,r.period.week_start),el("span",null,"– "+r.period.week_end)):fmt.date(r.created)},
      {key:"state",label:"Status",render:r=>status(r.state)},
      {key:"evidence",label:"Observed activity",sort:false,hideSm:true,render:r=>r.evidence?`${r.evidence.api_requests} API · ${r.evidence.launches+r.evidence.access_events} access`:"No weekly telemetry"},
      ...(admin?[{key:"reconciliation",label:"Reconciliation",render:r=>stateLabel(r.reconciliation)}]:[])],rows:data.items});
  }
  const steps=["Confirm usage","Purpose & project","Results & impact","Time & cost","Issues & next steps","Review & submit"];
  const numeric=new Set(["manual_hours","ai_hours","manual_cost","ai_cost","subscription_cost","extra_credits","other_expenses","revenue","frequency","usage_amount","usage_included","usage_unit_cost_usd","usage_cost_usd","usage_flat_rate","claimed_requests","claimed_access_events","claimed_days"]);
  function wizard(report,api,{onDone,onDirty,params}) {
    let c=caches.get(report.id);
    if(!c || (!c.dirty && c.model.updated !== report.updated)){ c={id:report.id,model:{...report,projects:report.projects.map(p=>({...p}))},dirty:false};caches.set(report.id,c); }
    active=c;const m=c.model;let step=Math.max(0,Math.min(5,Number(params?.get("step"))||0));
    const root=el("section",{class:"hub-wizard", "aria-label":"Report wizard"});
    const err=el("p",{class:"form-error",role:"alert"});const saved=el("span",{class:"muted small",role:"status"},report.state==="returned"?"Returned: "+report.reviewer_note:"Saved draft");
    const change=()=>{c.dirty=true;saved.textContent="Unsaved changes";onDirty?.(()=>c.dirty);};
    function field(key,label,{type="textarea",help,required=false}={}) {
      const id="report-"+report.id+"-"+key;
      const attrs={id,class:"input",required,oninput:e=>{m[key]=numeric.has(key)?(e.target.value===""?null:Number(e.target.value)):e.target.value;change();}};
      let control;
      if(type==="flat_rate") { control=el("select",attrs,[["","Unknown"],["1","Yes — flat subscription"],["0","No — metered"]].map(([value,label])=>el("option",{value,selected:value===String(m[key]??"")},label))); }
      else if(type==="select") { control=el("select",attrs,[['','Choose a response'],['used','Used for work'],['opened_not_used','Opened but not used'],['accidental','Accidentally accessed']].map(([value,label])=>el("option",{value,selected:value===m[key]},label))); }
      else if(type==="textarea")control=el("textarea",{...attrs,rows:3,maxlength:8000},m[key]||"");
      else control=el("input",{...attrs,type,value:m[key]??"",min:type==="number"?0:null,step:type==="number"?"any":null});
      return el("label",{class:"field",for:id},el("span",null,label+(required?" *":"")),control,help?el("span",{class:"muted small"},help):null);
    }
    function projects() {
      const list=el("div",{class:"hub-projects"});
      function draw(){list.replaceChildren(...m.projects.map((p,i)=>el("fieldset",{class:"hub-project"},el("legend",null,`Project ${i+1}`),
        ...[['name','Project name'],['description','Work / deliverable'],['traditional','Traditional approach'],['ai_way','AI-assisted approach'],['benefit','Benefit'],['link','Supporting HTTP(S) link']].map(([key,label])=>{const id=`project-${report.id}-${i}-${key}`;return el("label",{class:"field",for:id},el("span",null,label),el("input",{id,class:"input",type:key==="link"?"url":"text",value:p[key]||"",oninput:e=>{p[key]=e.target.value;change();}}));}),
        el("button",{class:"btn btn--quiet btn--small",type:"button",onclick:()=>{m.projects.splice(i,1);change();draw();}},"Remove project"))));}
      draw();return el("div",null,list,el("button",{class:"btn btn--small",type:"button",onclick:()=>{m.projects.push({name:"",link:"",description:""});change();draw();}},"Add supporting project"));
    }
    async function persist(submit=false){
      err.textContent="";root.querySelectorAll("button").forEach(b=>b.disabled=true);
      try{const body={};["usage_confirmation","reason","impact","deliverables","quality","challenges","issues","next_steps","revenue_description","currency","usage_unit","pricing_source","selected_plan",...numeric].forEach(k=>body[k]=m[k]??(numeric.has(k)?null:""));body.currency=body.currency||"USD";body.projects=m.projects;body.version=m.version;
        const out=await api(submit?"POST":"PUT",`/hub/reports/${report.id}`+(submit?"/submit":""),body);
        Object.assign(m,out);c.dirty=false;onDirty?.(()=>false);saved.textContent=submit?"Submitted":"Draft saved";
        if(submit){caches.delete(report.id);active=null;toast(report.kind==="weekly"?"Report submitted. Its reporting requirement is cleared.":"Adoption report submitted.");await onDone(out);}return true;
      }catch(e){err.textContent=e.message;return false;}finally{root.querySelectorAll("button").forEach(b=>b.disabled=false);}
    }
    function render(){
      let content;
      if(step===0)content=[evidence(m.evidence),field("usage_confirmation","Did you use this tool?",{type:"select",required:true}),el("p",{class:"muted small"},"Only confirm work you actually did. Opening a site alone is access-level evidence.")];
      if(step===1)content=[field("reason",m.usage_confirmation==="used"?"Business problem and purpose":"Why was the tool opened without being used?",{required:true}),m.usage_confirmation==="used"?projects():null];
      if(step===2)content=m.usage_confirmation==="used"?[field("deliverables","Deliverables / results"),field("quality","Quality and productivity"),field("impact","Business impact",{help:"Describe value honestly; it remains a staff declaration."})]:[el("p",{class:"muted"},"Business results are not required when the tool was not used.")];
      if(step===3)content=m.usage_confirmation==="used"?[el("p",{class:"muted small"},"Optional defensible estimates. Leave unknown values blank; zero means a known zero. Hours mean working time. Currency: "+m.currency),
        el("div",{class:"hub-form-grid"},field("manual_hours","Manual work hours",{type:"number"}),field("ai_hours","AI-assisted work hours",{type:"number"}),field("manual_cost","Traditional cost",{type:"number"}),field("ai_cost","AI-assisted cost",{type:"number"}),field("subscription_cost","Subscription cost",{type:"number"}),field("extra_credits","Additional credits",{type:"number"}),field("other_expenses","Other expenses",{type:"number"})),
        el("details",{open:m.revenue!==null},el("summary",null,"Revenue contribution, if meaningful"),field("revenue","Estimated revenue contribution",{type:"number"}),field("revenue_description","How it contributed")),
        el("details",null,el("summary",null,"Currency and metered usage, if relevant"),field("currency","Currency code",{type:"text"}),field("frequency","Occurrences per reporting period",{type:"number"}),field("usage_amount","Declared metered quantity",{type:"number"}),field("usage_unit","Metered unit",{type:"text"}),field("selected_plan","Declared plan",{type:"text"}),field("usage_included","Included usage quantity",{type:"number"}),field("usage_unit_cost_usd","Declared unit price (USD)",{type:"number"}),field("usage_cost_usd","Declared usage allocation (USD)",{type:"number"}),field("usage_flat_rate","Flat subscription pricing",{type:"flat_rate"}),field("pricing_source","Pricing explanation")),el("details",null,el("summary",null,"Optional comparable activity counts"),el("p",{class:"muted small"},"Counts can be compared with recorded events. Time saved cannot be proven by request counts."),field("claimed_requests","API requests you recall",{type:"number"}),field("claimed_access_events","Website access events you recall",{type:"number"}),field("claimed_days","Days used (0–7)",{type:"number"}))]:[el("p",{class:"muted"},"Time, costs and revenue are not required for tools you did not use.")];
      if(step===4)content=[field("challenges","Limitations / challenges"),field("issues","Privacy or quality concerns"),field("next_steps","Lessons and likely use next week")];
      if(step===5)content=[declaration(m),el("p",{class:"notice"},"Review your declaration before submitting. Your original submission and later correction versions are preserved. Submitting clears this report's requirement without waiting for admin confirmation.")];
      const go=async n=>{if((step===0&&!m.usage_confirmation)||(step===1&&!m.reason?.trim())){err.textContent="Complete the required field before continuing.";return;}if(await persist()){step=n;const p=new URLSearchParams(location.hash.split("?")[1]||"");p.set("step",String(step));window.history.pushState(null,"",location.hash.split("?")[0]+"?"+p);render();root.querySelector("h2").focus();}};
      root.replaceChildren(el("header",{class:"hub-wizard-head"},el("div",null,el("p",{class:"eyebrow"},`Step ${step+1} of 6 · ${report.tool_name}`),el("h2",{tabindex:"-1"},steps[step])),status(report.state)),
        el("ol",{class:"hub-stepper","aria-label":"Reporting progress"},steps.map((label,i)=>el("li",{"aria-current":i===step?"step":null,class:i===step?"on":null},el("span",null,String(i+1)),el("span",null,label)))),
        el("div",{class:"hub-step-body"},content),err,el("footer",{class:"hub-wizard-foot"},saved,el("div",{class:"hub-actions"},
          el("button",{class:"btn",type:"button",onclick:()=>persist()},"Save draft"),step?el("button",{class:"btn",type:"button",onclick:()=>go(step-1)},"Back"):null,
          step<5?el("button",{class:"btn btn--solid",type:"button",onclick:()=>go(step+1)},"Continue"):el("button",{class:"btn btn--solid",type:"button",onclick:()=>persist(true)},"Submit report"))));
    }
    render();return root;
  }
  function procurementForm(api,onDone) {
    const form=el("form",{class:"hub-procurement-form"});const data=purchaseDraft;const err=el("p",{class:"form-error",role:"alert"});
    function input(key,label,type="text",required=false){const id="purchase-"+key;let c;
      if(key==="purchase_type"){c=el("select",{id,class:"input",required:true,onchange:e=>{data[key]=e.target.value;purchaseDirty=true;}},el("option",{value:""},"Choose a purchase type"),...['new_tool','subscription','licence','credits','other'].map(v=>el("option",{value:v},stateLabel(v))));if(data[key])c.value=data[key];}
      else c=el(type==="textarea"?"textarea":"input",{id,class:"input",type:type==="textarea"?null:type,value:data[key]??"",rows:type==="textarea"?3:null,required,min:type==="number"?0:null,step:type==="number"?"any":null,oninput:e=>{purchaseDirty=true;data[key]=type==="number"?(e.target.value===""?null:Number(e.target.value)):e.target.value;}});
      return el("label",{class:"field",for:id},el("span",null,label+(required?" *":"")),c);}
    const send=el("button",{class:"btn btn--solid",type:"submit"},"Submit procurement request");
    form.append(el("p",{class:"muted"},"Propose a purchase. Approval does not grant access; security, subscription and entitlement checks are separate."),
      el("div",{class:"hub-form-grid"},input("tool_name","Tool name","text",true),input("purchase_type","Purchase type"),input("official_url","Official URL","url"),input("requested_plan","Plan / licence")),
      input("reason","Business reason","textarea",true),input("business_impact","Expected business value","textarea"),
      el("details",null,el("summary",null,"Estimated costs (USD), if known"),el("div",{class:"hub-form-grid"},input("estimated_monthly_cost","Monthly estimate","number"),input("estimated_one_time_cost","One-time estimate","number"))),err,send);
    form.addEventListener("submit",async e=>{e.preventDefault();err.textContent="";send.disabled=true;try{await api("POST","/hub/procurement",data);purchaseDraft={};purchaseDirty=false;toast("Procurement request submitted.");onDone();}catch(x){err.textContent=x.message;}finally{send.disabled=false;}});
    return form;
  }
  window.HubUI={evidence,declaration,history,reportRows,wizard,procurementForm,status,stateLabel,fact,guard,dirty,text};
})();
