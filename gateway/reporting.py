"""Native Hub accountability: frozen observations remain separate from staff declarations."""
import csv
import io
import json
import math
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from . import policy
from .admin import ApiError

TEXT_FIELDS = ('usage_confirmation', 'reason', 'impact', 'deliverables', 'quality', 'challenges',
               'issues', 'next_steps', 'revenue_description', 'usage_unit', 'pricing_source', 'selected_plan', 'currency')
NUM_FIELDS = ('manual_hours', 'ai_hours', 'manual_cost', 'ai_cost', 'subscription_cost', 'extra_credits',
              'other_expenses', 'revenue', 'frequency', 'usage_amount', 'usage_included', 'usage_unit_cost_usd', 'usage_cost_usd')
COUNT_FIELDS = ('claimed_requests', 'claimed_access_events', 'claimed_days')
CLAIMS = TEXT_FIELDS + NUM_FIELDS + COUNT_FIELDS + ('usage_flat_rate',)
OPEN_STATES = ('draft', 'returned')


def timezone(gw):
    return ZoneInfo(gw.settings.company_timezone)


def week(gw, ts=None):
    local = datetime.fromtimestamp(time.time() if ts is None else ts, timezone(gw))
    monday = local.date() - timedelta(days=local.weekday())
    return bounds(gw, monday.isoformat())


def bounds(gw, start):
    try:
        day = date.fromisoformat(start)
        if day.weekday() != 0:
            raise ValueError()
    except (TypeError, ValueError):
        raise ApiError(400, 'Reporting week must be a Monday in YYYY-MM-DD format.')
    zone = timezone(gw)
    end = day + timedelta(days=7)
    return {'week_start': day.isoformat(), 'week_end': (end - timedelta(days=1)).isoformat(),
            'starts': datetime.combine(day, datetime.min.time(), zone).timestamp(),
            'ends': datetime.combine(end, datetime.min.time(), zone).timestamp(),
            'timezone': str(zone)}


def safe_url(value):
    text = str(value or '').strip()
    p = urlsplit(text)
    if text and (p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or
                 any(ord(c) < 32 for c in text) or len(text) > 2000):
        raise ApiError(400, 'Use a valid HTTP or HTTPS supporting link without credentials.')
    return text


def number(value, field, integer=False):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ApiError(400, f'{field} must be a non-negative number.')
    try:
        n = float(value)
    except (ValueError, TypeError):
        raise ApiError(400, f'{field} must be a non-negative number.')
    if not math.isfinite(n) or n < 0 or n > 1e12 or (integer and not n.is_integer()):
        raise ApiError(400, f'{field} must be a finite non-negative {"integer" if integer else "number"}.')
    return int(n) if integer else n


def validate(body, submit=False):
    out = {}
    for field in TEXT_FIELDS:
        if field in body:
            v = body[field]
            if v is not None and not isinstance(v, str):
                raise ApiError(400, f'{field} must be text.')
            out[field] = str(v or '').strip()
            if len(out[field]) > (8000 if field != 'currency' else 3):
                raise ApiError(400, f'{field} is too long.')
    for field in NUM_FIELDS + COUNT_FIELDS:
        if field in body:
            out[field] = number(body[field], field, field in COUNT_FIELDS)
    if 'usage_flat_rate' in body:
        value=body['usage_flat_rate']
        if value is not None and (not isinstance(value,(bool,int)) or value not in (0,1)):
            raise ApiError(400,'Flat-rate pricing must be yes, no or unknown.')
        out['usage_flat_rate']=None if value is None else int(value)
    if out.get('claimed_days') is not None and out['claimed_days'] > 7:
        raise ApiError(400, 'Activity days must be between zero and seven.')
    if 'usage_confirmation' in out and not out['usage_confirmation']:
        out['usage_confirmation']=None
    if out.get('usage_confirmation') not in (None, '', 'used', 'opened_not_used', 'accidental'):
        raise ApiError(400, 'Confirm whether you used the tool, only opened it or accessed it accidentally.')
    if out.get('currency') and not re.fullmatch('[A-Z]{3}', out['currency']):
        raise ApiError(400, 'Currency must be a three-letter code.')
    if 'projects' in body:
        projects = body['projects']
        if not isinstance(projects, list) or len(projects) > 30:
            raise ApiError(400, 'Provide up to 30 projects.')
        out['projects'] = []
        for p in projects:
            if not isinstance(p, dict) or not isinstance(p.get('name'), str) or (submit and not p['name'].strip()):
                raise ApiError(400, 'Each project needs a name.')
            name, description = p['name'].strip(), str(p.get('description') or '').strip()
            if len(name) > 300 or len(description) > 4000:
                raise ApiError(400, 'Project name or description is too long.')
            project = {'name': name, 'description': description, 'link': safe_url(p.get('link'))}
            for key in ('traditional','ai_way','benefit'):
                value = p.get(key) or ''
                if not isinstance(value,str) or len(value)>4000:
                    raise ApiError(400,'Project explanations must be text up to 4,000 characters.')
                project[key] = value.strip()
            out['projects'].append(project)
    if submit and (not out.get('usage_confirmation') or not out.get('reason')):
        raise ApiError(400, 'Confirm usage and explain the work, or why the tool was not used.')
    return out


