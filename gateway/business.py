"""Native business-value calculations. No Tracker runtime or external financial assumptions."""
import json
import html
import math
from pathlib import Path
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from . import admin, reporting, staff
from .admin import ApiError

UNIT_HOURS = {'sec': 1/3600, 'min': 1/60, 'h': 1, 'd': 8, 'wk': 40, 'mo': 160, 'yr': 1920}
FORMULAS = {
 'working_time': 'seconds / 3600; minutes / 60; day × 8; week × 40; month × 160; year × 1920. Stored values are hours.',
 'time_saved': '(manual hours − AI-assisted hours) × declared frequency. Frequency period is explicit; unknown frequency produces no recurring total.',
 'cost': 'Manual cost per job × frequency. AI total = declared AI cost per job × frequency + subscription + credits + other expenses. An allowance allocation is not charged again as variable usage.',
 'roi': '(declared manual period cost − declared AI period cost) / declared AI period cost × 100. Requires both costs and a strictly positive AI denominator. Revenue is shown separately.',
 'allocation': 'Recurring charges are declarations, not invoices. Different declarations are never silently divided to infer a licence allocation. Catalogue subscription cost is shown separately.',
 'labour_value': 'Reported hours saved × explicitly configured current administrative USD/hour. This is an administrative valuation, not cash savings or a change to the original declaration.',
 'currency_conversion': 'An explicit current administrator-entered USD→UGX rate may show an alternate valuation. It is dated and is not a live market rate or a historical invoice conversion. Other currencies are not converted.',
 'scope': 'Business totals include submitted adoption declarations only, grouped by declared frequency period and currency. Weekly evidence remains independent. Missing values remain unavailable; partial sums disclose coverage.'}


def refresh_management(ctx,created,actor):
    period=reporting.week(ctx.gw,created)
    if period['ends']<=time.time():reporting.management_snapshot(ctx.gw,period['week_start'],actor)


def usage_price(r):
    amount, included, rate, sub = (r.get(k) for k in ('usage_amount', 'usage_included', 'usage_unit_cost_usd', 'subscription_cost'))
    if r.get('usage_flat_rate') == 1:
        return {'allocation': 0, 'variable': 0, 'method': 'flat subscription; marginal usage zero'}
    if amount is None:
        return {'allocation': None, 'variable': None, 'method': 'usage not supplied'}
    if amount == 0:
        return {'allocation': 0, 'variable': 0, 'method': 'declared zero usage'}
    if r.get('usage_unit') == 'usd':
        return {'allocation': amount, 'variable': amount, 'method': 'declared direct USD spend'}
    if included is not None and included > 0 and sub is not None and r.get('currency') == 'USD':
        excess = max(0, amount - included)
        extra = excess * rate if rate is not None else (0 if not excess else None)
        return {'allocation': sub * min(amount, included) / included + extra if extra is not None else None,
                'variable': extra, 'method': 'subscription allowance allocation plus priced overage'}
    if rate is not None:
        return {'allocation': amount * rate, 'variable': amount * rate, 'method': 'declared USD unit rate'}
    return {'allocation': None, 'variable': None, 'method': 'missing usage pricing'}


def calculate(r):
    if r.get('usage_confirmation') in ('opened_not_used','accidental'):
        r={**r,'frequency':None,'manual_hours':None,'ai_hours':None,'revenue':None}
    n = r.get('frequency')
    manual, assisted = r.get('manual_hours'), r.get('ai_hours')
    saved = manual - assisted if manual is not None and assisted is not None else None
    price = usage_price(r)
    old = r.get('manual_cost') * n if r.get('manual_cost') is not None and n is not None else None
    # Subscription is monthly. Never add it to a weekly/yearly/project total without an explicit allocation.
    ai = None
    if n is not None and r.get('frequency_period') == 'month' and all(r.get(k) is not None for k in ('subscription_cost','extra_credits','other_expenses')):
        per_job = r.get('ai_cost')
        if per_job is None and r.get('currency') == 'USD':
            per_job = price['variable']
        if per_job is not None:
            ai = per_job * n + r['subscription_cost'] + r['extra_credits'] + r['other_expenses']
    net = old - ai if old is not None and ai is not None else None
    return {'report_id': r['id'], 'version': r['version'], 'time_saved_per_job': saved,
            'manual_period_hours': manual * n if manual is not None and n is not None else None,
            'ai_period_hours': assisted * n if assisted is not None and n is not None else None,
            'time_saved_hours': saved * n if saved is not None and n is not None else None,
            'manual_period_cost': old, 'ai_period_cost': ai, 'net_savings': net,
            'roi_percent': _roi(net,ai),
            'revenue': r.get('revenue'), 'currency': r['currency'], 'period': r['frequency_period'],
            'usage_pricing': price, 'basis': r.get('financial_basis','declaration estimate'),
            'financial_complete': net is not None}


