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
const {execFileSync}=require('node:child_process');
const crypto=require('node:crypto'),zlib=require('node:zlib');
(async()=>{
 const exact='d89f3e778d350bbf8148cb734d3b92109a6ce569',main='6ee3ed3aeaa5244cb88df8302b1435546112d524';
 check('requested product and fixture source unchanged',execFileSync('git',['diff','--exit-code',exact,'--','gateway','tests/browser/demo.py'],{cwd:root,encoding:'utf8'}).trim()==='');
 const {url}=await start();browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 result.provenance={head:exact,baseline:main,viewport:[1440,900],theme:'dark',cpuThrottle:1,rounds:1,limitations:'One trace per variant, synthetic backend, shared laptop/software-rendered headless Chromium; tracing overhead and scheduling noise uncontrolled; no 60fps/GPU/device claim'};
 const sys=await browser.newBrowserCDPSession();const info=await sys.send('SystemInfo.getInfo');result.gpu=info.gpu.devices.map(({vendorString,deviceString})=>({vendorString,deviceString}));result.traces=[];
 for(const [name,ref]of [['main',main],['r4',exact]]){
  const c=await browser.newContext({viewport:{width:1440,height:900}});
  for(const file of ['ui.css','admin-monitor.js']){const body=execFileSync('git',['show',ref+':gateway/static/'+file],{cwd:root,encoding:'utf8'});await c.route('**/static/'+file,r=>r.fulfill({contentType:file.endsWith('css')?'text/css':'application/javascript',body}));}
  check(name+' fixture login',(await c.request.post(url+'/admin/api/login',{headers:{'x-gateway-admin':'1'},data:{username:'owner@swangzavenue.com',password:'owner-password'}})).status()===200);
  const p=await c.newPage();p.on('pageerror',e=>result.errors.push(name+': '+e.message));await p.goto(url+'/admin#/');await p.locator('main h1').waitFor();await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(500);
  const cd=await c.newCDPSession(p);await cd.send('Performance.enable');const before=await cd.send('Performance.getMetrics');const events=[];cd.on('Tracing.dataCollected',e=>events.push(...e.value));
  await cd.send('Tracing.start',{categories:'devtools.timeline,blink.user_timing,v8.execute,disabled-by-default-devtools.timeline',options:'record-as-much-as-possible'});
  await p.evaluate(()=>{performance.mark('r4-workload-start');window.samples=[];window.sampling=true;let last;function tick(t){if(last!==undefined)samples.push(t-last);last=t;if(sampling)requestAnimationFrame(tick);}requestAnimationFrame(tick);});
  for(let round=0;round<2;round++){for(let i=0;i<3;i++){await p.locator('.kpi').nth(i).hover();await p.waitForTimeout(220);}await p.evaluate(()=>scrollTo(0,450));await p.waitForTimeout(250);await p.evaluate(()=>scrollTo(0,0));await p.waitForTimeout(250);}
  const frame=await p.evaluate(()=>{sampling=false;performance.mark('r4-workload-end');return {frames:samples.length,over50:samples.filter(v=>v>50).length,max:Math.max(...samples)};});
  const ended=new Promise(resolve=>cd.once('Tracing.tracingComplete',resolve));await cd.send('Tracing.end');await ended;const after=await cd.send('Performance.getMetrics');
  const a=Object.fromEntries(after.metrics.map(x=>[x.name,x.value])),b=Object.fromEntries(before.metrics.map(x=>[x.name,x.value]));const metrics=Object.fromEntries(['TaskDuration','ScriptDuration','LayoutDuration','RecalcStyleDuration','LayoutCount','RecalcStyleCount'].map(k=>[k,a[k]-b[k]]));
  const bytes=zlib.gzipSync(Buffer.from(JSON.stringify({traceEvents:events,metadata:{...result.provenance,variant:name}})));const file='trace-'+name+'.json.gz';fs.writeFileSync(path.join(out,file),bytes);result.traces.push({name,ref,file,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length,events:events.length,frame,metrics});console.log(JSON.stringify(result.traces.at(-1)));await c.close();
 }
 check('no browser exceptions',result.errors.length===0);console.log('PASS two Chrome performance traces saved; no 60fps inference');
})().catch(e=>{result.failure=e.stack;console.error(e);process.exitCode=1}).finally(async()=>{fs.writeFileSync(path.join(out,'performance-trace-results.json'),JSON.stringify(result,null,2)+'\n');await browser?.close();fixture?.kill('SIGTERM');});
