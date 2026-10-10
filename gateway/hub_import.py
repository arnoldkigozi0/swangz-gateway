"""Read-only Tracker export and backed-up, transactional import. Never writes to the Tracker."""
import argparse
from contextlib import closing
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from . import reporting
from .admin import ApiError
from .db import DB

UNIT_HOURS = {'sec':1/3600,'min':1/60,'h':1,'d':8,'wk':40,'mo':160,'yr':1920}


def timestamp(v):
    if not v:
        raise ApiError(400,'Missing submission date; supply a reviewed source correction.')
    try:
        n=datetime.fromisoformat(str(v).replace('Z','+00:00'))
        if n.tzinfo is None:
            raise ValueError()
        return n.timestamp()
    except ValueError:
        raise ApiError(400,'Submission date must include a timezone.')


def _name(v):
    return re.sub(r'[^a-z0-9]','',str(v).lower())


def _url(v):
    p=urlsplit(reporting.safe_url(v))
    return (p.hostname or '').lower().removeprefix('www.')+p.path.rstrip('/')


def match_tool(db,entry,mapping):
    mapped=mapping.get(entry['id']) or entry.get('gateway_tool_id')
    if mapped:
        row=db.one('SELECT * FROM tools WHERE id=?',(mapped,))
        if not row:
            raise ApiError(400,'Mapped catalogue tool does not exist.')
        return row
    name=_name(entry.get('toolName'))
    tools=db.q('SELECT * FROM tools')
    matches=[t for t in tools if name and _name(t['name'])==name]
    if not matches and entry.get('officialUrl'):
        url=_url(entry['officialUrl'])
        matches=[t for t in tools if t['url'] and _url(t['url'])==url]
    if len(matches)>1:
        raise ApiError(400,'Ambiguous catalogue match; provide an explicit source-ID to tool-ID mapping.')
    return matches[0] if matches else None


def _hours(entry,field):
    value=reporting.number(entry.get(field),field)
    unit=entry.get(field+'Unit') or 'h'
    if unit not in UNIT_HOURS:
        raise ApiError(400,'Unknown working-time unit.')
    return None if value is None else value*UNIT_HOURS[unit]


def entries_from(data):
    entries=data.get('entries') if isinstance(data,dict) else data
    if not isinstance(entries,list) or len(entries)>100000:
        raise ApiError(400,'Expected a Tracker entries array, with at most 100,000 records.')
    out=[]
    for item in entries:
        if not isinstance(item,dict):
            raise ApiError(400,'Tracker entries must be objects.')
        row=item.get('payload',item)
        if not isinstance(row,dict):
            raise ApiError(400,'Tracker payload must be an object.')
        row=dict(row)
        if item.get('payload') is not None:
            if item.get('id') and row.get('id') and item['id']!=row['id']:
                raise ApiError(400,'Backend and payload IDs disagree.')
            row['id']=item.get('id') or row.get('id')
        out.append(row)
    return out


