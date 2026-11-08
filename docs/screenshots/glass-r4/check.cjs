const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const root = process.env.GLASS_ROOT || path.resolve(__dirname, '../../..');
const {chromium} = require(path.join(process.env.UI_TOOLING || path.join(root,'tests/browser/node_modules'), 'playwright'));
const {AxeBuilder} = require(path.join(process.env.UI_TOOLING || path.join(root,'tests/browser/node_modules'), '@axe-core/playwright'));
const out = path.join(root, 'docs/screenshots/glass-r4');
fs.mkdirSync(out, {recursive:true});
let fixture, browser;
const result = {checks:[], errors:[], screenshots:[], contrast:[], accessibility:[], layouts:[], tabBounds:[]};
function check(name, ok) {assert.ok(ok,name); result.checks.push(name);}
async function start() {
 fixture=spawn('python3',['tests/browser/demo.py'],{cwd:root,stdio:['ignore','pipe','pipe']});
 return await new Promise((resolve,reject)=>{let output='',err=''; const timer=setTimeout(()=>reject(Error('Fixture timeout '+err)),30000);fixture.stderr.on('data',d=>err+=d);fixture.stdout.on('data',d=>{output+=d;if(output.includes('\n')){clearTimeout(timer);resolve(JSON.parse(output.split('\n')[0]));}});fixture.on('exit',c=>{clearTimeout(timer);if(c)reject(Error(err));});});
}
(async()=>{
 const {url}=await start();
 browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const context=await browser.newContext();
 check('synthetic owner login', (await context.request.post(url+'/admin/api/login',{headers:{'x-gateway-admin':'1'},data:{username:'owner@swangzavenue.com',password:'owner-password'}})).status()===200);
 const p=await context.newPage();p.on('pageerror',e=>result.errors.push(e.message));
 for(const theme of ['dark','light'])for(const [width,height]of [[1440,900],[390,844]]){
  await p.setViewportSize({width,height});await p.goto(url+'/admin#/');await p.locator('main h1').waitFor();
  await p.waitForFunction(()=>!document.querySelector('main .u-skel-rows, main .u-skel-cards'));
  await p.evaluate(t=>{document.documentElement.dataset.theme=t;localStorage.setItem('swangz-theme',t)},theme);
  await p.evaluate(()=>document.fonts.ready);
  await p.waitForTimeout(600); // Allow the existing theme transitions to settle.
  const metrics=await p.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,scene:getComputedStyle(document.body,'::before').backgroundImage,font:getComputedStyle(document.body).fontFamily,numbers:getComputedStyle(document.body).fontVariantNumeric}));
  check(theme+width+' real app: no overflow',!metrics.overflow);check(theme+width+' fixed scene loads',metrics.scene.includes('admin-welcome.webp'));check(theme+width+' tabular figures',metrics.numbers.includes('tabular-nums'));
  check(theme+width+' Jakarta variable face loaded',metrics.font.includes('Plus Jakarta Sans')&&await p.evaluate(()=>document.fonts.check('650 16px "Plus Jakarta Sans"')));
  check(theme+width+' KPI values fit font metrics',await p.locator('.kpi .value:not(.text)').evaluateAll(es=>es.length>0&&es.every(e=>e.scrollHeight<=e.clientHeight+1&&e.scrollWidth<=e.clientWidth+1)));
  check(theme+width+' four real KPI values',await p.locator('.u-overview-kpis .kpi').count()===4);
  check(theme+width+' values fit',await p.locator('.u-overview-kpis .value').evaluateAll(es=>es.every(e=>e.scrollWidth<=e.clientWidth+1&&e.scrollHeight<=e.clientHeight+1)));
  check(theme+width+' four columns or phone two',await p.locator('.u-overview-kpis').evaluate((e,w)=>getComputedStyle(e).gridTemplateColumns.split(' ').length===(w===1440?4:2),width));
  const cards = await p.locator('.u-overview-kpis .kpi').evaluateAll(es => es.map(card => {
    const bounds = card.getBoundingClientRect();
    return {text:card.innerText, width:bounds.width, height:bounds.height,
      content:[...card.querySelectorAll('.label,.value,.foot,.kpi-note')].map(e => {
        const r=e.getBoundingClientRect();return {text:e.textContent.trim(),
          fits:e.scrollWidth<=e.clientWidth+1 && e.scrollHeight<=e.clientHeight+1 &&
            r.left>=bounds.left-1 && r.right<=bounds.right+1 && r.bottom<=bounds.bottom+1};
      })};
  }));
  result.layouts.push({theme,width,cards});
  check(theme+width+' KPI labels/values/context stay inside cards',cards.length===4 && cards.every(c=>c.content.every(e=>e.fits)));
  const violations=(await new AxeBuilder({page:p}).include('main').withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations;result.accessibility.push({theme,width,violations:violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}))});check(theme+width+' main axe',violations.length===0);
  await p.evaluate(()=>{document.activeElement?.blur();SUI.hideTip();});
  const file=`admin-${width}-${theme}.png`;await p.screenshot({path:path.join(out,file),animations:'disabled'});result.screenshots.push(file);
  if(width===390){
    const tabs=p.locator('main .ptabs').first();
    const buttons=tabs.getByRole('tab');check(theme+' phone four overview tabs',await buttons.count()===4);
    await buttons.first().evaluate(e=>e.focus());
    for(let i=0;i<await buttons.count();i++){
      const button=buttons.nth(i);if(i>0)await p.keyboard.press('ArrowRight');
      await p.waitForFunction(i=>document.querySelectorAll('main .ptabs [role=tab]')[i]?.getAttribute('aria-selected')==='true',i);
      await p.waitForTimeout(120);
      const bounds=await button.evaluate(e=>{const r=e.getBoundingClientRect(),p=e.parentElement.getBoundingClientRect();const nav=document.querySelector('.rail-mobile')?.getBoundingClientRect();return {text:e.textContent.trim(),scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,left:r.left,right:r.right,top:r.top,bottom:r.bottom,parentLeft:p.left,parentRight:p.right,navTop:nav?.top,scrollLeft:e.parentElement.scrollLeft,barScrollWidth:e.parentElement.scrollWidth,barClientWidth:e.parentElement.clientWidth,mask:getComputedStyle(e.parentElement).maskImage,fits:e.scrollWidth<=e.clientWidth+1 && r.left>=p.left-1 && r.right<=p.right+1 && r.left>=0 && r.right<=innerWidth && r.top>=0 && r.bottom<=Math.min(innerHeight,nav?.top??innerHeight)};});
      result.tabBounds.push({theme,...bounds});
      if(!bounds.fits)await p.screenshot({path:path.join(out,'phone-tabs-before-fix.png'),animations:'disabled'});
      check(theme+' phone tab fully readable on focus: '+bounds.text,bounds.fits);
    }
    const file=`tabs-${width}-${theme}.png`;await p.screenshot({path:path.join(out,file),animations:'disabled'});result.screenshots.push(file);
  }
 }
 const tr=await (await context.request.get(url+'/admin/api/trends?days=30')).json();
 check('request KPI matches existing API',await p.locator('.kpi-link[href="#/activity?tab=ai&range=30d"]').getAttribute('aria-label')==='AI requests · 30 days: '+tr.current.requests);
 await p.setViewportSize({width:1440,height:900});await p.locator('.u-glass-kpi').first().hover();await p.waitForTimeout(350);
 check('hover lift uses transform',await p.locator('.u-glass-kpi').first().evaluate(e=>getComputedStyle(e).transform!=='none'));
 await p.emulateMedia({reducedMotion:'reduce'});check('reduced motion removes lift',await p.locator('.u-glass-kpi').first().evaluate(e=>getComputedStyle(e).transform==='none'));
 await p.emulateMedia({reducedMotion:'no-preference'});
 await p.route('**/admin/api/trends?days=30',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Synthetic unavailable summary'})}));
 await p.reload();await p.getByText("The summary couldn't load",{exact:true}).waitFor();check('summary failure renders honest error',await p.locator('.u-overview-kpis').count()===0);await p.unroute('**/admin/api/trends?days=30');
 await p.route('**/admin/api/trends?days=30',async route=>{const response=await route.fetch();const data=await response.json();data.current={...data.current,cost:0,requests:0,people:0};data.previous={...data.previous,cost:0,requests:0,people:0};data.days=data.days.map(d=>({...d,cost:0,requests:0,people:0}));await route.fulfill({response,json:data});});
 await p.reload();await p.locator('.u-overview-kpis').waitFor();check('zero activity remains zero',await p.locator('.u-overview-kpis .value').nth(2).innerText()==='0');check('no invented zero-baseline percentage',await p.locator('.u-overview-kpis .u-delta').nth(1).innerText()==='no earlier data');await p.unroute('**/admin/api/trends?days=30');
 check('no browser exceptions' ,result.errors.length===0);
 console.log('PASS '+result.checks.length+' focused checks; '+result.screenshots.length+' screenshots');
})().catch(e=>{result.failure=e.stack;console.error(e);process.exitCode=1}).finally(async()=>{fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2));await browser?.close();fixture?.kill('SIGTERM');});
