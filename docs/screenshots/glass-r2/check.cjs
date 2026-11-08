/* Synthetic gateway fixture and existing pinned Chromium/axe; no runtime dependencies. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const root = path.resolve(__dirname, '../../..');
const tooling = process.env.UI_TOOLING || path.join(root, 'tests/browser/node_modules');
const {chromium} = require(path.join(tooling, 'playwright'));
const {AxeBuilder} = require(path.join(tooling, '@axe-core/playwright'));
const out = __dirname;
let fixture, browser;
const result = {checks:[],screenshots:[],errors:[],accessibility:[]};
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
 for(const theme of ['dark','light']){
  await p.setViewportSize({width:1440,height:900});await p.goto(url+'/admin#/');await loaded(p);
  await p.evaluate(t=>{document.documentElement.dataset.theme=t;localStorage.setItem('swangz-theme',t);},theme);await p.waitForTimeout(600);
  const rail=p.locator('.shell > .side');
  check(theme+' icon-first default',await rail.evaluate(e=>e.classList.contains('compact')));
  check(theme+' floating rail inset',await rail.evaluate(e=>{const r=e.getBoundingClientRect();return r.x===16&&r.y===16&&r.bottom===innerHeight-16&&r.width===76;}));
  check(theme+' existing five groups preserved',await rail.locator('.nav-group').count()===5);
  check(theme+' every main destination present',await rail.locator('nav a').count()===21);
  check(theme+' white active circle',await rail.locator('a.on').evaluate(e=>{const s=getComputedStyle(e);return s.backgroundColor==='rgb(255, 255, 255)'&&s.borderRadius==='999px';}));
  check(theme+' no page overflow',await p.evaluate(()=>document.documentElement.scrollWidth===innerWidth));
  await shot(p,'admin-1440-'+theme);await audit(p,theme+' desktop','.shell > .side');
  const first=rail.locator('.nav:not(.rail-foot) a').first();await first.focus();
  await p.waitForFunction(()=>document.querySelector('.u-tip.in')?.textContent==='Overview · Monitor');
  check(theme+' keyboard tooltip names destination',await p.locator('.u-tip.in').innerText()==='Overview · Monitor');
  await p.keyboard.press('ArrowDown');check(theme+' ArrowDown focuses Live',await p.evaluate(()=>document.activeElement.getAttribute('href')==='#/live'));
  check(theme+' focus ring',await p.evaluate(()=>getComputedStyle(document.activeElement).outlineWidth==='2px'));
  await p.keyboard.press('End');check(theme+' End reaches Audit log',await p.evaluate(()=>document.activeElement.getAttribute('href')==='#/audit'));
  await p.keyboard.press('Home');check(theme+' Home returns Overview',await p.evaluate(()=>document.activeElement.getAttribute('href')==='#/'));
  await p.keyboard.press('Escape');check(theme+' Escape dismisses tooltip',await p.locator('.u-tip.in').count()===0);
  await rail.getByRole('button',{name:'Show navigation labels',exact:true}).click();
  check(theme+' expand retains focus',await p.evaluate(()=>document.activeElement.getAttribute('aria-label')==='Hide navigation labels'));
  check(theme+' labels shown',await p.locator('.side.expanded .nl').first().isVisible());
  await p.reload();await loaded(p);check(theme+' labelled preference survives reload',await p.locator('.shell > .side.expanded').count()===1);
  const govern=p.locator('.side .group-toggle').filter({hasText:'Govern'});if(await govern.getAttribute('aria-expanded')==='false')await govern.click();
  await p.locator('.side .nav a[href="#/tools"]').click();await loaded(p);
  check(theme+' active group stays visible',await p.locator('.side .nav-group.here .nav-links').isVisible());
  await shot(p,'expanded-1440-'+theme);
  await p.locator('.side .rail-toggle').click();
  await p.reload();await loaded(p);check(theme+' compact preference survives reload',await p.locator('.shell > .side.compact').count()===1);
  await p.setViewportSize({width:390,height:844});await p.goto(url+'/admin#/');await loaded(p);
  check(theme+' desktop rail hidden on phone',!await p.locator('.shell > .side').isVisible());
  check(theme+' five shortcuts and More',await p.locator('.rail-mobile > *').count()===6);
  check(theme+' mobile targets at least 44px',await p.locator('.rail-mobile > *').evaluateAll(es=>es.every(e=>{const r=e.getBoundingClientRect();return r.width>=44&&r.height>=44;})));
  check(theme+' quick bar fits viewport',await p.locator('.rail-mobile').evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight;}));
  check(theme+' mobile no horizontal overflow',await p.evaluate(()=>document.documentElement.scrollWidth===innerWidth));
  await shot(p,'admin-390-'+theme);await audit(p,theme+' phone','.rail-mobile');
  await p.getByRole('button',{name:'More navigation',exact:true}).click();
  await p.locator('.side.drawer.in').waitFor();await p.waitForTimeout(400);
  check(theme+' More opens labelled drawer',await p.locator('.side.drawer.expanded').count()===1);
  check(theme+' drawer focus starts at close',await p.evaluate(()=>document.activeElement.getAttribute('aria-label')==='Close navigation'));
  check(theme+' unique navigation control IDs',await p.evaluate(()=>{const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);return ids.length===new Set(ids).size;}));
  check(theme+' quick bar hidden beneath drawer',!await p.locator('.rail-mobile').isVisible());
  await p.keyboard.press('Shift+Tab');check(theme+' drawer traps reverse Tab',await p.evaluate(()=>document.activeElement.closest('.drawer')!==null));
  await audit(p,theme+' drawer','.side.drawer');await shot(p,'drawer-390-'+theme);
  await p.keyboard.press('Escape');await p.locator('.side.drawer').waitFor({state:'detached'});
  check(theme+' Escape returns focus to More',await p.evaluate(()=>document.activeElement.getAttribute('aria-label')==='More navigation'));
  await p.getByRole('button',{name:'More navigation',exact:true}).click();await p.locator('.side.drawer.in').waitFor();
  const reporting=p.locator('.drawer .group-toggle').filter({hasText:'Reporting'});if(await reporting.getAttribute('aria-expanded')==='false')await reporting.click();
  await p.locator('.drawer .nav a[href="#/business"]').click();await loaded(p);await p.locator('.side.drawer').waitFor({state:'detached'});
  check(theme+' More reaches long-label destination',await p.locator('main h1').innerText()==='Business value');
  check(theme+' More marks non-shortcut page',await p.locator('.rail-mobile button.on').count()===1);
  await p.getByRole('link',{name:'Overview',exact:true}).click();await loaded(p);
  check(theme+' quick link navigates',await p.locator('main h1').innerText()==='Overview');
  await p.goBack();await loaded(p);check(theme+' Back restores previous page',await p.locator('main h1').innerText()==='Business value');
  await p.goto(url+'/admin#/');await loaded(p);
 }
 await p.setViewportSize({width:1440,height:900});await p.reload();await loaded(p);
 await p.emulateMedia({reducedMotion:'reduce'});await p.setViewportSize({width:390,height:844});await p.getByRole('button',{name:'More navigation',exact:true}).click();await p.locator('.side.drawer.in').waitFor();
 check('reduced motion removes drawer transition',await p.locator('.side.drawer').evaluate(e=>getComputedStyle(e).transitionProperty==='none'));
 await p.keyboard.press('Escape');await p.locator('.side.drawer').waitFor({state:'detached'});
 const cdp=await c.newCDPSession(p);await cdp.send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-transparency',value:'reduce'}]});
 await p.waitForTimeout(700);
 result.transparency=await p.locator('.rail-mobile').evaluate(e=>({blur:getComputedStyle(e).backdropFilter,bg:getComputedStyle(e).backgroundColor,matches:matchMedia('(prefers-reduced-transparency: reduce)').matches}));
 check('reduced transparency solid quick bar',await p.locator('.rail-mobile').evaluate(e=>getComputedStyle(e).backdropFilter==='none'&&!getComputedStyle(e).backgroundColor.startsWith('rgba')));
 await cdp.send('Emulation.setEmulatedMedia',{features:[]});
 await p.emulateMedia({media:'print'});check('navigation omitted from print',!await p.locator('.rail-mobile').isVisible());await p.emulateMedia({media:'screen'});
 check('no browser exceptions',result.errors.length===0);
 console.log(`PASS ${result.checks.length} navigation checks; ${result.screenshots.length} screenshots; ${result.accessibility.length} axe scans`);
})().catch(e=>{result.failure=e.stack;console.error(e);process.exitCode=1;}).finally(async()=>{fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2)+'\n');await browser?.close();fixture?.kill('SIGTERM');});