def _prepare(db,entry,mapping):
    eid=entry.get('id')
    if not isinstance(eid,str) or not eid or len(eid)>200 or any(ord(c)<32 for c in eid):
        raise ApiError(400,'Entry needs a stable source ID.')
    if entry.get('isDemo'):
        return None
    tool=match_tool(db,entry,mapping)
    name=str(entry.get('toolName') or '').strip()
    if not name or len(name)>300:
        raise ApiError(400,'Missing or oversized tool name.')
    if entry.get('kind') not in (None,'tool','registry'):
        raise ApiError(400,'Legacy non-tool request requires separate governance reconciliation; it is not a procurement request.')
    if entry.get('kind')=='registry':
        if not tool:
            raise ApiError(400,'Registry item has no verified catalogue match; map it before importing.')
        updates={}
        for dest,source in (('url','officialUrl'),('category','category')):
            if not tool[dest] and entry.get(source):
                updates[dest]=reporting.safe_url(entry[source]) if dest=='url' else str(entry[source])[:100]
        return 'registry',tool['id'],updates,None
    if entry.get('tag','report') not in ('report','request'):
        raise ApiError(400,'Unknown Tracker entry tag.')
    email=str(entry.get('submittedByEmail') or '').strip().lower()
    people=db.q('SELECT id FROM people WHERE lower(email)=? AND email<>\'\'',(email,)) if email else []
    pid=people[0]['id'] if len(people)==1 else None
    if len(people)>1:
        raise ApiError(400,'Submitter matches multiple Gateway people.')
    if not entry.get('currency') and any(entry.get(k) not in (None,'') for k in ('tradCost','aiCost','toolMonthlyCost','extraCredits','revenueAmount')):
        raise ApiError(400,'Monetary history needs an explicit currency; legacy Tracker values may be UGX. Supply a reviewed source correction.')
    common={'person_id':pid,'tool_id':tool['id'] if tool else None,
            'submitter_name':str(entry.get('submittedBy') or '')[:300], 'submitter_email':email[:320],
            'department':str(entry.get('department') or '')[:200], 'tool_name':name,
            'official_url':reporting.safe_url(entry.get('officialUrl')),'category':str(entry.get('category') or '')[:100],
            'created':timestamp(entry.get('submittedAt')),'updated':timestamp(entry.get('updatedAt') or entry.get('submittedAt'))}
    if entry.get('tag')=='request':
        state={'new':'submitted','reviewed':'reviewed','approved':'approved','declined':'rejected'}.get(entry.get('requestStatus') or 'new')
        if not state:
            raise ApiError(400,'Unknown procurement state.')
        common.update(purchase_type='other',reason=str(entry.get('reason') or 'Historical Tracker procurement request')[:4000],
                      business_impact=str(entry.get('impact') or '')[:4000],requested_plan=str(entry.get('selectedPlanName') or '')[:300],
                      estimated_monthly_cost=reporting.number(entry.get('toolMonthlyCost'),'toolMonthlyCost'),
                      estimated_one_time_cost=reporting.number(entry.get('extraCredits'),'extraCredits'),
                      currency=entry.get('currency') or 'USD',state=state,admin_note=str(entry.get('adminNote') or '')[:8000])
        procurement_currency=common['currency']
        if not isinstance(procurement_currency,str) or not re.fullmatch('[A-Z]{3}',procurement_currency):
            raise ApiError(400,'Invalid historical currency.')
        return 'procurement',None,common,None
    claim={'usage_confirmation':'used', 'reason':str(entry.get('reason') or ''), 'impact':str(entry.get('impact') or ''),
           'manual_hours':_hours(entry,'tradTime'),'ai_hours':_hours(entry,'aiTime'), 'manual_cost':entry.get('tradCost'),
           'ai_cost':entry.get('aiCost'), 'subscription_cost':entry.get('toolMonthlyCost'), 'extra_credits':entry.get('extraCredits'),
           'revenue':entry.get('revenueAmount'),'revenue_description':entry.get('revenueDesc') or '',
           'frequency':entry.get('frequency'),'usage_amount':entry.get('usageAmount'),'usage_unit':entry.get('usageUnit') or '',
           'pricing_source':entry.get('usagePricingSource') or '', 'selected_plan':entry.get('selectedPlanName') or '',
           'usage_included':entry.get('usageIncluded'),'usage_unit_cost_usd':entry.get('usageUnitCostUSD'),
           'usage_cost_usd':entry.get('usageCostUSD'),'usage_flat_rate':entry.get('usageFlatRate'), 'currency':entry.get('currency') or 'USD',
           'projects':[{ 'name':p.get('name') or p.get('title') or 'Historical project','link':p.get('link') or '',
                         'description':p.get('description') or p.get('desc') or '', 'traditional':p.get('traditional') or '', 'ai_way':p.get('aiWay') or '', 'benefit':p.get('benefit') or ''} for p in entry.get('projects') or []]}
    claim=reporting.validate(claim)
    state={'new':'submitted','reviewed':'reviewed','confirmed':'confirmed','returned':'returned'}.get(entry.get('reportStatus') or 'new')
    if not state:
        raise ApiError(400,'Unknown historical report state.')
    common.update(kind='adoption',state=state,submitted=common['created'],version=1,
                  reviewer_note=str(entry.get('adminNote') or '')[:8000],reconciliation='insufficient_telemetry',
                  reconciliation_reason='Historical adoption report; not evidence of use in a particular week.',
                  **{k:v for k,v in claim.items() if k!='projects'})
    return 'adoption',None,common,claim


