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

 await p.setViewportSize({width:1366,height:768});await p.goto(url+'/admin#/');await loaded(p);
 check('compact has explicit All pages entry',await p.getByRole('button',{name:'All pages and account controls'}).isVisible());
 check('compact has visible scroll cue',await p.getByRole('button',{name:'Scroll to more pages'}).isVisible());
 check('compact utilities are available through full navigator',!await p.locator('.shell > .side .who').isVisible());
 await p.evaluate(()=>{SWA.S.notes={...SWA.S.notes,items:[{key:'incident:synthetic-review',resolved:false}]};SWA.render();});await loaded(p);
 await shot(p,'alerts-1366');
 check('offscreen serious incident is summarised in compact rail',await p.locator('.rail-pages .count.bad').innerText()==='1');
 await p.getByRole('button',{name:'All pages and account controls'}).click();await p.locator('.drawer.in').waitFor();
 check('all five area shortcuts visible at 1366',await p.locator('.drawer .rail-groups button').evaluateAll(es=>es.length===5&&es.every(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight&&r.width>=44&&r.height>=44;})));
 for(const area of ['Monitor','Govern','Reporting','Money','Trust']){await p.getByRole('button',{name:'Show '+area+' pages',exact:true}).last().click();check(area+' reachable from pinned area index',await p.evaluate(()=>document.activeElement.closest('.nav-group').getAttribute('aria-label'))===area);}
 check('Trust summary retains red severity',await p.locator('.drawer .rail-groups button').last().locator('.count.bad').count()===1);
 await p.keyboard.press('Escape');await p.locator('.drawer').waitFor({state:'detached'});
 await p.getByRole('button',{name:'Show navigation labels'}).click();
 await p.locator('.shell > .side .group-toggle').filter({hasText:'Trust'}).focus();
 await p.waitForTimeout(16500);
 check('Trust toggle survives live count refresh',await p.evaluate(()=>document.activeElement.getAttribute('aria-controls'))==='nav-trust');
 await p.getByRole('button',{name:'Hide navigation labels'}).focus();await p.waitForTimeout(50);
 check('labels tooltip stays clear of brand',await p.locator('.u-tip.in').evaluate(e=>e.getBoundingClientRect().left>document.querySelector('.shell > .side').getBoundingClientRect().right));
 await p.getByRole('button',{name:'Hide navigation labels'}).click();
 await p.evaluate(()=>document.documentElement.dataset.theme='light');await p.waitForTimeout(700);
 const ring=await p.locator('.shell > .side a.on').evaluate(e=>({shadow:getComputedStyle(e).boxShadow,bg:getComputedStyle(e).backgroundColor}));result.selection=ring;
 check('light selection has dark state ring',ring.shadow.includes('rgb(33, 29, 25)')&&ring.bg==='rgb(255, 255, 255)');
 const channels=ring.shadow.match(/rgb\(([^)]+)\)/)[1].split(',').map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});
 result.selection.contrast=1.05/(channels.reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0)+.05);check('selection ring contrast at least 3:1',result.selection.contrast>=3);
 check('rail removes backdrop repaint cost',await p.locator('.shell > .side').evaluate(e=>getComputedStyle(e).backdropFilter==='none'));
 await p.setViewportSize({width:390,height:844});await p.getByRole('button',{name:'More navigation'}).click();await p.locator('.drawer.in').waitFor();
 check('phone Stop all AI is at least 44px tall',await p.locator('.drawer .estop button').evaluate(e=>e.getBoundingClientRect().height>=44));
 await p.locator('.drawer .estop button').click();await p.getByRole('dialog',{name:'Stop all AI for everyone?',exact:true}).waitFor();
 check('confirmation closes navigator before acting',await p.locator('.drawer').count()===0);
 await p.getByRole('button',{name:'Cancel',exact:true}).click();
 check('cancel keeps fake gateway unpaused',!(await(await c.request.get(url+'/admin/api/overview')).json()).paused);
 await p.getByRole('button',{name:'More navigation'}).click();await p.locator('.drawer.in').waitFor();await p.locator('.drawer .estop button').click();
 await p.getByRole('button',{name:'Stop everything',exact:true}).click();await p.getByText('AI access is paused for everyone.',{exact:true}).waitFor();
 check('confirmed pause reaches fake gateway',!!(await(await c.request.get(url+'/admin/api/overview')).json()).paused);
 await p.getByRole('button',{name:'More navigation'}).click();await p.locator('.drawer.in').waitFor();await p.getByRole('button',{name:'Resume AI access',exact:true}).last().click();
 await p.getByText('AI access is paused for everyone.',{exact:true}).waitFor({state:'detached'});
 check('resume reaches fake gateway',!(await(await c.request.get(url+'/admin/api/overview')).json()).paused);
 check('no browser exceptions',result.errors.length===0);
 console.log(`PASS ${result.checks.length} review regression checks`);
})().catch(e=>{result.failure=e.stack;console.error(e);process.exitCode=1;}).finally(async()=>{fs.writeFileSync(path.join(out,'review-results.json'),JSON.stringify(result,null,2)+'\n');await browser?.close();fixture?.kill('SIGTERM');});
