"""Native, governed department-report access; never confers a tool entitlement."""
import time
from . import admin, business, reporting, staff
from .admin import ApiError


def departments(db):
    return [r['department'] for r in db.q("SELECT department FROM people WHERE department<>'' UNION SELECT department FROM hub_reports WHERE department<>'' ORDER BY department")]


def permitted(db,person,department):
    return bool(department and (department==person['department'] or db.one('SELECT person_id FROM hub_department_grants WHERE person_id=? AND department=? AND revoked IS NULL',(person['id'],department))))


@staff.route('GET',r'/hub/departments')
def directory(ctx):
    return {'items':[{'department':d,'available':permitted(ctx.db,ctx.person,d)} for d in departments(ctx.db)]}


@staff.route('GET',r'/hub/department-business')
def dashboard(ctx):
    department=ctx.arg('department','')
    if not permitted(ctx.db,ctx.person,department):raise ApiError(403,'An approved department-report scope is required.')
    return business.model(ctx,department_scope=department)


@staff.route('GET',r'/hub/department-reports/(?P<rid>\d+)')
def report(ctx,rid):
    row=ctx.db.one("SELECT department FROM hub_reports WHERE id=? AND kind='adoption' AND archived_at IS NULL AND state NOT IN ('draft','returned')",(rid,))
    if not row or not permitted(ctx.db,ctx.person,row['department']):raise ApiError(404,'Department declaration not found.')
    return reporting.detail(ctx.gw,int(rid))


def listing(ctx,personal=False):
    where=' WHERE person_id=?' if personal else '';args=[ctx.person['id']] if personal else []
    offset=max(0,ctx.arg('offset',0,int));limit=30
    rows=ctx.db.q('SELECT * FROM hub_department_requests'+where+' ORDER BY id DESC LIMIT ? OFFSET ?',(*args,limit,offset))
    for row in rows:
        row['departments']=[d['department'] for d in ctx.db.q('SELECT department FROM hub_department_request_scopes WHERE request_id=?',(row['id'],))]
        row['decisions']=ctx.db.q('SELECT actor,ts,state,note FROM hub_department_decisions WHERE request_id=? ORDER BY id',(row['id'],))
    return {'items':rows,'offset':offset,'limit':limit,'total':ctx.db.scalar('SELECT COUNT(*) FROM hub_department_requests'+where,args)}


@staff.route('GET',r'/hub/department-requests')
def own_requests(ctx):return listing(ctx,True)


@admin.route('GET',r'/hub/department-requests')
def all_requests(ctx):
    out=listing(ctx);out['grants']=ctx.db.q('SELECT g.*,p.name FROM hub_department_grants g JOIN people p ON p.id=g.person_id WHERE g.revoked IS NULL ORDER BY g.department,p.name');return out


@staff.route('POST',r'/hub/department-requests')
def request(ctx):
    scopes=ctx.body.get('departments');reason=ctx.body.get('reason')
    if not isinstance(scopes,list) or not 1<=len(scopes)<=20 or any(not isinstance(d,str) or d not in departments(ctx.db) for d in scopes):raise ApiError(400,'Choose existing departments.')
    if not isinstance(reason,str) or not reason.strip() or len(reason)>4000:raise ApiError(400,'Explain why department-report access is needed.')
    scopes=sorted(set(scopes));pid=ctx.person['id'];now=time.time()
    with ctx.db.tx():
        for pending in ctx.db.q("SELECT id FROM hub_department_requests WHERE person_id=? AND state IN ('submitted','reviewed')",(pid,)):
            old=[d['department'] for d in ctx.db.q('SELECT department FROM hub_department_request_scopes WHERE request_id=? ORDER BY department',(pending['id'],))]
            if old==scopes:return {'id':pending['id'],'state':'submitted','duplicate':True}
        rid=ctx.db.x('INSERT INTO hub_department_requests(person_id,submitter_name,submitter_email,reason,created,updated) VALUES(?,?,?,?,?,?)',(pid,ctx.person['name'],ctx.person['email'],reason.strip(),now,now)).lastrowid
        for d in scopes:ctx.db.x('INSERT INTO hub_department_request_scopes VALUES(?,?)',(rid,d))
        ctx.gw.audit(ctx.person['email'],'requested department report access',str(rid),detail=', '.join(scopes))
        reporting.notify_person(ctx.gw,pid,'department:'+str(rid),'Your department-report access request was submitted','#/requests?view=departments')
    return {'id':rid,'state':'submitted'}


@admin.route('POST',r'/hub/department-requests/(?P<rid>\d+)/review',area='govern')
def review(ctx,rid):
    state=ctx.body.get('state');note=ctx.body.get('note')
    if state not in ('reviewed','approved','rejected') or not isinstance(note,str) or not note.strip() or len(note)>4000:raise ApiError(400,'Choose a decision and explain it.')
    with ctx.db.tx():
        row=ctx.db.one('SELECT * FROM hub_department_requests WHERE id=?',(rid,))
        if not row:raise ApiError(404,'Department request not found.')
        if row['state'] not in ('submitted','reviewed') or row['state']==state:raise ApiError(409,'This request cannot move to that state.')
        if state=='approved' and not row['person_id']:raise ApiError(409,'Associate and verify the historical requester before granting access.')
        now=time.time()
        ctx.db.x('UPDATE hub_department_requests SET state=?,admin_note=?,reviewer_id=?,updated=? WHERE id=?',(state,note.strip(),ctx.admin['id'],now,rid))
        ctx.db.x('INSERT INTO hub_department_decisions(request_id,actor,ts,state,note) VALUES(?,?,?,?,?)',(rid,ctx.admin['username'],now,state,note.strip()))
        if state=='approved':
            for scope in ctx.db.q('SELECT department FROM hub_department_request_scopes WHERE request_id=?',(rid,)):
                ctx.db.x('INSERT INTO hub_department_grants(person_id,department,actor,granted) VALUES(?,?,?,?) ON CONFLICT(person_id,department) DO UPDATE SET actor=excluded.actor,granted=excluded.granted,revoked=NULL',(row['person_id'],scope['department'],ctx.admin['username'],now))
        ctx.audit('reviewed department report access',rid,reason=note.strip(),after={'state':state})
        if row['person_id']:reporting.notify_person(ctx.gw,row['person_id'],'department:'+str(rid)+':'+state,'Your department-report access request is '+state,'#/requests?view=departments')
    return {'state':state,'tool_access_granted':False}


@admin.route('POST',r'/hub/department-grants/revoke',area='govern')
def revoke(ctx):
    pid=ctx.body.get('person_id');dep=ctx.body.get('department');reason=ctx.body.get('reason')
    if not isinstance(reason,str) or not reason.strip() or len(reason)>1000:raise ApiError(400,'Explain the revocation.')
    with ctx.db.tx():
        if not ctx.db.one('SELECT person_id FROM hub_department_grants WHERE person_id=? AND department=? AND revoked IS NULL',(pid,dep)):raise ApiError(404,'Active department grant not found.')
        ctx.db.x('UPDATE hub_department_grants SET revoked=? WHERE person_id=? AND department=?',(time.time(),pid,dep))
        ctx.audit('revoked department report access',str(pid),reason=reason,detail=dep)
    return {'revoked':True}
