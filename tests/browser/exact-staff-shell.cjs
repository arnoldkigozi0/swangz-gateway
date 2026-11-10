/* Focused real-browser acceptance harness. Uses the existing optional Playwright/axe tooling.
   Run only on the authorized browser test surface. Fixture is local and synthetic. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const { chromium } = require('playwright');
const { AxeBuilder } = require('@axe-core/playwright');
const root = path.resolve(__dirname, '../..');
const out = process.env.UI_OUTPUT || path.join(root,'docs/screenshots/exact-staff-shell');
fs.mkdirSync(out,{recursive:true});
const results = { cells: [], errors: [], checks: [], scope: 'Staff shell only. Main launchpad content is inherited; all visual differences require review.' };
let demo, browser;
function check(label,value) { assert.ok(value,label); results.checks.push(label); }
async function fixture() {
  demo = spawn('python3',[path.join(__dirname,'demo.py')],{cwd:root,stdio:['ignore','pipe','pipe']});
  return new Promise((resolve,reject) => {
    let stdout='',stderr='';
    const timer=setTimeout(()=>reject(Error('Fixture timeout: '+stderr)),30000);
    demo.stdout.on('data',d=>{stdout+=d;if(stdout.includes('\n')){clearTimeout(timer);resolve(JSON.parse(stdout.split('\n')[0]));}});
    demo.stderr.on('data',d=>{stderr+=d;});
    demo.on('exit',code=>{clearTimeout(timer);reject(Error('Fixture exited: '+code+' '+stderr));});
  });
}
(async()=>{
  try {
    const {url}=await fixture();
    browser=await chromium.launch({headless:true});
    for(const theme of ['dark','light']) for(const [width,height] of [[1440,852],[390,844]]) {
      const c=await browser.newContext({viewport:{width,height},reducedMotion:'reduce'});
      await c.addInitScript(t=>localStorage.setItem('swangz-theme',t),theme);
      const login=await c.request.post(url+'/api/login',{headers:{'x-swangz-app':'1'},data:{email:'grace@swangzavenue.com',password:'demo-password'}});
      assert.equal(login.status(),200);
      const p=await c.newPage(); p.on('pageerror',e=>results.errors.push(e.message));
      await p.goto(url+'/#/'); await p.locator('.staff-exact').waitFor();
      await p.evaluate(()=>document.fonts.ready);
      const name=`${width}-${height}-${theme}`;
      check(name+' no horizontal overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      if(width===1440) {
        const home=await p.locator('.home-grid').evaluate(n=>({width:n.getBoundingClientRect().width,columns:getComputedStyle(n).gridTemplateColumns}));
        check(name+' home grid is not console 129px',home.width>900 && !home.columns.startsWith('129px'));
        const meta=await p.locator('.hero-meta').evaluate(n=>({width:n.getBoundingClientRect().width,height:n.getBoundingClientRect().height,client:n.clientWidth,scroll:n.scrollWidth,text:n.textContent}));
        check(name+' home metadata is visible and fits',meta.width>400 && meta.height>0 && meta.scroll<=meta.client+1 && meta.text.trim().length>0);
      }
      const shot=path.join(out,name+'.png'); await p.screenshot({path:shot});
      const geometry=await p.evaluate(()=>Object.fromEntries(['.staff-rail','.staff-workspace','.staff-search','.staff-new','.staff-account'].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return[s,{x:r.x,y:r.y,width:r.width,height:r.height}];})));
      if(width===1440){
        for(const [sel,x,y,w,h] of [['.staff-rail',67,22,62,810],['.staff-workspace',175,19,135,38],['.staff-search',588,19,345,38],['.staff-new',1082,19,83,38],['.staff-account',1327,19,36,38]]) {
          const got=geometry[sel]; check(name+' '+sel+' geometry',Math.abs(got.x-x)<=4&&Math.abs(got.y-y)<=4&&Math.abs(got.width-w)<=4&&Math.abs(got.height-h)<=4);
        }
      }
      // Scan the whole shell, including menus when open, with no disabled rules.
      const axe=await new AxeBuilder({page:p}).include('.staff-exact').analyze();
      fs.writeFileSync(path.join(out,'axe-'+name+'.json'),JSON.stringify(axe.violations,null,2));
      results.cells.push({name,geometry,violations:axe.violations.length});
      check(name+' axe',axe.violations.length===0);
      await p.getByRole('button',{name:'Your account',exact:true}).focus();
      await p.keyboard.press('ArrowDown');
      check(name+' account keyboard opens',await p.getByRole('menuitem',{name:'Profile',exact:true}).evaluate(n=>n===document.activeElement));
      await p.keyboard.press('End');
      check(name+' account End',await p.getByRole('menuitem',{name:'Sign out',exact:true}).evaluate(n=>n===document.activeElement));
      await p.keyboard.press('Escape');
      await p.keyboard.press('Control+k');
      await p.getByRole('searchbox',{name:'Search pages',exact:true}).fill('weekly');
      check(name+' search retains report route',await p.locator('.drawer a[href="#/weekly"]').isVisible());
      await p.keyboard.press('Escape');
      if(width===390){
        await p.getByRole('button',{name:'Open navigation',exact:true}).click();
        check(name+' all routes reachable',await p.locator('.drawer a[href="#/privacy"]').isVisible());
        await p.keyboard.press('Escape');
      }
      await c.close();
    }
    const ref=path.join(root,'docs/design/references/stills/dashboard-02.jpg');
    fs.copyFileSync(ref,path.join(out,'reference-dashboard-02.jpg'));
    const image=path.join(out,'1440-852-dark.png');
    for(const [file,filter] of [['overlay-dark.png','[0:v][1:v]blend=all_expr=(A+B)/2'],['beside-dark.png','[0:v][1:v]hstack=inputs=2']]) {
      const run=spawnSync('ffmpeg',['-y','-i',ref,'-i',image,'-filter_complex',filter,'-frames:v','1',path.join(out,file)],{encoding:'utf8'});
      assert.equal(run.status,0,run.stderr);
    }
    check('No browser exceptions',results.errors.length===0);
  } finally {
    if(browser) await browser.close();
    if(demo && demo.exitCode===null){const ended=new Promise(r=>demo.once('exit',r));demo.kill('SIGTERM');await ended;}
    fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify(results,null,2));
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
