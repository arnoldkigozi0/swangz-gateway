"use strict";
/* Installation retains browser OAuth and server authorisation; no offline private-record store. */
(() => {
 if('serviceWorker' in navigator&&isSecureContext)navigator.serviceWorker.register('/hub-worker.js').catch(()=>{});
 // Staff sign-in form, or the signed-in top bar. The console links the same manifest but installs the staff app, so it gets no button.
 const TARGETS='.gate-form form,.topbar .top-right';
 let promptEvent=null,observer=null;
 const stop=()=>{promptEvent=null;observer?.disconnect();observer=null;document.querySelector('.hub-install-action')?.remove();};
 const button=()=>SUI.el('button',{type:'button',class:'btn btn--small hub-install-action','aria-label':'Install app: Swangz AI Hub',onclick:async()=>{
   const e=promptEvent;if(!e)return;promptEvent=null;
   try{await e.prompt();const choice=await e.userChoice;if(choice.outcome==='accepted'){stop();return;}}catch(err){/* prompt can be used once */}
   document.querySelector('.hub-install-action')?.remove();observer?.disconnect();observer=null; // dismissed: the browser offers it again later
 }},'Install app');
 // The app renders after /me answers and re-renders on sign-in/out, so place the button whenever a target appears.
 const place=()=>{if(!promptEvent||document.querySelector('.hub-install-action'))return;const target=document.querySelector(TARGETS);if(!target)return;const b=button();if(target.classList.contains('top-right'))target.prepend(b);else target.append(b);};
 addEventListener('beforeinstallprompt',e=>{e.preventDefault();promptEvent=e;place();
   if(!observer&&typeof MutationObserver==='function'){observer=new MutationObserver(place);observer.observe(document.body,{childList:true,subtree:true});}
 });
 addEventListener('appinstalled',stop);
})();