def _roi(net,ai):
    if net is None or ai is None or ai<=0:return None
    value=net/ai*100
    return value if math.isfinite(value) else None


def scope(ctx, personal=False):
    clauses, args = ["kind='adoption'", 'archived_at IS NULL'], []
    if personal:
        clauses.append('person_id=?'); args.append(ctx.person['id'])
    for key, col in (('department','department'), ('tool','tool_id'), ('person','person_id'), ('state','state')):
        if ctx.arg(key) and (not personal or key not in ('department','person')):
            clauses.append(col+'=?'); args.append(ctx.arg(key))
    if ctx.arg('q'):
        clauses.append('(tool_name LIKE ? OR reason LIKE ? OR impact LIKE ?)'); args.extend(['%'+ctx.arg('q')[:200]+'%']*3)
    if ctx.arg('from') and ctx.arg('to') and ctx.arg('from')>ctx.arg('to'):
        raise ApiError(400,'The start date must not follow the end date.')
    for key, op in (('from','>='), ('to','<')):
        if ctx.arg(key):
            try:
                d=date.fromisoformat(ctx.arg(key))
                if key=='to': d+=timedelta(days=1)
            except ValueError:
                raise ApiError(400, 'Use valid local dates for the reporting range.')
            clauses.append('created'+op+'?'); args.append(datetime.combine(d,datetime.min.time(),reporting.timezone(ctx.gw)).timestamp())
    return ' WHERE '+' AND '.join(clauses), args


def model(ctx, personal=False, department_scope=None):
    where, args = scope(ctx, personal)
    if department_scope is not None:
        where+=" AND department=? AND state NOT IN ('draft','returned')";args.append(department_scope)
    rows = ctx.db.q('SELECT * FROM hub_reports'+where+' ORDER BY created DESC,id DESC', args)
    catalogue={t['id']:t['name'] for t in ctx.db.q('SELECT id,name FROM tools')}
    declarations=[r for r in rows if r['state'] not in reporting.OPEN_STATES]
    values=[{**calculate(r), 'tool_name':catalogue.get(r['tool_id'],r['tool_name']), 'declared_tool_name':r['tool_name'], 'tool_id':r['tool_id'], 'department':r['department'],
             'submitter_name':r['submitter_name'], 'submitter_email':r['submitter_email'], 'person_id':r['person_id'], 'created':r['created'],
             'impact':r['impact'], 'reason':r['reason'], 'quality':r['quality'], 'adoption_stage':r['adoption_stage']} for r in declarations]
    hourly=reporting.number(ctx.db.get_setting('hub_hourly_rate_usd',''),'hourly_rate_usd')
    fx=reporting.number(ctx.db.get_setting('hub_usd_ugx',''),'usd_ugx')
    for r in values:
        r.update(allocation_hourly_rate_usd=hourly,allocation_usd_ugx=fx,allocation_asof=ctx.db.get_setting('hub_finance_asof',''))
        r['allocated_time_value_usd']=r['time_saved_hours']*hourly if r['time_saved_hours'] is not None and hourly is not None else None
        r['allocated_time_value_ugx']=r['allocated_time_value_usd']*fx if r['allocated_time_value_usd'] is not None and fx is not None else None
        r['net_savings_ugx']=r['net_savings']*fx if r['net_savings'] is not None and r['currency']=='USD' and fx is not None else None
    groups={}
    for key in ('tool_name','department','submitter_name'):
        buckets=defaultdict(list)
        for r in values:
            identity=r['tool_id'] or r['tool_name'] if key=='tool_name' else str(r['person_id'] or r['submitter_email'] or r['submitter_name']) if key=='submitter_name' else r[key]
            buckets[(str(identity),r['period'],r['currency'])].append(r)
        groups[key]=[]
        for (identity,period,currency), items in sorted(buckets.items()):
            label=items[0][key]
            out={'name':label or 'Unattributed', 'period':period, 'currency':currency, 'reports':len(items),
                 'report_ids':[i['report_id'] for i in items], 'tool_id':items[0]['tool_id'], 'person_id':items[0]['person_id']}
            for metric in ('time_saved_hours','manual_period_hours','ai_period_hours','net_savings','revenue'):
                known=[i[metric] for i in items if i[metric] is not None]
                out[metric]=sum(known) if known else None
                out[metric+'_coverage']=len(known)
            groups[key].append(out)
    months=defaultdict(list)
    for r in values: months[datetime.fromtimestamp(r['created'],reporting.timezone(ctx.gw)).strftime('%Y-%m')].append(r)
    trends=[{'month':m,'declarations':len(items), 'tools':len({i['tool_id'] or i['tool_name'] for i in items})} for m,items in sorted(months.items())]
    project_scope=where.replace("kind='adoption' AND ",'').replace('person_id=', 'r.person_id=')
    projects=ctx.db.q('SELECT p.*,r.kind,r.tool_name,r.department,r.submitter_name,r.state,r.version FROM hub_report_projects p JOIN hub_reports r ON r.id=p.report_id'+project_scope+' ORDER BY r.created DESC,p.position',args)
    evidence_clauses, evidence_args = [], []
    if department_scope is not None:
        evidence_clauses.append('department=?');evidence_args.append(department_scope)
    if personal:
        evidence_clauses.append('person_id=?'); evidence_args.append(ctx.person['id'])
    for key in ('department','tool','person'):
        if ctx.arg(key) and (not personal or key=='tool'):
            evidence_clauses.append({'department':'department','tool':'tool_id','person':'person_id'}[key]+'=?');evidence_args.append(ctx.arg(key))
    for key,op in (('from','>='),('to','<')):
        if ctx.arg(key):
            day=date.fromisoformat(ctx.arg(key))+(timedelta(days=1) if key=='to' else timedelta())
            evidence_clauses.append('starts'+op+'?');evidence_args.append(datetime.combine(day,datetime.min.time(),reporting.timezone(ctx.gw)).timestamp())
    evidence=ctx.db.q('SELECT person_id,tool_id,week_start,department,api_requests,launches,access_events,estimated_api_cost,completeness FROM weekly_evidence'+(' WHERE '+' AND '.join(evidence_clauses) if evidence_clauses else '')+' ORDER BY week_start',evidence_args)
    licences=[]
    if not personal and department_scope is None:
        for s in ctx.db.q("SELECT s.tool_id,t.name,s.seats,s.monthly_cost FROM subscriptions s JOIN tools t ON t.id=s.tool_id WHERE s.state='active'"):
            activity=[e for e in evidence if e['tool_id']==s['tool_id']]
            s['observed_people']=len({e['person_id'] for e in activity})
            s['observed_events']=sum(e['api_requests']+e['launches']+e['access_events'] for e in activity)
            s['basis']='Administrative subscription record; closed-week observed users, not vendor seat verification.'
            licences.append(s)
    findings=[]
    for g in groups['tool_name']:
        if g['net_savings'] is not None and g['net_savings']<0:
            findings.append({'title':'Declared costs exceed estimated savings','tool':g['name'],'report_ids':g['report_ids'],
                             'reason':f"{g['currency']} {g['net_savings']:g} estimated net per {g['period']}; {g['net_savings_coverage']}/{g['reports']} declarations have comparable costs. Review context before making a subscription decision."})
    incomplete=sum(not r['financial_complete'] for r in values)
    if incomplete: findings.append({'title':'Financial evidence gaps','tool':'','report_ids':[], 'reason':f'{incomplete} declarations lack a defensible comparable cost calculation. Missing values were not treated as zero.'})
    return {'reports':values, 'draft_count':len(rows)-len(declarations), 'groups':groups, 'trends':trends, 'findings':findings,
            'projects':projects, 'observed':evidence, 'licences':licences, 'formulas':FORMULAS, 'generated':time.time(),
            'company':{'drive_folder':ctx.db.get_setting('hub_drive_folder',''),'hourly_rate_usd':hourly,'usd_ugx':fx,'finance_asof':ctx.db.get_setting('hub_finance_asof',''),'finance_basis':ctx.db.get_setting('hub_finance_basis','')},
            'limitations':'Reported estimates, not verified savings or vendor spend. Frequency periods and currencies are never combined. Repeated declarations may describe overlapping work; totals are declaration totals, not unique production output.'}


