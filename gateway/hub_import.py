"""Read-only Tracker export and backed-up, transactional import. Never writes to the Tracker."""
import argparse
from contextlib import closing
import hashlib
import json
import os
import re
import sqlite3
import socket
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


def business_claim(entry):
    claim={'usage_confirmation':'used' if entry.get('tag')!='request' else None, 'reason':str(entry.get('reason') or ''), 'impact':str(entry.get('impact') or ''),
           'manual_hours':_hours(entry,'tradTime'),'ai_hours':_hours(entry,'aiTime'), 'manual_cost':entry.get('tradCost'),
           'ai_cost':entry.get('aiCost'), 'subscription_cost':entry.get('toolMonthlyCost'), 'extra_credits':entry.get('extraCredits'),
           'revenue':entry.get('revenueAmount'),'revenue_description':entry.get('revenueDesc') or '',
           'frequency':entry.get('frequency'),'usage_amount':entry.get('usageAmount'),'usage_unit':entry.get('usageUnit') or '',
           'pricing_source':entry.get('usagePricingSource') or '', 'selected_plan':entry.get('selectedPlanName') or '',
           'usage_included':entry.get('usageIncluded'),'usage_unit_cost_usd':entry.get('usageUnitCostUSD'),
           'usage_cost_usd':entry.get('usageCostUSD'),'usage_flat_rate':entry.get('usageFlatRate'), 'currency':entry.get('currency') or 'USD','manual_unit':entry.get('tradTimeUnit') or 'h','ai_unit':entry.get('aiTimeUnit') or 'h','frequency_period':'month','adoption_stage':{'Requesting (need to invest)':'exploring','Piloting':'piloting','In Active Use':'adopted','Scaling Across Team':'scaling'}.get(entry.get('status'),''),
           'projects':[{ 'name':p.get('name') or p.get('title') or '','link':p.get('link') or '',
                         'description':p.get('description') or p.get('desc') or '', 'traditional':p.get('traditional') or '', 'ai_way':p.get('aiWay') or '', 'benefit':p.get('benefit') or ''} for p in entry.get('projects') or []]}
    claim=reporting.validate(claim)
    return claim


