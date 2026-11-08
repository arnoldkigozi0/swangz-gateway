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
 const c=await browser.newContext({viewport:{width:1440,height:900}});
 check('synthetic staff login',(await c.request.post(url+'/api/login',{headers:{'x-swangz-app':'1'},data:{email:'grace@swangzavenue.com',password:'demo-password'}})).status()===200);
 const p=await c.newPage();await p.goto(url+'/');await p.locator('.home-tool-rows a[href$="canva"]').waitFor();await p.evaluate(()=>document.fonts.ready);
 await p.evaluate(()=>{document.documentElement.dataset.theme='dark';});await p.waitForTimeout(350);
 result.before=await p.locator('.home-tool-rows a.btn').evaluateAll(es=>es.map(e=>({href:e.getAttribute('href'),color:getComputedStyle(e).color})));
 await p.evaluate(()=>{document.documentElement.dataset.theme='light';getComputedStyle(document.querySelector('.home-tool-rows a.btn')).color;});
 // Freeze the native transition at its real 30ms colour state so axe can inspect it
 // independently of CPU speed. No style values or accessibility rules are replaced.
 result.transitions=await p.evaluate(()=>document.getAnimations().filter(a=>a.transitionProperty==='color').map(a=>{a.pause();a.currentTime=30;return {property:a.transitionProperty,duration:a.effect.getTiming().duration};}));
 const mid=await new AxeBuilder({page:p}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();result.transient=mid.violations;
 check('native transitional launch link contrast reproduced',mid.violations.some(v=>v.id==='color-contrast'&&v.nodes.some(n=>n.html.includes('/go/canva'))));
 await p.evaluate(async()=>{await document.fonts.ready;const finite=document.getAnimations().filter(a=>Number.isFinite(a.effect.getComputedTiming().endTime));for(const a of finite)a.play();await Promise.all(finite.map(a=>a.finished.catch(()=>{})));});
 const end=await new AxeBuilder({page:p}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();result.settled=end.violations;
 check('settled staff Home has no axe findings',end.violations.length===0);
 console.log('PASS '+result.checks.length+' CI contrast diagnosis checks; native 30ms state fails, settled state passes');
})().catch(e=>{result.failure=e.stack;console.error(e);process.exitCode=1;}).finally(async()=>{fs.writeFileSync(path.join(out,'ci-contrast-results.json'),JSON.stringify(result,null,2)+'\n');await browser?.close();fixture?.kill('SIGTERM');});