@staff.route('POST', r'/hub/business/calculate')
@admin.route('POST', r'/hub/business/calculate')
def scenario(ctx):
    claim=reporting.validate(ctx.body)
    for value,unit,destination in (('manual_time','manual_unit','manual_hours'),('ai_time','ai_unit','ai_hours')):
        if value in ctx.body:
            amount=reporting.number(ctx.body[value],value)
            claim[destination]=amount*UNIT_HOURS[claim.get(unit,'h')] if amount is not None else None
    r={'id':None,'version':0,'currency':claim.get('currency') or 'USD','frequency_period':claim.get('frequency_period') or 'month',**claim}
    result=calculate(r);result['basis']='hypothetical scenario; not saved as a declaration or observed activity'
    return {'calculation':result,'formulas':FORMULAS}


@staff.route('GET', r'/hub/business')
def staff_business(ctx): return model(ctx, True)


@admin.route('GET', r'/hub/business')
def admin_business(ctx): return model(ctx)


@admin.route('GET', r'/hub/registry')
def registry(ctx):
    references=json.loads(Path(__file__).with_name('tracker_registry_reference.json').read_text())
    return {'references':references, 'unmatched':ctx.db.q("SELECT id,tool_name,official_url,category,submitter_name FROM hub_reports WHERE kind='adoption' AND tool_id IS NULL AND archived_at IS NULL ORDER BY created DESC"),
            'note':'Catalogue settings, assignments and subscriptions remain authoritative.'}