def _prepare(db,entry,mapping):
    eid=entry.get('id')
    if not isinstance(eid,str) or not eid or len(eid)>200 or any(ord(c)<32 for c in eid):
        raise ApiError(400,'Entry needs a stable source ID.')
    if entry.get('isDemo'):
        return None
    if entry.get('kind')=='access':
        # The old client encoded scopes in a display string. Require reviewed scopes instead of guessing.
        scopes=entry.get('reviewed_departments')
        from .departments import departments
        if not isinstance(scopes,list) or not scopes or len(scopes)>20 or any(not isinstance(d,str) or d not in departments(db) for d in scopes):
            raise ApiError(400,'Legacy department access needs explicit reviewed_departments matching existing company departments.')
        email=str(entry.get('submittedByEmail') or '').strip().lower()
        person=db.q('SELECT id FROM people WHERE lower(email)=? AND email<>\'\'',(email,)) if email else []
        if len(person)>1: raise ApiError(400,'Ambiguous historical requester.')
        state={'new':'submitted','reviewed':'reviewed','approved':'approved','declined':'rejected'}.get(entry.get('requestStatus') or 'new')
        reason=str(entry.get('reason') or '').strip()
        if not state or not reason or len(reason)>4000: raise ApiError(400,'Invalid department request lifecycle or reason.')
        fields={'person_id':person[0]['id'] if person else None,'submitter_name':str(entry.get('submittedBy') or '')[:300],'submitter_email':email[:320],
                'reason':reason,'state':state,'created':timestamp(entry.get('submittedAt')),'updated':timestamp(entry.get('updatedAt') or entry.get('submittedAt')),'admin_note':str(entry.get('adminNote') or '')[:8000]}
        return 'department',None,fields,sorted(set(scopes))
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
        return 'procurement',None,common,business_claim(entry)
    claim=business_claim(entry)
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
    summary={'source':source,'read':len(entries),'new':{'adoption':0,'procurement':0,'registry':0,'department':0},'duplicates':0,'demo_skipped':0,
             'unmatched_people':0,'unmatched_tools':0,'email_domain_exceptions':0,'errors':[], 'applied':False}
    summary.update(matched=0,archived_matches=0,conflicts=0,
                   destination_before={t:db.scalar('SELECT COUNT(*) FROM '+t) for t in ('hub_reports','procurement_requests','hub_department_requests','tracker_imports')},
                   unverified_cache_records=db.scalar("SELECT COUNT(*) FROM tracker_imports WHERE source='tracker-browser-recovered'"),
                   history_completeness='Not established by this import. Original backend must be reconciled independently.')
    prepared=[];seen=set();matches=[]
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
            cross=db.q('SELECT * FROM tracker_imports WHERE source_id=?',(entry.get('id'),))
            if cross:
                targets={(r['kind'],r['target_id']) for r in cross}
                if len(targets)!=1 or any(r['digest']!=digest for r in cross):
                    summary['conflicts']+=1
                    raise ApiError(409,'This source ID already exists under another provenance with conflicting values; reconcile without overwriting the original.')
                match=cross[0];summary['matched']+=1
                if match['kind']=='adoption' and db.scalar('SELECT archived_at FROM hub_reports WHERE id=?',(match['target_id'],)):
                    summary['archived_matches']+=1
                matches.append((entry,digest,payload,match));continue
            item=_prepare(db,entry,mapping or {})
            if item is None:
                summary['demo_skipped']+=1;continue
            kind,_,fields,_=item
            summary['new'][kind]+=1
            if kind!='registry':
                summary['unmatched_people']+=fields['person_id'] is None
                summary['unmatched_tools']+=kind!='department' and fields['tool_id'] is None
                summary['email_domain_exceptions']+=not settings.email_allowed(fields['submitter_email'])
            prepared.append((entry,digest,payload,item))
        except (ApiError,ValueError,TypeError,AttributeError) as exc:
            summary['errors'].append({'row':index+1,'error':str(exc)[:300]})
    if not apply or summary['errors']:
        return summary
    with db.tx():
        for entry,digest,payload,match in matches:
            db.x('INSERT INTO tracker_imports(source,source_id,digest,kind,target_id,imported,original_json) VALUES(?,?,?,?,?,?,?)',
                 (source,entry['id'],digest,match['kind'],match['target_id'],time.time(),payload))
        for entry,digest,payload,(kind,target,fields,claim) in prepared:
            if db.one('SELECT 1 FROM tracker_imports WHERE source_id=?',(entry['id'],)):
                raise ApiError(409,'Import state changed concurrently; rerun the dry run.')
            if kind=='registry':
                if fields:
                    db.x(f"UPDATE tools SET {','.join(k+'=?' for k in fields)} WHERE id=?",(*fields.values(),target))
            else:
                table={'adoption':'hub_reports','procurement':'procurement_requests','department':'hub_department_requests'}[kind]
                target=db.x(f"INSERT INTO {table}({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",tuple(fields.values())).lastrowid
                if kind=='department':
                    for scope in claim:db.x('INSERT INTO hub_department_request_scopes VALUES(?,?)',(target,scope))
                    # Historical approval is attribution, not a new live authorisation.
                if kind=='procurement':
                    business_fields={k:v for k,v in claim.items() if k in reporting.CLAIMS}
                    business_fields['request_id']=target
                    db.x('INSERT INTO procurement_business('+','.join(business_fields)+') VALUES('+','.join('?' for _ in business_fields)+')',tuple(business_fields.values()))
                    for pos,p in enumerate(claim['projects']):
                        db.x('INSERT INTO procurement_projects(request_id,position,name,link,description,traditional,ai_way,benefit) VALUES(?,?,?,?,?,?,?,?)',(target,pos,p['name'],p['link'],p['description'],p['traditional'],p['ai_way'],p['benefit']))
                if kind=='adoption':
                    for pos,p in enumerate(claim['projects']):
                        db.x('INSERT INTO hub_report_projects(report_id,position,name,link,description,traditional,ai_way,benefit) VALUES(?,?,?,?,?,?,?,?)',(target,pos,p['name'],p['link'],p['description'],p['traditional'],p['ai_way'],p['benefit']))
                    db.x('INSERT INTO hub_report_versions(report_id,version,submitted,actor,declaration_json,reconciliation,reconciliation_reason) VALUES(?,?,?,?,?,?,?)',
                         (target,1,fields['submitted'],fields['submitter_email'],json.dumps(claim,sort_keys=True),'insufficient_telemetry',fields['reconciliation_reason']))
            db.x('INSERT INTO tracker_imports(source,source_id,digest,kind,target_id,imported,original_json) VALUES(?,?,?,?,?,?,?)',
                 (source,entry['id'],digest,kind,str(target),time.time(),payload))
        db.x('INSERT INTO audit(ts,actor,action,target,detail) VALUES(?,?,?,?,?)',(time.time(),'import operator','imported Tracker history',source,json.dumps(summary['new'],sort_keys=True)))
    summary['applied']=True
    summary['destination_after']={t:db.scalar('SELECT COUNT(*) FROM '+t) for t in ('hub_reports','procurement_requests','hub_department_requests','tracker_imports')}
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
    try: socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError('The configured Tracker hostname does not resolve. No authenticated request was attempted.') from None
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


