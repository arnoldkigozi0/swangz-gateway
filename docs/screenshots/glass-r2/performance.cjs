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


 const {execFileSync}=require('node:child_process');const variants={main:'f898ebf',reviewed:'dcb058e',corrected:null};result.runs=[];
 const current=Object.fromEntries(['admin.css','admin.js'].map(file=>[file,fs.readFileSync(path.join(root,'gateway/static',file),'utf8')]));
 result.sourceHashes=Object.fromEntries(Object.entries(current).map(([file,source])=>[file,require('node:crypto').createHash('sha256').update(source).digest('hex')]));
 const state=await c.storageState();await p.close();
 for(let round=0;round<3;round++)for(const[name,ref]of Object.entries(variants)){
  const cc=await browser.newContext({storageState:state,viewport:{width:1366,height:768}});
  for(const file of ['admin.css','admin.js']){const source=ref?execFileSync('git',['show',ref+':gateway/static/'+file],{cwd:root,encoding:'utf8'}):current[file];await cc.route('**/static/'+file,route=>route.fulfill({contentType:file.endsWith('css')?'text/css':'application/javascript',body:source}));}
  const page=await cc.newPage();page.on('pageerror',e=>result.errors.push(name+': '+e.message));await page.bringToFront();await page.goto(url+'/admin#/');await loaded(page);
  await page.evaluate(()=>{window.frameSamples=[];window.sample=true;let last;function tick(t){if(last!==undefined)frameSamples.push(t-last);last=t;if(sample)requestAnimationFrame(tick);}requestAnimationFrame(tick);});
  for(const route of ['#/tools','#/people','#/reports','#/security','#/settings','#/']){
   await page.evaluate(h=>location.hash=h,route);await page.waitForFunction(()=>window.SWA.S.route===location.hash&&document.querySelector('main h1')?.textContent);await page.waitForTimeout(500);
  }
  const run=await page.evaluate(()=>{sample=false;const s=frameSamples;return{frames:s.length,over50:s.filter(x=>x>50).length,max:Math.max(...s)};});result.runs.push({round,name,...run});console.log(JSON.stringify(result.runs.at(-1)));await cc.close();
 }
 for(const name of Object.keys(variants)){const rows=result.runs.filter(r=>r.name===name);const med=key=>rows.map(r=>r[key]).sort((a,b)=>a-b)[1];console.log(name+' median '+JSON.stringify({over50:med('over50'),max:med('max')}));}
 check('no performance-run browser exceptions',result.errors.length===0);
 console.log('Same fixture, browser, viewport and six-route rAF script. Three interleaved rounds; scheduling noise and other builders uncontrolled. This is not Probe original script, a 60fps guarantee, or a device test.');
})().catch(e=>{result.failure=e.stack;console.error(e);process.exitCode=1;}).finally(async()=>{fs.writeFileSync(path.join(out,'performance-results.json'),JSON.stringify(result,null,2)+'\n');await browser?.close();fixture?.kill('SIGTERM');});