@staff.route('GET', r'/hub/business/export')
def staff_export(ctx): return export(ctx, True)


@admin.route('GET', r'/hub/business/export')
def admin_export(ctx): return export(ctx)


def export(ctx, personal=False):
    data=model(ctx,personal)
    fields=('report_id','version','tool_name','department','submitter_name','period','currency','manual_period_hours','ai_period_hours','time_saved_hours','manual_period_cost','ai_period_cost','net_savings','roi_percent','revenue','financial_complete','basis','impact','allocated_time_value_usd','allocated_time_value_ugx','net_savings_ugx','allocation_hourly_rate_usd','allocation_usd_ugx','allocation_asof')
    ctx.gw.audit(ctx.person['email'] if personal else ctx.admin['username'],'exported adoption estimates',str(len(data['reports'])))
    mode=ctx.arg('format','csv')
    headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
    if mode=='json':
        data['declarations']=[reporting.detail(ctx.gw,r['report_id'],ctx.person['id'] if personal else None) for r in data['reports']]
        headers['Content-Disposition']='attachment; filename="hub-business-reports.json"'
        return json.dumps(data,ensure_ascii=False).encode(),'application/json; charset=utf-8',headers
    if mode=='html':
        def esc(v): return html.escape('Unavailable' if v is None else str(v))
        document_fields=('report_id','version','tool_name','department','period','currency','time_saved_hours','net_savings','roi_percent','basis')
        table='<table><thead><tr>'+''.join('<th>'+esc(k.replace('_',' '))+'</th>' for k in document_fields)+'</tr></thead><tbody>'
        table+=''.join('<tr>'+''.join('<td>'+esc(r.get(k))+'</td>' for k in document_fields)+'</tr>' for r in data['reports'])+'</tbody></table>'
        cases=''.join('<article><h3>'+esc(r['tool_name'])+' — declaration '+esc(r['report_id'])+', version '+esc(r['version'])+'</h3><p>'+esc(r['submitter_name'])+' · '+esc(r['department'])+'</p>'+''.join('<p><strong>'+esc(label)+': </strong>'+esc(r.get(key))+'</p>' for key,label in (('reason','Business purpose'),('quality','Reported quality'),('impact','Reported impact'),('manual_period_hours','Manual working hours'),('ai_period_hours','AI working hours'),('manual_period_cost','Manual cost estimate'),('ai_period_cost','AI cost estimate'),('revenue','Reported revenue contribution')))+'<p>'+esc(r['currency'])+' per '+esc(r['period'])+' · '+esc(r['basis'])+'</p></article>' for r in data['reports'])
        projects=''.join('<article><h3>'+esc(p['name'])+'</h3><p>'+esc(p['tool_name'])+' · '+esc(p['kind'])+' · '+esc(p['submitter_name'])+'</p>'+''.join('<p><strong>'+esc(label)+': </strong>'+esc(p[key])+'</p>' for key,label in (('description','Deliverable'),('traditional','Manual workflow'),('ai_way','AI workflow'),('benefit','Reported outcome')) if p[key])+'</article>' for p in data['projects'])
        body='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Swangz AI Hub — business report</title><link rel="stylesheet" href="/static/business-print.css"><main><h1>Swangz AI Hub — business report</h1><p>Generated '+esc(datetime.fromtimestamp(data['generated'],reporting.timezone(ctx.gw)).isoformat())+'</p><p>'+esc(data['limitations'])+'</p><p>Use your browser’s Print command to save a PDF. This export contains only your authenticated reporting scope.</p>'+'<p>Current administrative hourly value (USD): '+esc(data['company']['hourly_rate_usd'])+'; USD→UGX: '+esc(data['company']['usd_ugx'])+'; entered at: '+esc(data['company']['finance_asof'] or None)+'; basis: '+esc(data['company']['finance_basis'] or None)+'.</p>'+table+'<h2>Business cases</h2>'+cases+'<h2>Projects</h2>'+projects+'<h2>Calculation methods</h2>'+''.join('<p><strong>'+esc(k)+': </strong>'+esc(v)+'</p>' for k,v in data['formulas'].items())+'</main></html>'
        headers['Content-Security-Policy']="default-src 'none'; style-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; sandbox"
        return body.encode(),'text/html; charset=utf-8',headers
    if mode!='csv': raise ApiError(400,'Choose CSV, JSON or the print/document view.')
    headers['Content-Disposition']='attachment; filename="hub-business-estimates.csv"'
    return reporting.csv_bytes(data['reports'],fields),'text/csv; charset=utf-8',headers