def import_entries(db,data,source='tracker',mapping=None,apply=False):
    entries=entries_from(data)
    summary={'source':source,'read':len(entries),'new':{'adoption':0,'procurement':0,'registry':0},'duplicates':0,'demo_skipped':0,
             'unmatched_people':0,'unmatched_tools':0,'email_domain_exceptions':0,'errors':[], 'applied':False}
    prepared=[];seen=set()
    from .config import Settings
    settings=Settings()
    for index,entry in enumerate(entries):
        try:
            if entry.get('id') in seen:
                raise ApiError(400,'Duplicate source ID in export.')
            seen.add(entry.get('id'))
            payload=json.dumps(entry,sort_keys=True,allow_nan=False)
            if len(payload.encode())>128000:
                raise ApiError(400,'Entry exceeds import size limit.')
            digest=hashlib.sha256(payload.encode()).hexdigest()
            prior=db.one('SELECT digest FROM tracker_imports WHERE source=? AND source_id=?',(source,entry.get('id')))
            if prior:
                if prior['digest']!=digest:
                    raise ApiError(409,'Previously imported source ID changed; reconcile explicitly rather than overwrite history.')
                summary['duplicates']+=1;continue
            item=_prepare(db,entry,mapping or {})
            if item is None:
                summary['demo_skipped']+=1;continue
            kind,_,fields,_=item
            summary['new'][kind]+=1
            if kind!='registry':
                summary['unmatched_people']+=fields['person_id'] is None
                summary['unmatched_tools']+=fields['tool_id'] is None
                summary['email_domain_exceptions']+=not settings.email_allowed(fields['submitter_email'])
            prepared.append((entry,digest,payload,item))
        except (ApiError,ValueError,TypeError,AttributeError) as exc:
            summary['errors'].append({'row':index+1,'error':str(exc)[:300]})
    if not apply or summary['errors']:
        return summary
    with db.tx():
        for entry,digest,payload,(kind,target,fields,claim) in prepared:
            if db.one('SELECT 1 FROM tracker_imports WHERE source=? AND source_id=?',(source,entry['id'])):
                raise ApiError(409,'Import state changed concurrently; rerun the dry run.')
            if kind=='registry':
                if fields:
                    db.x(f"UPDATE tools SET {','.join(k+'=?' for k in fields)} WHERE id=?",(*fields.values(),target))
            else:
                table='hub_reports' if kind=='adoption' else 'procurement_requests'
                target=db.x(f"INSERT INTO {table}({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",tuple(fields.values())).lastrowid
                if kind=='adoption':
                    for pos,p in enumerate(claim['projects']):
                        db.x('INSERT INTO hub_report_projects(report_id,position,name,link,description,traditional,ai_way,benefit) VALUES(?,?,?,?,?,?,?,?)',(target,pos,p['name'],p['link'],p['description'],p['traditional'],p['ai_way'],p['benefit']))
                    db.x('INSERT INTO hub_report_versions(report_id,version,submitted,actor,declaration_json,reconciliation,reconciliation_reason) VALUES(?,?,?,?,?,?,?)',
                         (target,1,fields['submitted'],fields['submitter_email'],json.dumps(claim,sort_keys=True),'insufficient_telemetry',fields['reconciliation_reason']))
            db.x('INSERT INTO tracker_imports(source,source_id,digest,kind,target_id,imported,original_json) VALUES(?,?,?,?,?,?,?)',
                 (source,entry['id'],digest,kind,str(target),time.time(),payload))
        db.x('INSERT INTO audit(ts,actor,action,target,detail) VALUES(?,?,?,?,?)',(time.time(),'import operator','imported Tracker history',source,json.dumps(summary['new'],sort_keys=True)))
    summary['applied']=True
    return summary