def backfill_v20(db,apply=False):
    """Restore missing typed projections from retained v19 provenance; never alter original versions."""
    out={'adoption_metadata':0,'procurement_business':0,'unchanged':0,'skipped_amended':0,'errors':[],'applied':False}
    changes=[];seen=set()
    for ledger in db.q("SELECT * FROM tracker_imports WHERE kind IN ('adoption','procurement') ORDER BY imported"):
        key=(ledger['kind'],ledger['target_id'])
        if key in seen: continue
        seen.add(key)
        try:
            claim=business_claim(json.loads(ledger['original_json']))
            if ledger['kind']=='adoption':
                row=db.one('SELECT * FROM hub_reports WHERE id=?',(ledger['target_id'],))
                if not row: raise ValueError('Missing import target.')
                if row['version']!=1 or row['archived_at']:
                    out['skipped_amended']+=1;continue
                fields={k:claim[k] for k in ('manual_unit','ai_unit','frequency_period','adoption_stage') if row[k]!=claim[k]}
                defaults={'manual_unit':'h','ai_unit':'h','frequency_period':'month','adoption_stage':''}
                if any(row[k]!=defaults[k] for k in fields): raise ValueError('Metadata changed after import; manual reconciliation required.')
                if not fields: out['unchanged']+=1;continue
                out['adoption_metadata']+=1;changes.append(('adoption',row['id'],fields))
            else:
                if db.one('SELECT request_id FROM procurement_business WHERE request_id=?',(ledger['target_id'],)):
                    out['unchanged']+=1;continue
                if not db.one('SELECT id FROM procurement_requests WHERE id=?',(ledger['target_id'],)): raise ValueError('Missing import target.')
                out['procurement_business']+=1;changes.append(('procurement',int(ledger['target_id']),claim))
        except (ApiError,ValueError,TypeError,KeyError) as exc:
            out['errors'].append({'kind':ledger['kind'],'target':ledger['target_id'],'error':str(exc)[:300]})
    if apply and not out['errors']:
        with db.tx():
            for kind,rid,claim in changes:
                if kind=='adoption':
                    db.x('UPDATE hub_reports SET '+','.join(k+'=?' for k in claim)+' WHERE id=?',(*claim.values(),rid))
                else:
                    fields={k:v for k,v in claim.items() if k in reporting.CLAIMS};fields['request_id']=rid
                    db.x('INSERT INTO procurement_business('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',tuple(fields.values()))
                    for i,p in enumerate(claim['projects']):
                        db.x('INSERT INTO procurement_projects VALUES(?,?,?,?,?,?,?,?)',(rid,i,p['name'],p['link'],p['description'],p['traditional'],p['ai_way'],p['benefit']))
                db.x('INSERT INTO audit(ts,actor,action,target,detail,ip) VALUES(?,?,?,?,?,?)',(time.time(),'Tracker migration','restored typed business metadata',kind+':'+str(rid),'Original source ledger and submitted versions retained.',''))
        out['applied']=True
    return out


def main():
    parser=argparse.ArgumentParser(description='Safe Tracker-to-Hub migration. Defaults to a non-mutating dry run.')
    parser.add_argument('--database');parser.add_argument('--file');parser.add_argument('--mapping');parser.add_argument('--source',default='tracker')
    parser.add_argument('--apply',action='store_true');parser.add_argument('--backup');parser.add_argument('--summary',required=True)
    parser.add_argument('--export-supabase')
    parser.add_argument('--backfill-v20',action='store_true',help='Restore missing typed metadata from retained import provenance; dry run by default.')
    args=parser.parse_args()
    if args.export_supabase:
        fd=os.open(args.summary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        count=supabase_export(args.export_supabase)
        with os.fdopen(fd,'w') as f:
            json.dump({'exported':count,'read_only':True},f,indent=2)
        return
    if not args.database or (not args.file and not args.backfill_v20):
        parser.error('--database and --file are required for import.')
    if args.apply and not args.backup:
        parser.error('--apply requires --backup pointing to a new backup file.')
    # Reserve the review artifact before any target DB opening, migration or import.
    fd=os.open(args.summary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    data=json.loads(Path(args.file).read_text()) if args.file else None;mapping=json.loads(Path(args.mapping).read_text()) if args.mapping else {}
    with tempfile.TemporaryDirectory(prefix='hub-import-preflight-') as tmp:
        scratch=Path(tmp)/'gateway.db'
        backup(args.database,scratch)
        dry=DB(str(scratch))
        try:
            summary=backfill_v20(dry) if args.backfill_v20 else import_entries(dry,data,args.source,mapping)
        finally:
            dry.close()
        if args.apply and not summary['errors']:
            verified=backup(args.database,args.backup)
            db=DB(args.database)
            try:
                summary=backfill_v20(db,True) if args.backfill_v20 else import_entries(db,data,args.source,mapping,True)
                summary['backup']=verified
            finally:
                db.close()
        summary['mode']='apply' if args.apply else 'dry_run'
        with os.fdopen(fd,'w') as f:
            json.dump(summary,f,indent=2)
        print(json.dumps({k:v for k,v in summary.items() if k not in ('backup','errors')}))
        if summary['errors']:
            raise SystemExit('Validation errors: no Tracker records imported. Read the private reconciliation summary.')


if __name__=='__main__':
    main()
