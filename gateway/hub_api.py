"""Native staff and console workflows, registered in the existing authenticated dispatchers."""
import json
import time
from . import admin, reporting, staff
from .admin import ApiError


def _filters(ctx, personal=False):
    clauses, args = [], []
    if personal:
        clauses.append('person_id=?'); args.append(ctx.person['id'])
    for param, column in (('kind','kind'), ('week','week_start'), ('department','department'), ('person','person_id'),
                          ('tool','tool_id'), ('state','state'), ('reconciliation','reconciliation')):
        value = ctx.arg(param)
        if value is not None and (not personal or param not in ('person','department')):
            if param == 'week':
                reporting.bounds(ctx.gw, value)
            if param == 'state' and value in ('pending','completed','awaiting_review'):
                states={'pending':('draft','returned'),'completed':('submitted','resubmitted','reviewed','confirmed'),'awaiting_review':('submitted','resubmitted')}[value]
                clauses.append(column+' IN ('+','.join('?' for _ in states)+')');args.extend(states)
            else:
                clauses.append(column+'=?'); args.append(value)
    if ctx.arg('evidence'):
        clauses.append('evidence_id IN (SELECT id FROM weekly_evidence WHERE completeness=?)'); args.append(ctx.arg('evidence'))
    if ctx.arg('q'):
        clauses.append('(tool_name LIKE ? OR submitter_name LIKE ? OR department LIKE ?)')
        args.extend(['%'+ctx.arg('q')[:200]+'%']*3)
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    return where, args


def _list(ctx, personal=False):
    reporting.compile_closed(ctx.gw)
    where, args = _filters(ctx, personal)
    limit = max(1, min(100, ctx.arg('limit', 30, int)))
    offset = max(0, ctx.arg('offset', 0, int))
    fields = 'id,kind,person_id,tool_id,week_start,department,submitter_name,tool_name,state,created,updated,submitted,version,reconciliation,evidence_id'
    rows = ctx.db.q('SELECT '+fields+' FROM hub_reports'+where+' ORDER BY COALESCE(week_start,created) DESC,id DESC LIMIT ? OFFSET ?', (*args,limit,offset))
    summary = ctx.db.q('SELECT state,COUNT(*) AS count FROM hub_reports'+where+' GROUP BY state', args)
    for row in rows:
        if row['week_start']:
            frozen=ctx.db.one('SELECT week_start,starts,ends,timezone FROM weekly_evidence WHERE id=?',(row['evidence_id'],))
            row['period'] = reporting.evidence_period(frozen) if frozen else reporting.bounds(ctx.gw, row['week_start'])
            row['deadline'] = row['period']['ends']
            row['overdue'] = row['state'] in reporting.OPEN_STATES
        row['evidence'] = ctx.db.one('SELECT api_requests,launches,access_events,active_days,completeness FROM weekly_evidence WHERE id=?', (row['evidence_id'],)) if row['evidence_id'] else None
    return {'items': rows, 'total': ctx.db.scalar('SELECT COUNT(*) FROM hub_reports'+where, args),
            'summary': {r['state']: r['count'] for r in summary}, 'offset': offset, 'limit': limit,
            'timezone': ctx.gw.settings.company_timezone}


@staff.route('GET', r'/hub/reports')
def staff_reports(ctx):
    return _list(ctx, True)


@staff.route('GET', r'/hub/reports/(?P<rid>\d+)')
def staff_detail(ctx, rid):
    return reporting.detail(ctx.gw, int(rid), ctx.person['id'])


@staff.route('PUT', r'/hub/reports/(?P<rid>\d+)')
def staff_save(ctx, rid):
    return reporting.save(ctx.gw, ctx.person['id'], int(rid), ctx.body)


@staff.route('POST', r'/hub/reports/(?P<rid>\d+)/submit')
def staff_submit(ctx, rid):
    return reporting.save(ctx.gw, ctx.person['id'], int(rid), ctx.body, True)