def amend(ctx, rid, personal=False):
    reason=str(ctx.body.get('amendment_reason') or '').strip()
    if not reason or len(reason)>1000: raise ApiError(400,'Explain the amendment in up to 1,000 characters.')
    actor=ctx.person['email'] if personal else ctx.admin['username']
    with ctx.db.tx():
        r=reporting.detail(ctx.gw,int(rid),ctx.person['id'] if personal else None)
        if r['kind']!='adoption' or r['archived_at'] or r['state'] in reporting.OPEN_STATES:
            raise ApiError(409,'Only active submitted adoption declarations can be amended. Weekly corrections use the review workflow.')
        if ctx.body.get('version')!=r['version']: raise ApiError(409,'This declaration changed. Reload before amending.')
        claim={k:r[k] for k in reporting.CLAIMS};claim['projects']=r['projects'];claim.update(reporting.validate(ctx.body));claim=reporting.validate(claim,True)
        claim.update(financial_basis=r['financial_basis'],financial_actor=r['financial_actor'])
        financial=('manual_cost','ai_cost','subscription_cost','extra_credits','other_expenses','revenue','revenue_description','usage_included','usage_unit_cost_usd','usage_cost_usd','currency','selected_plan','pricing_source','usage_unit','usage_flat_rate')
        if not personal:
            from . import authz
            if any(claim.get(k)!=r[k] for k in financial) and not authz.can(ctx.admin,'money'):
                raise ApiError(403,'Money permission is required to amend financial estimates.')
        fields={k:v for k,v in claim.items() if k in reporting.CLAIMS}
        fields.update(version=r['version']+1,updated=time.time())
        if personal and any(claim.get(k)!=r[k] for k in financial):
            basis='mixed staff and administrative estimates' if r['financial_basis'] in ('administrative estimate','mixed staff and administrative estimates') else 'staff-reported estimate'
            fields.update(financial_basis=basis,financial_actor=actor)
            claim.update(financial_basis=basis,financial_actor=actor)
        if not personal and any(claim.get(k)!=r[k] for k in financial):
            fields.update(financial_basis='administrative estimate',financial_actor=actor)
            claim.update(financial_basis='administrative estimate',financial_actor=actor)
        ctx.db.x('UPDATE hub_reports SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),r['id']))
        ctx.db.x('DELETE FROM hub_report_projects WHERE report_id=?',(r['id'],))
        for i,p in enumerate(claim['projects']):
            ctx.db.x('INSERT INTO hub_report_projects(report_id,position,name,link,description,traditional,ai_way,benefit) VALUES(?,?,?,?,?,?,?,?)',(r['id'],i,p['name'],p['link'],p['description'],p['traditional'],p['ai_way'],p['benefit']))
        ctx.db.x('INSERT INTO hub_report_versions VALUES(?,?,?,?,?,?,?)',(r['id'],fields['version'],fields['updated'],actor,json.dumps(claim,sort_keys=True),r['reconciliation'],'Amendment: '+reason))
        ctx.db.x('INSERT INTO hub_report_reviews(report_id,version,actor,ts,action,note) VALUES(?,?,?,?,?,?)',(r['id'],fields['version'],actor,fields['updated'],'amended',reason))
        ctx.gw.audit(actor,'amended adoption declaration',str(r['id']),reason=reason,before={'version':r['version']},after={'version':fields['version']},correlation=f"hub-report:{r['id']}")
    refresh_management(ctx,r['created'],actor)
    return reporting.detail(ctx.gw,r['id'])


@staff.route('POST', r'/hub/reports/(?P<rid>\d+)/amend')
def staff_amend(ctx,rid): return amend(ctx,rid,True)


@admin.route('POST', r'/hub/reports/(?P<rid>\d+)/amend', area='govern')
def admin_amend(ctx,rid): return amend(ctx,rid)


@admin.route('POST', r'/hub/reports/(?P<rid>\d+)/pricing', area='money')
def report_pricing(ctx,rid):
    allowed={'manual_cost','ai_cost','subscription_cost','extra_credits','other_expenses','revenue','revenue_description',
             'usage_included','usage_unit_cost_usd','usage_cost_usd','currency','selected_plan','pricing_source','usage_unit','usage_flat_rate','version','amendment_reason'}
    if set(ctx.body)-allowed: raise ApiError(400,'Use the governance amendment workflow for non-financial changes.')
    return amend(ctx,rid)


@admin.route('POST', r'/hub/reports/archive', area='govern')
def archive(ctx):
    ids=ctx.body.get('ids'); reason=str(ctx.body.get('reason') or '').strip()
    if not isinstance(ids,list) or not ids or len(ids)>100 or any(type(i)!=int for i in ids) or not reason or len(reason)>1000:
        raise ApiError(400,'Select up to 100 declarations and provide an archival reason.')
    with ctx.db.tx():
        rows=[reporting.detail(ctx.gw,i) for i in set(ids)]
        if any(r['kind']!='adoption' for r in rows): raise ApiError(400,'Weekly accountability records cannot be archived.')
        for r in rows:
            if r['archived_at']: continue
            ctx.db.x('UPDATE hub_reports SET archived_at=?,archived_by=? WHERE id=?',(time.time(),ctx.admin['username'],r['id']))
            ctx.audit('archived adoption declaration',str(r['id']),reason=reason,correlation=f"hub-report:{r['id']}")
    for created in {r['created'] for r in rows}:
        refresh_management(ctx,created,ctx.admin['username'])
    return {'archived':len(rows),'note':'Original versions and import provenance retained. Reimport cannot resurrect these IDs.'}


@admin.route('POST', r'/hub/reports/(?P<rid>\d+)/attribution', area='govern')
def attribution(ctx,rid):
    reason=str(ctx.body.get('reason') or '').strip()
    if not reason or len(reason)>1000: raise ApiError(400,'Explain the attribution correction.')
    with ctx.db.tx():
        r=reporting.detail(ctx.gw,int(rid))
        if r['kind']!='adoption' or r['archived_at']: raise ApiError(409,'Only active adoption attribution can be corrected.')
        pid=ctx.body.get('person_id',r['person_id']);tid=ctx.body.get('tool_id',r['tool_id'])
        if pid is not None and (type(pid)!=int or not ctx.db.one('SELECT id FROM people WHERE id=?',(pid,))): raise ApiError(400,'Choose an existing person.')
        if tid is not None and not ctx.db.one('SELECT id FROM tools WHERE id=? AND archived=0',(tid,)): raise ApiError(400,'Choose an active catalogue tool.')
        ctx.db.x('INSERT INTO hub_attribution_changes(report_id,actor,ts,reason,previous_person_id,person_id,previous_tool_id,tool_id) VALUES(?,?,?,?,?,?,?,?)',(r['id'],ctx.admin['username'],time.time(),reason,r['person_id'],pid,r['tool_id'],tid))
        ctx.db.x('UPDATE hub_reports SET person_id=?,tool_id=? WHERE id=?',(pid,tid,r['id']))
        ctx.audit('corrected adoption association',str(r['id']),reason=reason,before={'person_id':r['person_id'],'tool_id':r['tool_id']},after={'person_id':pid,'tool_id':tid},correlation=f"hub-report:{r['id']}")
    refresh_management(ctx,r['created'],ctx.admin['username'])
    return reporting.detail(ctx.gw,r['id'])


@admin.route('PUT', r'/hub/business/settings', area=('govern','money'))
def settings(ctx):
    # Shared Drive is a company setting; rates are allocations and never rewrite declarations.
    from . import authz
    if 'drive_folder' in ctx.body and not authz.can(ctx.admin,'govern'): raise ApiError(403,'Governance permission required.')
    rates=any(k in ctx.body for k in ('hourly_rate_usd','usd_ugx'))
    if rates and not authz.can(ctx.admin,'money'): raise ApiError(403,'Money permission required.')
    changes={}
    if 'drive_folder' in ctx.body: changes['hub_drive_folder']=reporting.safe_url(ctx.body['drive_folder'])
    if 'hourly_rate_usd' in ctx.body: changes['hub_hourly_rate_usd']=reporting.number(ctx.body['hourly_rate_usd'],'hourly_rate_usd')
    if 'usd_ugx' in ctx.body:
        rate=reporting.number(ctx.body['usd_ugx'],'usd_ugx')
        if rate==0:raise ApiError(400,'Currency conversion requires a positive rate, or blank for unknown.')
        changes['hub_usd_ugx']=rate
    if rates:
        reason=ctx.body.get('reason')
        if not isinstance(reason,str) or not reason.strip() or len(reason)>1000:raise ApiError(400,'Explain the administrative financial assumptions.')
        changes.update(hub_finance_asof=time.time(),hub_finance_basis=reason.strip())
    with ctx.db.tx():
        for key,value in changes.items(): ctx.db.set_setting(key,'' if value is None else value)
        ctx.audit('changed business configuration','business',after=changes)
    return {'saved':True}


@staff.route('GET', r'/hub/plans')
@admin.route('GET', r'/hub/plans')
def plans(ctx):
    return {'items':ctx.db.q('SELECT p.*,t.name AS tool_name FROM hub_tool_plans p JOIN tools t ON t.id=p.tool_id WHERE p.archived=0 ORDER BY t.name,p.monthly_usd'),
            'basis':'Administrator-published pricing reference, dated when entered; not a current vendor quote or entitlement.'}


@admin.route('POST', r'/hub/plans', area='money')
def publish_plan(ctx):
    tool=ctx.db.one('SELECT id FROM tools WHERE id=? AND archived=0',(ctx.body.get('tool_id'),))
    name=str(ctx.body.get('name') or '').strip()
    url=reporting.safe_url(ctx.body.get('pricing_url'))
    if not tool or not name or len(name)>200 or not url:
        raise ApiError(400,'A pricing reference needs a catalogue tool, plan name and official pricing URL.')
    monthly=reporting.number(ctx.body.get('monthly_usd'),'monthly_usd')
    if monthly is None: raise ApiError(400,'Enter the published monthly amount, including known zero.')
    unit=str(ctx.body.get('usage_unit') or '').strip()
    if len(unit)>100 or type(ctx.body.get('flat_rate',False)) is not bool: raise ApiError(400,'Invalid pricing unit or flat-rate flag.')
    fields=(tool['id'],name,monthly,reporting.number(ctx.body.get('included'),'included'),reporting.number(ctx.body.get('unit_rate_usd'),'unit_rate_usd'),unit,int(ctx.body.get('flat_rate',False)),url,time.time(),ctx.admin['username'])
    with ctx.db.tx():
        before=ctx.db.one('SELECT * FROM hub_tool_plans WHERE tool_id=? AND name=?',(tool['id'],name))
        ctx.db.x('INSERT INTO hub_tool_plans(tool_id,name,monthly_usd,included,unit_rate_usd,usage_unit,flat_rate,pricing_url,checked,actor) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(tool_id,name) DO UPDATE SET monthly_usd=excluded.monthly_usd,included=excluded.included,unit_rate_usd=excluded.unit_rate_usd,usage_unit=excluded.usage_unit,flat_rate=excluded.flat_rate,pricing_url=excluded.pricing_url,checked=excluded.checked,actor=excluded.actor,archived=0',fields)
        row=ctx.db.one('SELECT * FROM hub_tool_plans WHERE tool_id=? AND name=?',(tool['id'],name))
        ctx.audit('published tool pricing reference',str(row['id']),before=before,after=row)
    return row


@admin.route('POST', r'/hub/plans/(?P<pid>\d+)/archive', area='money')
def archive_plan(ctx,pid):
    if not ctx.db.one('SELECT id FROM hub_tool_plans WHERE id=?',(pid,)):raise ApiError(404,'Plan not found.')
    with ctx.db.tx():
        ctx.db.x('UPDATE hub_tool_plans SET archived=1 WHERE id=?',(pid,))
        ctx.audit('archived pricing reference',pid)
    return {'archived':True}


@admin.route('GET', r'/hub/delivery')
def delivery_queue(ctx):
    state=ctx.arg('state','');args=[];where=''
    if state:
        if state not in ('not_configured','pending','sent','failed'): raise ApiError(400,'Choose a valid delivery state.')
        where=' WHERE n.email_state=?';args.append(state)
    offset=max(0,ctx.arg('offset',0,int));limit=30
    rows=ctx.db.q('SELECT n.id,n.title,n.href,n.created,n.email_state,n.emailed,n.attempts,p.name AS recipient FROM hub_notifications n JOIN people p ON p.id=n.person_id'+where+' ORDER BY n.id DESC LIMIT ? OFFSET ?',(*args,limit,offset))
    return {'items':rows,'offset':offset,'limit':limit,'total':ctx.db.scalar('SELECT COUNT(*) FROM hub_notifications n'+where,args)}


@admin.route('POST', r'/hub/delivery/(?P<nid>\d+)/retry', area='govern')
def retry_delivery(ctx,nid):
    import os
    with ctx.db.tx():
        row=ctx.db.one('SELECT email_state FROM hub_notifications WHERE id=?',(nid,))
        if not row: raise ApiError(404,'Delivery record not found.')
        if row['email_state']=='sent': raise ApiError(409,'A successful delivery is not resent.')
        state='pending' if os.environ.get('GATEWAY_SMTP_HOST') else 'not_configured'
        ctx.db.x('UPDATE hub_notifications SET attempts=0,email_state=? WHERE id=?',(state,nid))
        ctx.audit('queued Hub notification retry',nid,after={'delivery':state})
    return {'ok':True,'email_state':state,'sent':False}


@admin.route('POST',r'/hub/procurement/(?P<rid>\d+)/pricing',area='money')
def procurement_pricing(ctx,rid):
    allowed={'version','reason','estimated_monthly_cost','estimated_one_time_cost','requested_plan','currency'}
    if set(ctx.body)-allowed:raise ApiError(400,'Only financial procurement fields can be corrected here.')
    reason=ctx.body.get('reason')
    if not isinstance(reason,str) or not reason.strip() or len(reason)>1000:raise ApiError(400,'Explain the procurement pricing correction.')
    fields={}
    for key in ('estimated_monthly_cost','estimated_one_time_cost'):
        if key in ctx.body:fields[key]=reporting.number(ctx.body[key],key)
    for key in ('requested_plan','currency'):
        if key in ctx.body:
            value=ctx.body[key]
            if not isinstance(value,str) or len(value)>(300 if key=='requested_plan' else 3):raise ApiError(400,'Invalid procurement pricing text.')
            if key=='currency' and not __import__('re').fullmatch('[A-Z]{3}',value):raise ApiError(400,'Use a three-letter currency code.')
            fields[key]=value.strip()
    if not fields:raise ApiError(400,'Provide the financial fields being corrected.')
    with ctx.db.tx():
        r=ctx.db.one('SELECT * FROM procurement_requests WHERE id=?',(rid,))
        if not r:raise ApiError(404,'Procurement request not found.')
        if ctx.body.get('version')!=r['proposal_version']:raise ApiError(409,'Procurement pricing changed. Reload before editing.')
        if r['state'] in ('purchased','rejected'):raise ApiError(409,'Finalised procurement pricing cannot be silently changed. Record a follow-up decision.')
        now=time.time()
        if r['proposal_version']==0 and not ctx.db.one('SELECT version FROM procurement_versions WHERE request_id=? AND version=0',(rid,)):
            ctx.db.x('INSERT INTO procurement_versions VALUES(?,?,?,?,?,?)',(rid,0,r['submitter_email'],now,'Preserved proposal before first Hub financial correction; imported provenance remains separate',json.dumps(r,sort_keys=True)))
        if r['state']=='approved':
            fields['state']='reviewed'
            ctx.db.x('INSERT INTO procurement_reviews(request_id,actor,ts,previous_state,state,note) VALUES(?,?,?,?,?,?)',(rid,ctx.admin['username'],now,'approved','reviewed','Pricing changed; approval must be renewed. '+reason.strip()))
        fields.update(proposal_version=r['proposal_version']+1,financial_basis='administrative estimate',updated=now)
        ctx.db.x('UPDATE procurement_requests SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),rid))
        current=ctx.db.one('SELECT * FROM procurement_requests WHERE id=?',(rid,))
        ctx.db.x('INSERT INTO procurement_versions VALUES(?,?,?,?,?,?)',(rid,current['proposal_version'],ctx.admin['username'],now,reason.strip(),json.dumps(current,sort_keys=True)))
        ctx.audit('corrected procurement financial estimate',rid,reason=reason,before={'version':r['proposal_version']},after={'version':current['proposal_version']})
        if r['person_id']:reporting.notify_person(ctx.gw,r['person_id'],f'procurement:{rid}:pricing:{current["proposal_version"]}','Your procurement estimate was updated',f'#/requests?view=procurement&request={rid}')
    refresh_management(ctx,r['created'],ctx.admin['username'])
    return current


@admin.route('POST',r'/hub/procurement/(?P<rid>\d+)/attribution',area='govern')
def procurement_attribution(ctx,rid):
    reason=ctx.body.get('reason')
    if not isinstance(reason,str) or not reason.strip() or len(reason)>1000:raise ApiError(400,'Explain the association correction.')
    with ctx.db.tx():
        r=ctx.db.one('SELECT * FROM procurement_requests WHERE id=?',(rid,))
        if not r:raise ApiError(404,'Procurement request not found.')
        if ctx.body.get('version')!=r['proposal_version']:raise ApiError(409,'The proposal changed. Reload before correcting attribution.')
        pid=ctx.body.get('person_id',r['person_id']);tid=ctx.body.get('tool_id',r['tool_id'])
        if pid is not None and (type(pid)!=int or not ctx.db.one('SELECT id FROM people WHERE id=?',(pid,))):raise ApiError(400,'Choose an existing staff member.')
        if tid is not None and not ctx.db.one('SELECT id FROM tools WHERE id=? AND archived=0',(tid,)):raise ApiError(400,'Choose an active catalogue tool.')
        if tid!=r['tool_id'] and r['state']=='purchased':raise ApiError(409,'A completed purchase needs a separate security review before changing its tool association.')
        now=time.time()
        if not ctx.db.one('SELECT version FROM procurement_versions WHERE request_id=? AND version=0',(rid,)):
            ctx.db.x('INSERT INTO procurement_versions VALUES(?,?,?,?,?,?)',(rid,0,r['submitter_email'],now,'Preserved proposal before first Hub correction; original import provenance is separate',json.dumps(r,sort_keys=True)))
        fields={'person_id':pid,'tool_id':tid,'proposal_version':r['proposal_version']+1,'updated':now}
        if r['state']=='approved' and (pid!=r['person_id'] or tid!=r['tool_id']):
            fields['state']='reviewed'
            ctx.db.x('INSERT INTO procurement_reviews(request_id,actor,ts,previous_state,state,note) VALUES(?,?,?,?,?,?)',(rid,ctx.admin['username'],now,'approved','reviewed','Association changed; review renewed. '+reason.strip()))
        ctx.db.x('UPDATE procurement_requests SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),rid))
        current=ctx.db.one('SELECT * FROM procurement_requests WHERE id=?',(rid,))
        ctx.db.x('INSERT INTO procurement_versions VALUES(?,?,?,?,?,?)',(rid,current['proposal_version'],ctx.admin['username'],now,reason.strip(),json.dumps(current,sort_keys=True)))
        ctx.audit('corrected procurement association',rid,reason=reason,before={'person_id':r['person_id'],'tool_id':r['tool_id']},after={'person_id':pid,'tool_id':tid})
    refresh_management(ctx,r['created'],ctx.admin['username'])
    return current
