"use strict";
/* Installation retains browser OAuth and server authorisation; no offline private-record store. */
(() => {
 if('serviceWorker' in navigator&&isSecureContext)navigator.serviceWorker.register('/hub-worker.js').catch(()=>{});
 let promptEvent;
 addEventListener('beforeinstallprompt',e=>{e.preventDefault();promptEvent=e;
   const button=SUI.el('button',{type:'button',class:'btn hub-install-action','aria-label':'Install Swangz AI Hub',onclick:async()=>{if(!promptEvent)return;await promptEvent.prompt();const choice=await promptEvent.userChoice;if(choice.outcome==='accepted')button.remove();promptEvent=null;}},'Install Swangz AI Hub');
   const target=document.querySelector('.login-card,.auth-card,.topbar .inner');if(target&&!document.querySelector('.hub-install-action'))target.append(button);
 });
 addEventListener('appinstalled',()=>document.querySelector('.hub-install-action')?.remove());
})();