def notify_person(gw, pid, key, title, href):
    import os
    state = 'pending' if os.environ.get('GATEWAY_SMTP_HOST') else 'not_configured'
    gw.db.x('INSERT OR IGNORE INTO hub_notifications(person_id,dedupe_key,title,href,created,email_state) VALUES(?,?,?,?,?,?)',
            (pid, key, title[:180], href, time.time(), state))


def _events(gw, closed, after=None):
    db = gw.db
    sources = (
        ('requests', 'ts', "kind NOT IN ('other','media-status') AND person_id IS NOT NULL"),
        ('launches', 'ts', 'person_id IS NOT NULL AND tool_id IS NOT NULL'),
        ('site_usage', 'started', 'person_id IS NOT NULL AND tool_id IS NOT NULL'),
        ('tool_turns', 'started', 'person_id IS NOT NULL'))
    tools = {t['id']: t for t in db.q('SELECT id, provider FROM tools')}
    for source, column, where in sources:
        for row in db.q(f'SELECT * FROM {source} WHERE id > ? AND {column} < ? AND {where}', ((after or {}).get(source,0),closed)):
            tool = (tools.get(row.get('hub_tool_id')) or policy.request_tool(db, row['client'], row['provider'])) if source == 'requests' else tools.get(row['tool_id'])
            if not tool:
                continue
            timestamp = row[column]
            yield source, row, tool['id'], timestamp
            if source == 'tool_turns':
                # A turn crossing midnight/week boundaries is access occupancy in each intersected week.
                end = min(row.get('ended') or row['expires'], row['expires'], closed)
                cursor = week(gw, timestamp)['ends']
                while cursor < end:
                    yield source, row, tool['id'], cursor
                    cursor = week(gw, cursor)['ends']


