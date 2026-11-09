/* Synthetic gateway fixture and existing pinned Chromium/axe; no runtime dependencies. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const root = path.resolve(__dirname, '../../..');
const tooling = process.env.UI_TOOLING || path.join(root, 'tests/browser/node_modules');
const {chromium} = require(path.join(tooling, 'playwright'));
const {AxeBuilder} = require(path.join(tooling, '@axe-core/playwright'));
const out = process.env.UI_OUTPUT || __dirname;
fs.mkdirSync(out, {recursive:true});
let fixture, browser;
const result = {checks:[],screenshots:[],errors:[],accessibility:[],badgeContrast:[]};
const check = (name,ok) => {assert.ok(ok,name);result.checks.push(name);};
async function start(){
 fixture=spawn('python3',['tests/browser/demo.py'],{cwd:root,stdio:['ignore','pipe','pipe']});
 return new Promise((resolve,reject)=>{let output='',err='';const timer=setTimeout(()=>reject(Error('Fixture timeout '+err)),30000);fixture.stderr.on('data',d=>err+=d);fixture.stdout.on('data',d=>{output+=d;if(output.includes('\n')){clearTimeout(timer);resolve(JSON.parse(output.split('\n')[0]));}});fixture.on('exit',c=>{clearTimeout(timer);if(c)reject(Error(err));});});
}
async function loaded(p){await p.locator('main h1').waitFor();await p.waitForFunction(()=>window.SWA?.S.route===location.hash&&document.querySelector('main h1')?.textContent);await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(700);}
async function shot(p,name){await p.mouse.move(1400,8);await p.evaluate(()=>SUI.hideTip());await p.screenshot({path:path.join(out,name+'.png'),animations:'disabled'});result.screenshots.push(name+'.png');}
async function audit(p,name,include){const scan=await new AxeBuilder({page:p}).include(include).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();result.accessibility.push({name,violations:scan.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}))});check(name+' axe navigation',scan.violations.length===0);}
(async()=>{
 const {url}=await start();browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const c=await browser.newContext();
 check('synthetic owner login',(await c.request.post(url+'/admin/api/login',{headers:{'x-gateway-admin':'1'},data:{username:'owner@swangzavenue.com',password:'owner-password'}})).status()===200);
 const p=await c.newPage();p.on('pageerror',e=>result.errors.push(e.message));

 for(const theme of ['dark','light'])for(const[width,height]of[[1440,900],[390,844]]){
  await p.setViewportSize({width,height});await p.goto(url+'/admin#/');await loaded(p);await p.evaluate(t=>{document.documentElement.dataset.theme=t;localStorage.setItem('swangz-theme',t)},theme);await p.waitForTimeout(650);
  const bar=p.locator('.console-bar');
  check(theme+width+' toolbar visible',await bar.isVisible());
  check(theme+width+' no overflow',await p.evaluate(()=>document.documentElement.scrollWidth===innerWidth));
  check(theme+width+' all toolbar controls fit',await bar.locator('a,button,time').evaluateAll(es=>es.every(e=>{const r=e.getBoundingClientRect();return r.width>=44&&r.height>=44&&r.left>=0&&r.right<=innerWidth;})));
  check(theme+width+' real clock and timezone',await bar.locator('time').evaluate(e=>!Number.isNaN(Date.parse(e.dateTime))&&Math.abs(Date.now()-Date.parse(e.dateTime))<30000&&e.getAttribute('aria-label').includes(SUI.tzLabel())&&e.textContent===SUI.fmt.clock(Date.parse(e.dateTime)/1000)));
  check(theme+width+' real account name',await bar.locator('.console-account').getAttribute('aria-label')==='Your account: owner@swangzavenue.com');
  const badge = await bar.locator('.bell-n').evaluate(e => {
    const style = getComputedStyle(e);
    return {foreground:style.color, background:style.backgroundColor, opacity:style.opacity};
  });
  const luminance = color => color.match(/[\d.]+/g).slice(0,3).map(Number)
    .map(v => v/255).map(v => v <= .04045 ? v/12.92 : ((v+.055)/1.055)**2.4)
    .reduce((sum,v,i) => sum+v*[.2126,.7152,.0722][i],0);
  const [lo,hi] = [luminance(badge.foreground),luminance(badge.background)].sort((a,b)=>a-b);
  const ratio = (hi+.05)/(lo+.05);
  result.badgeContrast.push({theme,width,...badge,ratio});
  check(theme+width+' notification badge text >=4.5:1 ('+ratio.toFixed(6)+')',ratio>=4.5 && badge.opacity==='1');
  check(theme+width+' no fake presence',await bar.locator('[data-presence]').count()===0);
  await audit(p,theme+width+' toolbar','.console-bar');await shot(p,'admin-'+width+'-'+theme);
  await bar.getByRole('button',{name:'Search',exact:true}).focus();await p.keyboard.press('Enter');await p.getByRole('dialog',{name:'Command menu'}).waitFor();check(theme+width+' keyboard opens existing command search',await p.getByRole('dialog',{name:'Command menu'}).isVisible());await p.keyboard.press('Escape');
  check(theme+width+' command search restores focus',await p.evaluate(()=>document.activeElement.classList.contains('console-search')));
  check(theme+width+' visible focus ring',await bar.locator('.console-search').evaluate(e=>getComputedStyle(e).outlineWidth==='2px'));
  await bar.getByRole('button',{name:'Open navigation',exact:true}).click();await p.locator('.drawer.in').waitFor();check(theme+width+' workspace opens existing navigation',await p.locator('.drawer .rail-groups button').count()===5);await p.keyboard.press('Escape');await p.locator('.drawer').waitFor({state:'detached'});
  await bar.locator('.bell').click();await p.getByRole('dialog',{name:'Notifications',exact:true}).waitFor();check(theme+width+' bell opens real notification sheet',await p.getByRole('dialog',{name:'Notifications',exact:true}).isVisible());await p.keyboard.press('Escape');await p.getByRole('dialog',{name:'Notifications',exact:true}).waitFor({state:'detached'});
  await bar.locator('.console-account').click();await p.getByRole('heading',{name:'Your account',exact:true}).waitFor();check(theme+width+' avatar opens account page',p.url().includes('tab=account'));await p.goto(url+'/admin#/');await loaded(p);
 }
 await p.setViewportSize({width:1440,height:900});await p.goto(url+'/admin#/');await loaded(p);
 await p.evaluate(()=>SUI.setTzMode('utc'));await loaded(p);check('clock follows selected UTC mode',(await p.locator('.console-clock').getAttribute('aria-label')).endsWith('UTC'));
 const stamp=await p.locator('.console-clock').getAttribute('datetime');await p.waitForTimeout(16500);check('clock advances while page stays open',await p.locator('.console-clock').getAttribute('datetime')!==stamp);
 await p.evaluate(()=>SUI.setTzMode('gateway'));await loaded(p);
 for(const width of [320,768,1280]){await p.setViewportSize({width,height:844});check(width+' toolbar fits additional width',await p.locator('.console-bar a,.console-bar button,.console-bar time').evaluateAll(es=>es.every(e=>{const r=e.getBoundingClientRect();return r.width>=44&&r.left>=0&&r.right<=innerWidth;})));}
 const viewer=await browser.newContext();check('synthetic viewer login',(await viewer.request.post(url+'/admin/api/login',{headers:{'x-gateway-admin':'1'},data:{username:'viewer@swangzavenue.com',password:'viewer-password'}})).status()===200);
 const vp=await viewer.newPage();await vp.goto(url+'/admin#/');await loaded(vp);check('viewer header uses own identity',(await vp.locator('.console-account').getAttribute('aria-label')).includes('viewer@swangzavenue.com'));await viewer.close();
 await p.emulateMedia({reducedMotion:'reduce'});await p.setViewportSize({width:1440,height:900});check('toolbar uses no animation or blur',await p.locator('.console-bar').evaluate(e=>getComputedStyle(e).backdropFilter==='none'&&getComputedStyle(e).animationName==='none'));
 await p.emulateMedia({media:'print'});check('toolbar excluded from print',!await p.locator('.console-bar').isVisible());await p.emulateMedia({media:'screen'});
 check('no browser exceptions',result.errors.length===0);
 console.log(`PASS ${result.checks.length} header checks; ${result.screenshots.length} screenshots; ${result.accessibility.length} axe scans`);
})().catch(e=>{result.failure=e.stack;console.error(e);process.exitCode=1;}).finally(async()=>{fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2)+'\n');await browser?.close();fixture?.kill('SIGTERM');});
