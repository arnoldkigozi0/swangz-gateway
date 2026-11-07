const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const root = process.env.GLASS_ROOT || path.resolve(__dirname, '../../..');
const {chromium} = require(path.join(root, 'tests/browser/node_modules/playwright'));
const {AxeBuilder} = require(path.join(root, 'tests/browser/node_modules/@axe-core/playwright'));
const out = path.join(root, 'docs/screenshots/glass-r1');
fs.mkdirSync(out, {recursive:true});
let fixture, browser;
const result = {checks:[], errors:[], screenshots:[], contrast:[], accessibility:[]};
function check(name, ok) {assert.ok(ok,name); result.checks.push(name);}
function rgba(s) {const a=s.match(/[\d.]+/g).map(Number);return a.length===3?[...a,1]:a;}
function composite(a,b) {return a.slice(0,3).map((v,i)=>v*a[3]+b[i]*(1-a[3]));}
function lum(c) {return c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);}
function contrast(a,b) {const l=[lum(a),lum(b)].sort((a,b)=>b-a);return(l[0]+.05)/(l[1]+.05);}
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
  const file=`admin-${width}-${theme}.png`;await p.screenshot({path:path.join(out,file),animations:'disabled'});result.screenshots.push(file);
 }
 check('synthetic staff login', (await context.request.post(url+'/api/login',{headers:{'x-swangz-app':'1'},data:{email:'grace@swangzavenue.com',password:'demo-password'}})).status()===200);
 for(const theme of ['dark','light'])for(const [width,height]of [[1440,900],[390,844]]){
  await p.setViewportSize({width,height});await p.goto(url+'/#/tools');await p.locator('main h1').waitFor();
  await p.evaluate(t=>document.documentElement.dataset.theme=t,theme);await p.evaluate(()=>document.fonts.ready);
  check(theme+width+' staff catalogue no overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  check(theme+width+' staff uses own artwork',await p.evaluate(()=>getComputedStyle(document.body,'::before').backgroundImage.includes('home-welcome.webp')));
 }
 await p.route('**/r1-utilities',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Glass R1 utility verification</title><link rel="stylesheet" href="/static/tokens.css"><link rel="stylesheet" href="/static/ui.css"><style>main{max-width:960px;margin:auto;padding:24px;display:grid;gap:24px}.u-glass,.u-glass-strong,.u-glass-accent{padding:24px}.muted{color:var(--tx-3)}button{padding:12px 20px;min-height:44px}h1,h2{margin:0 0 12px}.u-glass-well{padding:16px;margin-top:16px}</style><main><h1>Glass foundation</h1><section class="u-glass u-glass-lift"><h2>Smoked glass</h2><p class="muted">Utility verification using synthetic content.</p><button class="u-glass u-glass-pill">Keyboard focus</button><div class="u-glass-well">Inset well: no second blur</div></section><section class="u-glass-strong"><h2>Dense text surface</h2><p class="muted">Strong glass keeps supporting text readable.</p></section><section class="u-glass-accent"><h2>Warm accent surface</h2><p class="muted">123,456.78 — tabular figures</p></section></main></html>`}));
 await p.goto(url+'/r1-utilities');
 const cdp=await context.newCDPSession(p);
 for(const theme of ['dark','light']){
  await p.evaluate(t=>document.documentElement.dataset.theme=t,theme);await p.setViewportSize({width:390,height:844});
  check(theme+' utilities: no overflow',await p.evaluate(()=>document.documentElement.scrollWidth===innerWidth));
  const style=await p.evaluate(()=>{const v=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();return {scrim:v('--scene-scrim'),tx:getComputedStyle(document.querySelector('.muted')).color,accentTx:getComputedStyle(document.querySelector('.u-glass-accent .muted')).color,normal:getComputedStyle(document.querySelector('.u-glass')).backgroundColor,strong:getComputedStyle(document.querySelector('.u-glass-strong')).backgroundColor,blur:getComputedStyle(document.querySelector('.u-glass')).backdropFilter,nested:getComputedStyle(document.querySelector('button.u-glass')).backdropFilter};});
  check(theme+' blur enabled once',style.blur.includes('22px')&&style.nested==='none');
  for(const bg of [[0,0,0],[255,255,255]]){
   const scene=composite(rgba(style.scrim),bg);
   const accents=theme==='dark'?[[245,179,43,.38],[120,72,24,.30]]:[[245,179,43,.30],[229,190,120,.18]];
   for(const [name,surface]of [['scene',scene],['glass',composite(rgba(style.normal),scene)],['strong',composite(rgba(style.strong),scene)],...accents.map((c,i)=>['accent'+i,composite(c,scene)])]){
    const ratio=contrast(rgba(name.startsWith('accent')?style.accentTx:style.tx),surface);result.contrast.push({theme,photo:bg[0],surface:name,ratio:Number(ratio.toFixed(2))});check(theme+' '+bg[0]+' '+name+' supporting text >=4.5',ratio>=4.5);
   }
  }
  await p.getByRole('button',{name:'Keyboard focus'}).focus();check(theme+' visible focus ring',await p.locator('button').evaluate(e=>getComputedStyle(e).outlineStyle==='solid'&&getComputedStyle(e).outlineWidth==='2px'));
  const axe=(await new AxeBuilder({page:p}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations;result.accessibility.push({theme,violations:axe.map(v=>v.id)});check(theme+' utility axe scan',axe.length===0);
  const file=`utilities-390-${theme}.png`;await p.screenshot({path:path.join(out,file),fullPage:true,animations:'disabled'});result.screenshots.push(file);
  await cdp.send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-transparency',value:'reduce'}]});
  check(theme+' reduced transparency removes blur and image',await p.evaluate(()=>getComputedStyle(document.querySelector('.u-glass')).backdropFilter==='none'&&getComputedStyle(document.body,'::before').backgroundImage==='none'));
  check(theme+' reduced transparency solid surface',await p.evaluate(()=>getComputedStyle(document.querySelector('.u-glass')).backgroundColor===getComputedStyle(document.querySelector('.u-glass-strong')).backgroundColor&&!getComputedStyle(document.querySelector('.u-glass')).backgroundColor.startsWith('rgba')));
  await cdp.send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});await p.locator('.u-glass-lift').hover();
  check(theme+' reduced motion prevents lift',await p.locator('.u-glass-lift').evaluate(e=>getComputedStyle(e).transform==='none'));
  check(theme+' reduced motion disables translated entrance',await p.locator('.u-glass-lift').evaluate(e=>{e.classList.add('u-enter');const none=getComputedStyle(e).animationName==='none';e.classList.remove('u-enter');return none;}));
  await cdp.send('Emulation.setEmulatedMedia',{features:[]});
 }
 // Exercise the unsupported-blur declaration block in a browser that otherwise supports blur.
 await p.route('**/static/ui.css',route=>route.fulfill({contentType:'text/css',body:fs.readFileSync(path.join(root,'gateway/static/ui.css'),'utf8').replace('@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px)))','@supports (display: block)')}));
 await p.reload();
 for(const theme of ['dark','light']){await p.evaluate(t=>document.documentElement.dataset.theme=t,theme);check(theme+' forced unsupported branch is solid with no blur',await p.locator('.u-glass').first().evaluate(e=>getComputedStyle(e).backdropFilter==='none'&&!getComputedStyle(e).backgroundColor.startsWith('rgba')));}
 check('no browser exceptions',result.errors.length===0);
 console.log('PASS '+result.checks.length+' targeted checks; '+result.screenshots.length+' screenshots; '+result.contrast.length+' contrast bounds');
})().catch(e=>{result.failure=e.stack;console.error(e);process.exitCode=1}).finally(async()=>{fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2));await browser?.close();fixture?.kill('SIGTERM');});