@staff.route('POST', r'/hub/adoption')
def adoption(ctx):
    tid = str(ctx.body.get('tool_id') or '')
    tool = ctx.db.one('SELECT * FROM tools WHERE id=? AND archived=0', (tid,))
    if not tool:
        raise ApiError(400, 'Choose an existing catalogue tool. Use procurement to propose a new tool.')
    now, p = time.time(), ctx.person
    rid = ctx.db.x('INSERT INTO hub_reports(kind,person_id,tool_id,department,submitter_name,submitter_email,tool_name,official_url,category,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   ('adoption',p['id'],tid,p['department'],p['name'],p['email'],tool['name'],tool['url'],tool['category'],now,now)).lastrowid
    ctx.gw.audit(p['email'],'started an adoption report',str(rid),correlation=f'hub-report:{rid}')
    return reporting.detail(ctx.gw,rid,p['id'])


@admin.route('GET', r'/hub/reports')
def admin_reports(ctx):
    return _list(ctx)


@admin.route('GET', r'/hub/reports/(?P<rid>\d+)')
def admin_detail(ctx,rid):
    ctx.audit('opened a Hub report',rid,correlation=f'hub-report:{rid}')
    return reporting.detail(ctx.gw,int(rid))


@admin.route('POST', r'/hub/reports/(?P<rid>\d+)/review', area='govern')
def admin_review(ctx,rid):
    return reporting.review(ctx,int(rid))


@admin.route('POST', r'/hub/override', area='emergency')
def override(ctx):
    reason = str(ctx.body.get('reason') or '').strip()
    if not reason or len(reason)>500:
        raise ApiError(400,'An emergency reporting override needs a reason up to 500 characters.')
    try:
        pid=int(ctx.body.get('person_id')); tid=str(ctx.body.get('tool_id') or '')
        hours=float(ctx.body.get('hours',1))
    except (ValueError,TypeError):
        raise ApiError(400,'Specify a person, tool and duration.')
    if not 0<hours<=24 or not ctx.db.one('SELECT id FROM people WHERE id=?',(pid,)) or not ctx.db.one('SELECT id FROM tools WHERE id=?',(tid,)):
        raise ApiError(400,'Choose an existing person and tool, and a duration up to 24 hours.')
    now=time.time()
    with ctx.db.tx():
        oid=ctx.db.x('INSERT INTO weekly_overrides(person_id,tool_id,starts,expires,admin_id,reason) VALUES(?,?,?,?,?,?)',
                    (pid,tid,now,now+hours*3600,ctx.admin['id'],reason)).lastrowid
        ctx.audit('authorised an emergency reporting override',str(oid),reason=reason,
                  after={'person_id':pid,'tool_id':tid,'starts':now,'expires':now+hours*3600},correlation=f'weekly-override:{oid}')
    return {'id':oid,'expires':now+hours*3600,'scope':{'person_id':pid,'tool_id':tid},'note':'Entitlement, suspension, subscription and emergency-stop checks still apply.'}


@admin.route('GET', r'/hub/management')
def management(ctx):
    start=ctx.arg('week')
    if not start:
        from datetime import date,timedelta
        start=(date.fromisoformat(reporting.week(ctx.gw)['week_start'])-timedelta(days=7)).isoformat()
    reporting.bounds(ctx.gw,start)
    reporting.compile_closed(ctx.gw)
    row=ctx.db.one('SELECT * FROM weekly_management_snapshots WHERE week_start=? ORDER BY revision DESC LIMIT 1',(start,))
    if not row:
        reporting.management_snapshot(ctx.gw,start)
        row=ctx.db.one('SELECT * FROM weekly_management_snapshots WHERE week_start=? ORDER BY revision DESC LIMIT 1',(start,))
    wanted=ctx.arg('revision',None,int)
    if wanted is not None:
        row=ctx.db.one('SELECT * FROM weekly_management_snapshots WHERE week_start=? AND revision=?',(start,wanted))
        if not row:
            raise ApiError(404,'Management snapshot not found.')
    return {'id':row['id'],'created':row['created'],'revision':row['revision'],'actor':row['actor'],
            'snapshot':json.loads(row['snapshot_json']),
            'history':ctx.db.q('SELECT id,revision,created,actor FROM weekly_management_snapshots WHERE week_start=? ORDER BY revision DESC',(start,))}


@admin.route('POST', r'/hub/management', area=('govern','money'))
def refresh_management(ctx):
    start=ctx.body.get('week')
    reporting.bounds(ctx.gw,start)
    revision=reporting.management_snapshot(ctx.gw,start,ctx.admin['username'])
    ctx.audit('compiled a weekly management snapshot',start,after={'revision':revision})
    return {'week_start':start,'revision':revision}


@admin.route('GET', r'/hub/export')
def export(ctx):
    start=ctx.arg('week')
    reporting.bounds(ctx.gw,start)
    data=management(ctx)
    evidence={e['id']:e for e in data['snapshot']['evidence']}
    rows=[{**evidence.get(r['evidence_id'],{}),**r,'week_start':data['snapshot']['period']['week_start']} for r in data['snapshot']['reports']]
    fields=('id','week_start','submitter_name','department','tool_name','state','reconciliation','api_requests','api_success','api_failed','launches','access_events','tab_open_seconds','active_days','estimated_api_cost','completeness','manual_hours','ai_hours','manual_cost','ai_cost','subscription_cost','extra_credits','currency','revenue','impact')
    ctx.audit('exported weekly Hub reports',start,detail=f'{len(rows)} reports')
    return reporting.csv_bytes(rows,fields),'text/csv; charset=utf-8',{'Content-Disposition':f'attachment; filename="hub-week-{start}.csv"','Cache-Control':'no-store',**__import__('gateway.server',fromlist=['CONSOLE_HEADERS']).CONSOLE_HEADERS}


def procurement_values(body):
    values={}
    for name in ('tool_name','official_url','category','purchase_type','reason','business_impact','requested_plan','currency'):
        value=body.get(name)
        if value is not None and not isinstance(value,str):
            raise ApiError(400,f'{name} must be text.')
        values[name]=str(value or '').strip()
        if len(values[name])>4000:
            raise ApiError(400,f'{name} is too long.')
    values['official_url']=reporting.safe_url(values['official_url'])
    values['currency']=values['currency'] or 'USD'
    if values['purchase_type'] not in ('new_tool','subscription','licence','credits','other') or not values['tool_name'] or not values['reason']:
        raise ApiError(400,'A request needs a tool, purchase type and business reason.')
    if not __import__('re').fullmatch('[A-Z]{3}',values['currency']):
        raise ApiError(400,'Currency must be a three-letter code.')
    for name in ('estimated_monthly_cost','estimated_one_time_cost'):
        values[name]=reporting.number(body.get(name),name)
    return values


@staff.route('POST', r'/hub/procurement')
def procurement_create(ctx):
    values=procurement_values(ctx.body)
    tid=ctx.body.get('tool_id') or None
    if tid and not ctx.db.one('SELECT id FROM tools WHERE id=?',(tid,)):
        raise ApiError(400,'Unknown catalogue tool.')
    p,now=ctx.person,time.time()
    values.update(person_id=p['id'],tool_id=tid,submitter_name=p['name'],submitter_email=p['email'],department=p['department'],created=now,updated=now)
    with ctx.db.tx():
        rid=ctx.db.x(f"INSERT INTO procurement_requests({','.join(values)}) VALUES({','.join('?' for _ in values)})",tuple(values.values())).lastrowid
        ctx.gw.audit(p['email'],'submitted a procurement request',str(rid),correlation=f'procurement:{rid}')
        reporting.notify_person(ctx.gw,p['id'],f'procurement:{rid}','Your procurement request was submitted','#/requests?view=procurement')
    return ctx.db.one('SELECT * FROM procurement_requests WHERE id=?',(rid,))


def _procurement_list(ctx,personal=False):
    clauses,args=[],[]
    if personal:
        clauses.append('person_id=?');args.append(ctx.person['id'])
    for param in ('state','department'):
        if ctx.arg(param) and (not personal or param!='department'):
            clauses.append(param+'=?');args.append(ctx.arg(param))
    if ctx.arg('q'):
        clauses.append('(tool_name LIKE ? OR submitter_name LIKE ?)');args.extend(['%'+ctx.arg('q')[:200]+'%']*2)
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    offset=max(0,ctx.arg('offset',0,int));limit=max(1,min(100,ctx.arg('limit',30,int)))
    return {'items':ctx.db.q('SELECT * FROM procurement_requests'+where+' ORDER BY id DESC LIMIT ? OFFSET ?',(*args,limit,offset)),
            'total':ctx.db.scalar('SELECT COUNT(*) FROM procurement_requests'+where,args),'offset':offset,'limit':limit}


@staff.route('GET', r'/hub/procurement')
def procurement_mine(ctx):
    return _procurement_list(ctx,True)


@admin.route('GET', r'/hub/procurement')
def procurement_all(ctx):
    return _procurement_list(ctx)


@admin.route('GET', r'/hub/procurement/(?P<rid>\d+)')
def procurement_detail(ctx,rid):
    row=ctx.db.one('SELECT * FROM procurement_requests WHERE id=?',(rid,))
    if not row:
        raise ApiError(404,'Procurement request not found.')
    row['history']=ctx.db.q('SELECT * FROM procurement_reviews WHERE request_id=? ORDER BY id',(rid,))
    return row


@admin.route('POST', r'/hub/procurement/(?P<rid>\d+)/review', area=('govern','money'))
def procurement_review(ctx,rid):
    state=ctx.body.get('state'); note=str(ctx.body.get('note') or '').strip()
    if state not in ('reviewed','approved','rejected','purchased') or len(note)>8000:
        raise ApiError(400,'Choose a valid procurement decision.')
    if state=='rejected' and not note:
        raise ApiError(400,'Explain why this request was rejected.')
    if state=='purchased':
        ctx.require('money');ctx.require('trust')
        if ctx.body.get('security_checked') is not True or ctx.body.get('subscription_checked') is not True:
            raise ApiError(400,'Record successful security and subscription checks before completing a purchase.')
    now=time.time()
    with ctx.db.tx():
        row=ctx.db.one('SELECT * FROM procurement_requests WHERE id=?',(rid,))
        if not row:
            raise ApiError(404,'Procurement request not found.')
        allowed={'submitted':('reviewed','approved','rejected'),'reviewed':('approved','rejected'), 'approved':('purchased','rejected')}
        if state not in allowed.get(row['state'],()):
            raise ApiError(409,'This request cannot move to that state.')
        ctx.db.x('UPDATE procurement_requests SET state=?,admin_note=?,reviewer_id=?,updated=?,security_checked=?,subscription_checked=? WHERE id=?',
                 (state,note,ctx.admin['id'],now,1 if state=='purchased' else row['security_checked'],1 if state=='purchased' else row['subscription_checked'],rid))
        ctx.db.x('INSERT INTO procurement_reviews(request_id,actor,ts,previous_state,state,note) VALUES(?,?,?,?,?,?)',(rid,ctx.admin['username'],now,row['state'],state,note))
        ctx.audit('reviewed a procurement request',rid,before={'state':row['state']},after={'state':state,'note':note},correlation=f'procurement:{rid}')
        if row['person_id']:
            reporting.notify_person(ctx.gw,row['person_id'],f'procurement:{rid}:{state}',f'Your procurement request is {state}','#/requests?view=procurement')
    period=reporting.week(ctx.gw,row['created'])
    if period['ends']<=now:
        reporting.management_snapshot(ctx.gw,period['week_start'],ctx.admin['username'])
    return {'ok':True,'state':state,'access_granted':False,'next_action':'Configure or verify the subscription and separately assign the tool in People and access.'}


@staff.route('GET', r'/hub/notifications')
def notifications(ctx):
    return {'items':ctx.db.q('SELECT id,title,href,created,read,email_state FROM hub_notifications WHERE person_id=? ORDER BY id DESC LIMIT 100',(ctx.person['id'],))}


@staff.route('POST', r'/hub/notifications/(?P<nid>\d+)/read')
def read_notification(ctx,nid):
    ctx.db.x('UPDATE hub_notifications SET read=? WHERE id=? AND person_id=?',(time.time(),nid,ctx.person['id']))
    return {'ok':True}


@staff.route('GET', r'/hub/activity')
def staff_activity(ctx):
    pid=ctx.person['id'];limit=max(1,min(100,ctx.arg('limit',30,int)));offset=max(0,ctx.arg('offset',0,int))
    source=ctx.arg('source','all')
    clauses=[];args=[]
    for name,query in (
        ('api',"SELECT ts,'api' AS source,COALESCE(hub_tool_id,provider) AS tool,outcome,model,cost AS estimated_cost FROM requests WHERE person_id=?"),
        ('launch',"SELECT ts,'launch' AS source,tool_id AS tool,outcome,NULL AS model,NULL AS estimated_cost FROM launches WHERE person_id=?"),
        ('website',"SELECT started AS ts,'website' AS source,tool_id AS tool,outcome,NULL AS model,NULL AS estimated_cost FROM site_usage WHERE person_id=?")):
        if source in ('all',name):clauses.append(query);args.append(pid)
    if not clauses:raise ApiError(400,'Choose a valid activity source.')
    sql=' UNION ALL '.join(clauses)
    return {'items':ctx.db.q('SELECT * FROM ('+sql+') ORDER BY ts DESC LIMIT ? OFFSET ?',(*args,limit,offset)),
            'total':ctx.db.scalar('SELECT COUNT(*) FROM ('+sql+')',args),'offset':offset,'limit':limit}


@admin.route('GET', r'/hub/overview')
def weekly_overview(ctx):
    reporting.compile_closed(ctx.gw)
    where,args=_filters(ctx)
    if not ctx.arg('kind'):
        where+=(' AND ' if where else ' WHERE ')+"kind='weekly'"
    summary=ctx.db.q('SELECT state,COUNT(*) AS n FROM hub_reports'+where+' GROUP BY state',args)
    comparison=ctx.db.q('SELECT reconciliation,COUNT(*) AS n FROM hub_reports'+where+' GROUP BY reconciliation',args)
    ids='SELECT id FROM hub_reports'+where
    groups={}
    for key, identity in (('submitter_name','person_id'),('tool_name','tool_id'),('department','department')):
        groups[key]=ctx.db.q(f"SELECT r.{identity} AS identity, r.{key} AS name,COUNT(*) AS reports,SUM(r.state IN ('draft','returned')) AS outstanding,SUM(r.state IN ('submitted','resubmitted','reviewed','confirmed')) AS submitted,SUM(r.reconciliation='needs_review') AS needs_review,COALESCE(SUM(e.api_requests),0) AS api_requests,COALESCE(SUM(e.launches+e.access_events),0) AS access_events,SUM(e.estimated_api_cost) AS estimated_api_cost FROM hub_reports r LEFT JOIN weekly_evidence e ON e.id=r.evidence_id WHERE r.id IN ({ids}) GROUP BY r.{identity},r.{key} ORDER BY outstanding DESC,reports DESC LIMIT 1000",args)
    return {'states':{r['state']:r['n'] for r in summary},'reconciliation':{r['reconciliation']:r['n'] for r in comparison},'groups':groups}


@admin.route('GET', r'/hub/settings')
def hub_settings(ctx):
    return {'timezone':ctx.gw.settings.company_timezone,'reconciliation_tolerance':float(ctx.db.get_setting('weekly_reconciliation_tolerance','0.1')),
            'correction_policy':'A formally returned report blocks only its tool until resubmission. Review and confirmation are not required for ordinary access.',
            'identity_policy':'Exact @swangzavenue.com accounts, with the two explicitly approved owner/admin exceptions.'}


@admin.route('PUT', r'/hub/settings', area='govern')
def save_hub_settings(ctx):
    tolerance=reporting.number(ctx.body.get('reconciliation_tolerance'),'reconciliation_tolerance')
    if tolerance is None or tolerance>1:raise ApiError(400,'Tolerance must be between zero and one.')
    before=ctx.db.get_setting('weekly_reconciliation_tolerance','0.1')
    with ctx.db.tx():
        ctx.db.set_setting('weekly_reconciliation_tolerance',tolerance)
        ctx.audit('changed weekly reconciliation tolerance','weekly_reporting',before={'tolerance':before},after={'tolerance':tolerance})
    return hub_settings(ctx)
