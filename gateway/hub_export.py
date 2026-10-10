"""Authenticated, escaped management exports from a historical snapshot."""
from html import escape
from . import admin, reporting
from .hub_api import management


@admin.route('GET', r'/hub/print')
def print_management(ctx):
    data=management(ctx);snapshot=data['snapshot'];period=snapshot['period']
    def table(title,rows,columns):
        headings=''.join('<th scope="col">'+escape(label)+'</th>' for _,label in columns)
        cells=''.join('<tr>'+''.join('<td>'+escape('Unknown' if r.get(key) is None else str(r[key]))+'</td>' for key,_ in columns)+'</tr>' for r in rows)
        return '<section><h2>'+escape(title)+'</h2><div class="u-table-wrap"><table><thead><tr>'+headings+'</tr></thead><tbody>'+cells+'</tbody></table></div></section>'
    evidence={e['id']:e for e in snapshot['evidence']}
    rows=[{**evidence.get(r['evidence_id'],{}),**r} for r in snapshot['reports']]
    body='<h1>Swangz AI Hub · weekly management report</h1><p>'+escape(f"{period['week_start']} – {period['week_end']} · {period['timezone']} · revision {data['revision']}")+'</p>'
    body+='<p>'+escape(snapshot['limitations'])+'</p>'
    body+=table('Independent system observations',rows,[('id','Report'),('submitter_name','Staff'),('department','Department'),('tool_name','Tool'),('api_requests','API requests'),('launches','Launches'),('access_events','Access events'),('estimated_api_cost','Estimated API cost'),('completeness','Evidence')])
    body+=table('Staff declarations and review',rows,[('id','Report'),('submitter_name','Staff'),('tool_name','Tool'),('state','Status'),('reconciliation','Reconciliation'),('manual_hours','Estimated manual hours'),('ai_hours','Estimated AI hours'),('currency','Currency'),('revenue','Estimated revenue'),('impact','Declared impact')])
    body+=table('Staff-reported costs (not verified vendor spend)',rows,[('id','Report'),('submitter_name','Staff'),('tool_name','Tool'),('currency','Currency'),('manual_cost','Declared manual cost'),('ai_cost','Declared AI cost'),('subscription_cost','Declared subscription'),('extra_credits','Declared credits'),('usage_cost_usd','Declared usage allocation (USD)')])
    body+=table('Separate adoption declarations (not weekly evidence)',snapshot.get('adoption_declarations',[]),[('id','Report'),('submitter_name','Staff'),('tool_name','Tool'),('state','Status'),('impact','Declared value')])
    body+=table('Potentially underused licences',snapshot['potential_underused_licences'],[('name','Tool'),('seats','Seats'),('monthly_cost','Recorded monthly cost')])
    body+=table('Procurement requests',snapshot['procurement'],[('id','Request'),('tool_name','Tool'),('department','Department'),('state','Status')])
    html='<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Weekly management report · Swangz AI Hub</title><link rel="stylesheet" href="/static/tokens.css"><link rel="stylesheet" href="/static/ui.css"><link rel="stylesheet" href="/static/hub.css"></head><body><main class="hub-print">'+body+'</main></body></html>'
    ctx.audit('exported weekly management print view',period['week_start'],after={'revision':data['revision']})
    from .server import CONSOLE_HEADERS
    return html.encode(),'text/html; charset=utf-8',{'Cache-Control':'no-store',**CONSOLE_HEADERS}


@admin.route('GET', r'/hub/trends')
def trends(ctx):
    import json
    rows=ctx.db.q('SELECT s.week_start,s.revision,s.created,s.snapshot_json FROM weekly_management_snapshots s WHERE s.revision=(SELECT MAX(x.revision) FROM weekly_management_snapshots x WHERE x.week_start=s.week_start) ORDER BY s.week_start DESC LIMIT 52')
    result=[]
    for row in rows:
        snapshot=json.loads(row['snapshot_json']);totals=snapshot.get('totals') or reporting.management_totals(snapshot['reports'],snapshot['evidence'])
        states=totals['states']
        result.append({'week_start':row['week_start'],'revision':row['revision'],'created':row['created'],
                       'outstanding':states.get('draft',0)+states.get('returned',0),'submitted':sum(n for s,n in states.items() if s not in reporting.OPEN_STATES),
                       'api_requests':totals['observed']['api_requests'],'access_events':totals['observed']['launches']+totals['observed']['access_events'],
                       'estimated_api_cost':totals['observed']['estimated_api_cost'], 'reported_time_saved_hours':totals['staff_estimates']['reported_time_saved_hours']})
    return {'items':result,'limit':52,'basis':'Latest preserved revision per week; time savings are staff estimates.'}