def compile_closed(gw, now=None, force=False):
    """Once-per-person/tool/week compilation. Run before retention and lazily before an access decision."""
    now = time.time() if now is None else now
    closed = week(gw, now)['starts']
    db = gw.db
    with db.tx():
        # Current-week events are revisited when the week changes. New late records have new IDs.
        # Maintenance forces a complete read before retention; snapshots themselves stay immutable.
        maxima={table:db.scalar(f'SELECT COALESCE(MAX(id),0) FROM {table}') for table in ('requests','launches','site_usage','tool_turns')}
        previous=getattr(gw,'_hub_compile_cursor',None)
        after={}
        if not force and previous and previous['closed']==closed:
            if previous['maxima']==maxima:
                return []
            after={table:value if value<=maxima[table] else 0 for table,value in previous['maxima'].items()}
        stored=None
        groups = defaultdict(list)
        for source, row, tid, ts in _events(gw, closed, after):
            if stored is None:
                stored = {(r['person_id'], r['tool_id'], r['week_start']) for r in db.q('SELECT person_id,tool_id,week_start FROM weekly_evidence')}
            w = week(gw, ts)
            key = (row['person_id'], tid, w['week_start'])
            if key not in stored:
                groups[key].append((source, row, ts))
        created = []
        for (pid, tid, start), events in groups.items():
            qualifying = [(s, r, ts) for s, r, ts in events if
                          (s == 'requests' and r['outcome'] in ('ok', 'error', 'cut')) or
                          (s == 'launches' and r['outcome'] == 'opened') or
                          (s == 'site_usage' and r['outcome'] == 'allowed') or s == 'tool_turns']
            if not qualifying:
                continue  # denied access is not proof that someone used or opened a tool
            w = bounds(gw, start)
            person = db.one('SELECT name,email,department FROM people WHERE id=?', (pid,))
            tool = db.one('SELECT name,url,category FROM tools WHERE id=?', (tid,))
            if not person or not tool:
                continue
            metrics = dict(api_requests=0, api_success=0, api_failed=0, launches=0, access_events=0,
                           tab_open_seconds=0, shared_turns=0, shared_occupancy_seconds=0, media_requests=0,
                           blocked=0, input_tokens=0, output_tokens=0, unpriced_requests=0)
            costs, days, last = [], set(), None
            for source, row, ts in events:
                admitted = (source, row, ts) in qualifying
                if admitted:
                    days.add(datetime.fromtimestamp(ts, timezone(gw)).date().isoformat())
                    last = max(last or ts, ts)
                if source == 'requests':
                    if admitted:
                        metrics['api_requests'] += 1
                        metrics['api_success' if row['outcome'] == 'ok' else 'api_failed'] += 1
                        metrics['input_tokens'] += row['in_tok'] + row['cache_write_tok'] + row['cache_read_tok']
                        metrics['output_tokens'] += row['out_tok']
                        metrics['media_requests'] += row['kind'] in ('voice', 'image', 'video', 'media')
                        if row['cost'] is not None:
                            costs.append(row['cost'])
                        else:
                            metrics['unpriced_requests'] += 1
                    else:
                        metrics['blocked'] += 1
                elif source == 'launches':
                    metrics['launches' if admitted else 'blocked'] += 1
                elif source == 'site_usage':
                    metrics['access_events' if admitted else 'blocked'] += 1
                    if admitted and row.get('ended'):
                        metrics['tab_open_seconds'] += max(0, min(row['seconds'], int(min(row['ended'], w['ends']) - max(row['started'], w['starts']))))
                else:
                    metrics['shared_turns'] += 1
                    metrics['shared_occupancy_seconds'] += max(0, int(min(row.get('ended') or row['expires'], row['expires'], w['ends']) - max(row['started'], w['starts'])))
            completeness = 'api_observed' if metrics['api_requests'] else 'access_only'
            limits = 'Observed records only; source retention or unconnected browsers can leave gaps. Tab-open and shared occupancy are not working time. Costs are gateway estimates, not vendor invoices. Business impact and time savings are staff estimates.'
            fields = {'person_id': pid, 'tool_id': tid, 'week_start': start, 'timezone': w['timezone'],
                      'starts': w['starts'], 'ends': w['ends'], 'compiled': now, 'department': person['department'],
                      **metrics, 'estimated_api_cost': sum(costs) if costs else None,
                      'active_days': len(days), 'last_activity': last, 'completeness': completeness, 'limitations': limits}
            eid = db.x(f"INSERT INTO weekly_evidence({','.join(fields)}) VALUES({','.join('?' for _ in fields)})", tuple(fields.values())).lastrowid
            for source, row, ts in events:
                db.x('INSERT INTO weekly_evidence_events(evidence_id,source,source_id,ts,outcome,model,cost_source) VALUES(?,?,?,?,?,?,?)',
                     (eid, source, row['id'], ts, row.get('outcome') or 'occupied', row.get('model'), row.get('cost_source')))
            rid = db.x('INSERT INTO hub_reports(kind,person_id,tool_id,evidence_id,week_start,department,submitter_name,submitter_email,tool_name,official_url,category,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       ('weekly', pid, tid, eid, start, person['department'], person['name'], person['email'], tool['name'], tool['url'], tool['category'], now, now)).lastrowid
            notify_person(gw, pid, f'report-required:{rid}', 'Complete your weekly tool report', f'#/weekly?report={rid}')
            created.append(rid)
    gw._hub_compile_cursor={'closed':closed,'maxima':maxima}
    for start in sorted({db.scalar('SELECT week_start FROM hub_reports WHERE id=?', (rid,)) for rid in created}):
        management_snapshot(gw, start, 'system')
    return created


def pending(gw, pid, tool_id=None, now=None, compile=True):
    if compile:
        compile_closed(gw, now)
    args = [pid]
    clause = ''
    if tool_id:
        clause = ' AND tool_id=?'
        args.append(tool_id)
    return gw.db.q("SELECT id,tool_id,tool_name,week_start,state FROM hub_reports WHERE person_id=? AND kind='weekly' AND state IN ('draft','returned')" + clause + ' ORDER BY week_start,id', args)


def gate(gw, pid, tid, now=None):
    now = time.time() if now is None else now
    outstanding = pending(gw, pid, tid, now)
    if not outstanding:
        return None
    override = gw.db.one('SELECT id FROM weekly_overrides WHERE person_id=? AND tool_id=? AND starts<=? AND expires>?', (pid, tid, now, now))
    if override:
        return None
    report = outstanding[0]
    return {'code': 'weekly_report_required', 'report_id': report['id'], 'tool_id': tid,
            'week_start': report['week_start'], 'href': f"/#/weekly?report={report['id']}",
            'message': f"Complete your {report['tool_name']} report for the week beginning {report['week_start']} before using it again."}


def reconcile(declaration, evidence, tolerance=0.1):
    if not evidence:
        return 'insufficient_telemetry', 'Historical adoption declaration has no weekly telemetry to compare.'
    if not any(evidence[k] for k in ('api_requests', 'launches', 'access_events', 'shared_turns')):
        return 'no_observed_activity', 'No qualifying activity was observed.'
    findings, matches = [], 0
    if declaration.get('usage_confirmation') != 'used' and evidence['api_success'] > 0:
        findings.append(f"Staff reported {declaration.get('usage_confirmation')}; system recorded {evidence['api_success']} successful API requests. Ask for context; this is not a misconduct finding.")
    for claim, metric in (('claimed_requests', 'api_requests'), ('claimed_access_events', 'access_events'), ('claimed_days', 'active_days')):
        value = declaration.get(claim)
        if value is None:
            continue
        observed = evidence[metric]
        if abs(value - observed) > max(1, observed * tolerance):
            findings.append(f'{claim}: staff declared {value}; system observed {observed}; tolerance {tolerance:.0%} or one event.')
        else:
            matches += 1
    if findings:
        return 'needs_review', ' '.join(findings)
    if evidence['completeness'] == 'access_only':
        return 'insufficient_telemetry', 'Access was recorded; website work and business outcomes cannot be independently verified.'
    if matches and not any(declaration.get(k) is not None for k in NUM_FIELDS) and not declaration.get('impact'):
        return 'matched', 'All supplied comparable numerical claims agree within tolerance; no business estimates are independently verified.'
    if matches:
        return 'partially_matched', 'Comparable activity counts agree. Business impact, revenue, time and declared spending remain staff-reported estimates.'
    return 'insufficient_telemetry', 'API activity was observed, but the declaration contains no directly comparable numerical claims.'


def import_provenance(db, kind, target):
    row = db.one('SELECT source,source_id,imported FROM tracker_imports WHERE kind=? AND target_id=?', (kind, str(target)))
    if row:
        row['note'] = ('Recovered Tracker browser cache; the original backend is unavailable. '
                       'Historical declarations have not been reconciled against the backend.'
                       if row['source'] == 'tracker-browser-recovered' else
                       'Imported Tracker history; this is a historical declaration, not observed weekly activity.')
    return row


def detail(gw, rid, pid=None):
    row = gw.db.one('SELECT * FROM hub_reports WHERE id=?' + (' AND person_id=?' if pid is not None else ''), (rid, pid) if pid is not None else (rid,))
    if not row:
        raise ApiError(404, 'Report not found.')
    row['import_provenance'] = import_provenance(gw.db, 'adoption', rid)
    row['projects'] = gw.db.q('SELECT name,link,description,traditional,ai_way,benefit FROM hub_report_projects WHERE report_id=? ORDER BY position', (rid,))
    row['evidence'] = gw.db.one('SELECT * FROM weekly_evidence WHERE id=?', (row['evidence_id'],)) if row['evidence_id'] else None
    if row['evidence']:
        row['period'] = evidence_period(row['evidence'])
        row['evidence']['events'] = gw.db.q('SELECT source,source_id,ts,outcome,model,cost_source FROM weekly_evidence_events WHERE evidence_id=? ORDER BY ts', (row['evidence_id'],))
    row['versions'] = gw.db.q('SELECT * FROM hub_report_versions WHERE report_id=? ORDER BY version', (rid,))
    for v in row['versions']:
        v['declaration'] = json.loads(v.pop('declaration_json'))
    row['reviews'] = gw.db.q('SELECT actor,ts,action,note,version FROM hub_report_reviews WHERE report_id=? ORDER BY id', (rid,))
    return row


def save(gw, pid, rid, body, submit=False):
    db, now = gw.db, time.time()
    with db.tx():
        row = detail(gw, rid, pid)
        person = db.one('SELECT email FROM people WHERE id=?',(pid,))
        actor = person['email'] if person else row['submitter_email']
        # A retry of a submitted request returns the existing version, never writes a duplicate.
        if submit and row['state'] in ('submitted', 'resubmitted', 'reviewed', 'confirmed'):
            return row
        if row['state'] not in OPEN_STATES:
            raise ApiError(409, 'This report is already submitted. Request a correction before changing it.')
        expected = body.get('version')
        if expected is not None and expected != row['version']:
            raise ApiError(409, 'This report changed. Reload it before saving.')
        merged = {k: row[k] for k in CLAIMS}
        merged['projects'] = row['projects']
        merged.update(validate(body))
        if submit:
            merged = validate(merged, submit=True)
        updates = {k: v for k, v in merged.items() if k in CLAIMS}
        updates['updated'] = now
        if submit:
            try:
                tolerance = float(db.get_setting('weekly_reconciliation_tolerance', '0.1'))
            except ValueError:
                tolerance = 0.1
            tolerance = max(0, min(1, tolerance))
            result, why = reconcile(merged, row['evidence'], tolerance)
            updates.update(state='resubmitted' if row['state'] == 'returned' else 'submitted',
                           submitted=now, version=row['version'] + 1, reconciliation=result,
                           reconciliation_reason=why, reconciliation_tolerance=tolerance)
            db.x('INSERT INTO hub_report_versions(report_id,version,submitted,actor,declaration_json,reconciliation,reconciliation_reason) VALUES(?,?,?,?,?,?,?)',
                 (rid, updates['version'], now, actor, json.dumps(merged, sort_keys=True), result, why))
        db.x(f"UPDATE hub_reports SET {','.join(k+'=?' for k in updates)} WHERE id=?", (*updates.values(), rid))
        if 'projects' in merged:
            db.x('DELETE FROM hub_report_projects WHERE report_id=?', (rid,))
            for i, project in enumerate(merged['projects']):
                db.x('INSERT INTO hub_report_projects(report_id,position,name,link,description,traditional,ai_way,benefit) VALUES(?,?,?,?,?,?,?,?)', (rid, i, project['name'], project['link'], project['description'],project['traditional'],project['ai_way'],project['benefit']))
        if submit:
            gw.audit(actor, 'submitted a Hub report', str(rid), reason='', after={'version': updates['version'], 'state': updates['state']}, correlation=f'hub-report:{rid}', area='govern')
            notify_person(gw, pid, f"report-submitted:{rid}:{updates['version']}", 'Weekly report submitted; its reporting gate is cleared' if row['kind'] == 'weekly' else 'Adoption report submitted', f'#/weekly?report={rid}')
    if submit and row['week_start']:
        management_snapshot(gw, row['week_start'], actor)
    return detail(gw, rid, pid)


def review(ctx, rid):
    db, now = ctx.db, time.time()
    action = str(ctx.body.get('state') or '')
    note = str(ctx.body.get('note') or '').strip()
    if len(note) > 8000 or action not in ('reviewed', 'confirmed', 'returned', 'annotated'):
        raise ApiError(400, 'Choose a review decision and a note up to 8,000 characters.')
    if action in ('returned', 'annotated') and not note:
        raise ApiError(400, 'Explain the correction or annotation.')
    with db.tx():
        row = detail(ctx.gw, rid)
        if row['state'] not in ('submitted', 'resubmitted', 'reviewed', 'confirmed') and action != 'annotated':
            raise ApiError(409, 'Only a submitted report can be reviewed or returned.')
        if action != 'annotated':
            db.x('UPDATE hub_reports SET state=?,reviewer_id=?,reviewed=?,reviewer_note=?,updated=? WHERE id=?', (action, ctx.admin['id'], now, note, now, rid))
        db.x('INSERT INTO hub_report_reviews(report_id,version,admin_id,actor,ts,action,note) VALUES(?,?,?,?,?,?,?)', (rid, row['version'], ctx.admin['id'], ctx.admin['username'], now, action, note))
        ctx.audit('reviewed a Hub report', str(rid), before={'state': row['state'], 'version': row['version']}, after={'state': action, 'note': note}, correlation=f'hub-report:{rid}')
        if action == 'returned' and row['person_id']:
            notify_person(ctx.gw, row['person_id'], f'report-returned:{rid}:{row["version"]}', 'Your tool report needs a correction', f'#/weekly?report={rid}')
    if row['week_start']:
        management_snapshot(ctx.gw, row['week_start'], ctx.admin['username'])
    return detail(ctx.gw, rid)


def evidence_period(evidence):
    return {'week_start': evidence['week_start'],
            'week_end': (date.fromisoformat(evidence['week_start']) + timedelta(days=6)).isoformat(),
            'starts': evidence['starts'], 'ends': evidence['ends'], 'timezone': evidence['timezone']}


def management_totals(reports, evidence):
    observed = {key: sum(e[key] or 0 for e in evidence) for key in
                ('api_requests','api_success','api_failed','launches','access_events','media_requests','blocked','input_tokens','output_tokens')}
    costs = [e['estimated_api_cost'] for e in evidence if e['estimated_api_cost'] is not None]
    observed['estimated_api_cost'] = sum(costs) if costs else None
    observed['estimated_cost_per_api_request'] = sum(costs)/observed['api_requests'] if costs and observed['api_requests'] else None
    observed['unpriced_requests'] = sum(e['unpriced_requests'] for e in evidence)
    claims = [r for r in reports if r['state'] not in OPEN_STATES]
    counts = {state: sum(r['state']==state for r in reports) for state in ('draft','submitted','resubmitted','reviewed','confirmed','returned')}
    comparisons = {state: sum(r['reconciliation']==state for r in claims) for state in ('matched','partially_matched','needs_review','insufficient_telemetry','no_observed_activity')}
    # Do not sum money across currencies. Hours remain unverified declarations.
    pairs = [(r['manual_hours'],r['ai_hours']) for r in claims if r['manual_hours'] is not None and r['ai_hours'] is not None]
    value = {'reported_time_saved_hours': sum(a-b for a,b in pairs) if pairs else None, 'time_estimate_count': len(pairs)}
    return {'observed': observed, 'states': counts, 'reconciliation': comparisons, 'staff_estimates': value}


def management_snapshot(gw, start, actor='system'):
    bounds(gw, start)
    db = gw.db
    with db.tx():
        reports = db.q("SELECT id,person_id,tool_id,department,submitter_name,tool_name,state,version,reconciliation,manual_hours,ai_hours,manual_cost,ai_cost,subscription_cost,extra_credits,currency,revenue,impact,usage_cost_usd,evidence_id FROM hub_reports WHERE kind='weekly' AND week_start=? ORDER BY id", (start,))
        evidence = db.q('SELECT * FROM weekly_evidence WHERE week_start=? ORDER BY id', (start,))
        procurement = db.q('SELECT id,tool_name,department,state,estimated_monthly_cost,estimated_one_time_cost FROM procurement_requests WHERE created>=? AND created<? ORDER BY id', (bounds(gw, start)['starts'], bounds(gw, start)['ends']))
        period=bounds(gw,start)
        adoption=db.q("SELECT id,person_id,tool_id,department,submitter_name,tool_name,state,version,currency,manual_hours,ai_hours,manual_cost,ai_cost,subscription_cost,extra_credits,usage_cost_usd,revenue,impact FROM hub_reports WHERE kind='adoption' AND created>=? AND created<? ORDER BY id",(period['starts'],period['ends']))
        subscriptions = db.q("SELECT s.tool_id,t.name,s.seats,s.monthly_cost FROM subscriptions s JOIN tools t ON t.id=s.tool_id WHERE s.state='active'")
        observed = {e['tool_id'] for e in evidence}
        snap = {'period': evidence_period(evidence[0]) if evidence else bounds(gw, start), 'totals': management_totals(reports,evidence), 'reports': reports, 'adoption_declarations': adoption, 'evidence': evidence, 'procurement': procurement,
                'potential_underused_licences': [s for s in subscriptions if s['tool_id'] not in observed],
                'limitations': 'No observed activity is not proof of non-use. Subscription prices are administrative records; API costs are estimates; time, savings and revenue are staff declarations. Report and evidence IDs permit trace-back.'}
        previous = db.one('SELECT revision,snapshot_json FROM weekly_management_snapshots WHERE week_start=? ORDER BY revision DESC LIMIT 1', (start,))
        payload = json.dumps(snap, sort_keys=True)
        if previous and previous['snapshot_json'] == payload:
            return previous['revision']
        revision = previous['revision'] + 1 if previous else 1
        db.x('INSERT INTO weekly_management_snapshots(week_start,revision,created,actor,snapshot_json) VALUES(?,?,?,?,?)', (start, revision, time.time(), actor, payload))
        return revision


def csv_bytes(rows, fields):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(fields)
    for row in rows:
        values = []
        for field in fields:
            v = row.get(field)
            text = '' if v is None else str(v)
            if text.lstrip().startswith(('=', '+', '-', '@')):
                text = "'" + text
            values.append(text)
        writer.writerow(values)
    return out.getvalue().encode('utf-8-sig')


def key_scope(db, person, tool_id):
    if not tool_id:
        return None  # backwards-compatible legacy key, conservative reporting gate
    from . import entitle
    tool = db.one("SELECT * FROM tools WHERE id=? AND archived=0", (str(tool_id),))
    if not tool or tool["kind"] not in ("api", "dev") or not tool["provider"]:
        raise ApiError(400, "Choose an API or developer tool for this key.")
    if not entitle.is_enabled(db, person, tool)[0]:
        raise ApiError(403, "This tool is not assigned and available to you.")
    return tool["id"]


def studio_denial(ctx, provider):
    tool = policy.request_tool(ctx.db, "Swangz AI Hub Studio", provider.name)
    denial = gate(ctx.gw, ctx.person["id"], tool["id"]) if tool else None
    if denial:
        raise ApiError(403, denial["message"], denial["code"], denial)


def close_week_turns(gw, now=None):
    """End earlier-week shared-browser leases; the existing sweep revokes their remote sign-ins."""
    closed=week(gw,now)['starts']
    with gw.db.tx():
        ids=gw.db.q('SELECT id FROM tool_turns WHERE ended IS NULL AND started<?',(closed,))
        if ids:
            gw.db.x("UPDATE tool_turns SET ended=MIN(expires,?),ended_by='system',reason='weekly reporting boundary' WHERE ended IS NULL AND started<?",(closed,closed))
            gw.audit('system','closed shared turns at the reporting boundary',str(len(ids)),after={'turn_ids':[r['id'] for r in ids],'boundary':closed},correlation='weekly-turn-boundary')
    return len(ids)
