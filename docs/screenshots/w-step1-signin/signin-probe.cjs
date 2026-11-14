const { chromium } = require('playwright');const fs=require('fs');
const out='/dev/shm/probe-t/shots';const log=[];
const L=(...a)=>{const s=a.join(' ');console.log(s);log.push(s)};
(async()=>{
const dir='/dev/shm/probe-t/signin-prof-'+Date.now();
const ctx=await chromium.launchPersistentContext(dir,{channel:'chrome',headless:false,ignoreDefaultArgs:['--enable-automation'],args:['--no-first-run','--no-default-browser-check'],viewport:{width:1280,height:800}});
const chain=[];
const FR=new Set();const watch=(p)=>{p.on('framenavigated',f=>{if(f.url().startsWith('http'))FR.add((f===p.mainFrame()?'main ':'frame ')+new URL(f.url()).origin);if(f===p.mainFrame())chain.push(f.url())});};
ctx.on('page',watch);
async function flow(name,url,pre,btn){
 chain.length=0;const reqs=[];const p=await ctx.newPage();watch(p);
 ctx.on('request',r=>{if(r.isNavigationRequest())reqs.push(r.url())});
 try{await p.goto(url,{waitUntil:'domcontentloaded',timeout:45000})}catch(e){L(name,'goto error',e.message.slice(0,90))}
 await p.waitForTimeout(4000);
 for(const pr of pre){const l=p.getByRole('button',{name:pr}).or(p.getByRole('link',{name:pr})).or(p.getByText(pr)).first();if(await l.count()){await l.click({timeout:8000}).catch(()=>{});await p.waitForTimeout(3000)}else L(name,'pre-click element missing',String(pr))}
 const l=p.getByRole('button',{name:btn}).or(p.getByRole('link',{name:btn})).or(p.getByText(btn)).first();
 if(!(await l.count())){L(name,'BUTTON NOT OFFERED:',String(btn));await p.screenshot({path:`${out}/${name}-notoffered.png`});await p.close();return}
 reqs.length=0;chain.length=0;const before=ctx.pages().length;
 await l.click({timeout:8000}).catch(e=>L(name,'click failed',e.message.slice(0,80)));
 await p.waitForTimeout(7000);
 const pages=ctx.pages();const tgt=pages[pages.length-1];
 L(name,'-> url:',tgt.url().slice(0,150),'| opened in new window/tab:',pages.length>before,'| title:',(await tgt.title()).slice(0,50));
 L(name,'   navigation requests:',JSON.stringify([...new Set(reqs)].map(u=>u.split('?')[0].slice(0,100))));
 const pw=await tgt.locator('input[type=password]:visible').count(), em=await tgt.locator('input[type=email]:visible,input[name=identifier]:visible,input[name=loginfmt]:visible,input[type=text]:visible').count();
 L(name,'   visible email/id fields:',em,'| password fields:',pw,'(nothing typed anywhere)');
 await tgt.screenshot({path:`${out}/${name}.png`});
 for(const pg of ctx.pages().slice(1))await pg.close().catch(()=>{});
}
await flow('chatgpt-google','https://chatgpt.com/',[/^Log in$/],/Continue with Google/);
await flow('chatgpt-apple','https://chatgpt.com/',[/^Log in$/],/Continue with Apple/);
await flow('claude-google','https://claude.ai/login',[],/Continue with Google/);
await flow('gemini-signin','https://gemini.google.com/',[],/^Sign in$/);
await flow('claude-google','https://claude.ai/login',[],/Continue with Google/);
L('ALL FRAME ORIGINS SEEN:',JSON.stringify([...FR].sort()));await ctx.close();
fs.writeFileSync('/dev/shm/probe-t/signin.log',log.join('\n'));
})();