def backup(source,destination):
    path=Path(destination)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    with closing(sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True)) as src, closing(sqlite3.connect(path)) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('Backup integrity check failed.')
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'integrity':'ok'}


def supabase_export(destination):
    base=os.environ.get('TRACKER_SUPABASE_URL','').rstrip('/')
    secret=os.environ.get('TRACKER_SUPABASE_SERVICE_KEY','')
    parsed=urlsplit(base)
    if not secret or parsed.scheme!='https' or not parsed.hostname or not parsed.hostname.endswith('.supabase.co') or parsed.path or parsed.username or parsed.password:
        raise ValueError('Configure an authorised Supabase HTTPS URL and server-side credential outside source control.')
    from urllib.request import HTTPRedirectHandler,build_opener
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):
            raise ValueError('Export redirect refused to protect backend credentials.')
    opener=build_opener(NoRedirect())
    rows=[]
    for offset in range(0,100000,1000):
        req=Request(base+'/rest/v1/entries?select=id,payload,inserted_at,updated_at&order=id&limit=1000&offset='+str(offset),
                    headers={'apikey':secret,'Authorization':'Bearer '+secret,'Accept':'application/json'})
        with opener.open(req,timeout=30) as response:
            part=json.loads(response.read(128*1024*1024))
        if not isinstance(part,list):
            raise ValueError('Backend export did not return an entries array.')
        rows.extend(part)
        if len(part)<1000:
            break
    else:
        raise ValueError('Export exceeded the configured record limit; no truncated export was written.')
    fd=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(rows,f)
    return len(rows)


def main():
    parser=argparse.ArgumentParser(description='Safe Tracker-to-Hub migration. Defaults to a non-mutating dry run.')
    parser.add_argument('--database');parser.add_argument('--file');parser.add_argument('--mapping');parser.add_argument('--source',default='tracker')
    parser.add_argument('--apply',action='store_true');parser.add_argument('--backup');parser.add_argument('--summary',required=True)
    parser.add_argument('--export-supabase')
    args=parser.parse_args()
    if args.export_supabase:
        count=supabase_export(args.export_supabase)
        fd=os.open(args.summary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f:
            json.dump({'exported':count,'read_only':True},f,indent=2)
        return
    if not args.database or not args.file:
        parser.error('--database and --file are required for import.')
    if args.apply and not args.backup:
        parser.error('--apply requires --backup pointing to a new backup file.')
    data=json.loads(Path(args.file).read_text());mapping=json.loads(Path(args.mapping).read_text()) if args.mapping else {}
    with tempfile.TemporaryDirectory(prefix='hub-import-preflight-') as tmp:
        scratch=Path(tmp)/'gateway.db'
        backup(args.database,scratch)
        dry=DB(str(scratch))
        try:
            summary=import_entries(dry,data,args.source,mapping)
        finally:
            dry.close()
        if args.apply and not summary['errors']:
            verified=backup(args.database,args.backup)
            db=DB(args.database)
            try:
                summary=import_entries(db,data,args.source,mapping,True)
                summary['backup']=verified
            finally:
                db.close()
        summary['mode']='apply' if args.apply else 'dry_run'
        fd=os.open(args.summary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f:
            json.dump(summary,f,indent=2)
        print(json.dumps({k:v for k,v in summary.items() if k not in ('backup','errors')}))
        if summary['errors']:
            raise SystemExit('Validation errors: no Tracker records imported. Read the private reconciliation summary.')


if __name__=='__main__':
    main()
