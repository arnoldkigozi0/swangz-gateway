"""Regression coverage for native Tracker parity, permissions and immutable historical claims."""
import json
import time
import unittest
from gateway import authz, business, reporting, security
from gateway.hub_import import import_entries
from . import test_hub


class BusinessHTTPTests(unittest.TestCase):
    def setUp(self):
        test_hub.HubHTTPTests.setUp(self)
        self.db.x("INSERT INTO admins(username,pw_hash,role,areas,created) VALUES(?,?,?,?,?)",('operations@swangzavenue.com',security.hash_password('operations-password',1000),*authz.stored('operations'),time.time()))
        self.db.x("INSERT INTO admins(username,pw_hash,role,areas,created) VALUES(?,?,?,?,?)",('billing@swangzavenue.com',security.hash_password('billing-password',1000),*authz.stored('billing'),time.time()))
    staff = test_hub.HubHTTPTests.staff
    obligation = test_hub.HubHTTPTests.obligation
    def adoption(self, **extra):
        state,r=self.staff('POST','/hub/adoption',{'tool_id':'chatgpt'})
        self.assertEqual(state,200)
        claim={'usage_confirmation':'used','reason':'Synthetic campaign','manual_hours':16,'ai_hours':2,
               'frequency':4,'frequency_period':'month','manual_cost':100,'ai_cost':5,
               'subscription_cost':20,'extra_credits':0,'other_expenses':0,'currency':'USD',
               'projects':[{'name':'Synthetic pilot','link':'https://example.test/project','description':'Deliverable','traditional':'Manual','ai_way':'Assisted','benefit':'Iterations'}],**extra}
        state,r=self.staff('POST',f'/hub/reports/{r["id"]}/submit',claim)
        self.assertEqual(state,200)
        return r

    def test_business_calculations_preserve_work_units_and_missing_values(self):
        r=self.adoption(manual_unit='d',ai_unit='h')
        value=business.calculate(r)
        self.assertEqual(value['time_saved_hours'],56)
        self.assertEqual((value['manual_period_cost'],value['ai_period_cost'],value['net_savings'],value['roi_percent']),(400,40,360,900))
        self.assertEqual(r['manual_hours'],16) # unit is input preference, never reconverted stored hours
        r['extra_credits']=None
        self.assertIsNone(business.calculate(r)['net_savings'])
        r['frequency']=None
        self.assertIsNone(business.calculate(r)['time_saved_hours'])
        r.update(ai_cost=0,subscription_cost=0,extra_credits=0,other_expenses=0,frequency=1)
        self.assertIsNone(business.calculate(r)['roi_percent'])

    def test_usage_cost_allowance_is_not_double_charged(self):
        r=self.adoption(ai_cost=None,usage_amount=50,usage_included=100,usage_unit_cost_usd=2,usage_unit='credits')
        x=business.calculate(r)
        self.assertEqual(x['usage_pricing']['allocation'],10)
        self.assertEqual(x['ai_period_cost'],20)
        r['usage_amount']=110
        self.assertEqual(business.calculate(r)['ai_period_cost'],100)
        r['usage_unit_cost_usd']=None
        self.assertIsNone(business.calculate(r)['ai_period_cost'])
        r['usage_flat_rate']=1
        self.assertEqual(business.calculate(r)['ai_period_cost'],20)

    def test_business_scope_is_authenticated_personal_and_local_date_inclusive(self):
        r=self.adoption()
        pid=self.db.x("INSERT INTO people(name,email,created) VALUES('Other','other@swangzavenue.com',?)",(time.time(),)).lastrowid
        self.db.x('UPDATE hub_reports SET person_id=? WHERE id=?',(pid,r['id']))
        self.assertEqual(self.staff('GET','/hub/business?person='+str(pid))[1]['reports'],[])
        self.assertEqual(len(self.rig.api('GET','/hub/business')[1]['reports']),1)
        self.assertEqual(self.rig.request('GET','/api/hub/business')[0],401)
        self.assertEqual(self.rig.api('GET','/hub/business?from=2026-10-02&to=2026-10-01')[0],400)
        self.assertEqual(self.rig.api('GET','/hub/business?from=invalid')[0],400)
        self.db.x('UPDATE hub_reports SET created=? WHERE id=?',(reporting.datetime.fromisoformat('2026-10-01T00:15:00+03:00').timestamp(),r['id']))
        self.assertEqual(len(self.rig.api('GET','/hub/business?from=2026-10-01&to=2026-10-01')[1]['reports']),1)

    def test_amendment_keeps_original_author_time_state_and_version(self):
        r=self.adoption();original=self.db.one('SELECT * FROM hub_report_versions WHERE report_id=?',(r['id'],))
        state,out=self.staff('POST',f'/hub/reports/{r["id"]}/amend',{'version':1,'amendment_reason':'Correct estimate','manual_hours':8})
        self.assertEqual(state,200);self.assertEqual(out['version'],2)
        self.assertEqual((out['submitter_email'],out['submitted'],out['state']),(r['submitter_email'],r['submitted'],r['state']))
        self.assertEqual(self.db.one('SELECT * FROM hub_report_versions WHERE report_id=? AND version=1',(r['id'],)),original)
        self.assertEqual(self.staff('POST',f'/hub/reports/{r["id"]}/amend',{'version':1,'amendment_reason':'Stale','manual_hours':2})[0],409)
        self.assertEqual(self.staff('POST',f'/hub/reports/{r["id"]}/amend',{'version':2,'manual_hours':2})[0],400)
        self.assertEqual(self.rig.api('POST',f'/hub/reports/{r["id"]}/amend',{'version':2,'amendment_reason':'Edit','manual_cost':2},who='operations')[0],403)
        self.assertEqual(self.rig.api('POST',f'/hub/reports/{r["id"]}/amend',{'version':2,'amendment_reason':'Edit','quality':'Clearer'},who='viewer')[0],403)

    def test_archive_is_atomic_and_cannot_remove_weekly_obligations(self):
        r=self.adoption();weekly=self.obligation()
        self.assertEqual(self.rig.api('POST','/hub/reports/archive',{'ids':[r['id'],weekly],'reason':'Cleanup'})[0],400)
        self.assertIsNone(self.db.scalar('SELECT archived_at FROM hub_reports WHERE id=?',(r['id'],)))
        self.assertEqual(self.rig.api('POST','/hub/reports/archive',{'ids':[r['id']],'reason':'Duplicate business declaration'})[0],200)
        self.assertEqual(self.staff('GET',f'/hub/reports/{r["id"]}')[0],404)
        self.assertEqual(self.staff('GET','/hub/business')[1]['reports'],[])
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM hub_report_versions WHERE report_id=?',(r['id'],)),1)
        self.assertIsNotNone(reporting.gate(self.rig.gw,self.pid,'chatgpt'))

    def test_attribution_never_changes_original_author_or_entitlements(self):
        r=self.adoption();entitlements=self.db.q('SELECT * FROM entitlements')
        state,out=self.rig.api('POST',f'/hub/reports/{r["id"]}/attribution',{'person_id':None,'tool_id':'canva','reason':'Registry reconciliation'})
        self.assertEqual(state,200)
        self.assertEqual(out['submitter_email'],r['submitter_email']);self.assertEqual(out['tool_name'],'ChatGPT')
        self.assertEqual(self.db.q('SELECT * FROM entitlements'),entitlements)
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM hub_attribution_changes'),1)
        self.assertEqual(self.rig.api('POST',f'/hub/reports/{r["id"]}/attribution',{'tool_id':'missing','reason':'Match'})[0],400)

    def test_unlisted_declaration_does_not_create_catalogue_or_entitlement(self):
        before=self.db.scalar('SELECT COUNT(*) FROM tools')
        state,r=self.staff('POST','/hub/adoption',{'tool_name':'Unlisted synthetic tool','official_url':'https://example.test','category':'Research'})
        self.assertEqual(state,200);self.assertIsNone(r['tool_id']);self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM tools'),before)
        self.assertIn(r['id'],[i['id'] for i in self.rig.api('GET','/hub/registry')[1]['unmatched']])
        self.assertEqual(self.staff('POST','/hub/adoption',{'tool_name':'X','category':'Research','official_url':'javascript:alert(1)'})[0],400)

    def test_procurement_preserves_proposed_business_case_and_project_without_counting_realised_value(self):
        payload={'tool_name':'New tool','purchase_type':'credits','reason':'Production plan','business':{'manual_hours':8,'ai_hours':1,'frequency':3,'revenue':None,'projects':[{'name':'Proposed pilot','benefit':'Expected iteration'}]}}
        state,r=self.staff('POST','/hub/procurement',payload);self.assertEqual(state,200)
        state,d=self.staff('GET',f'/hub/procurement/{r["id"]}');self.assertEqual(state,200);self.assertEqual(d['business']['manual_hours'],8);self.assertEqual(d['projects'][0]['name'],'Proposed pilot')
        self.assertEqual(self.staff('GET','/hub/business')[1]['reports'],[])
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM hub_reports'),0)
        self.assertEqual(self.staff('POST','/hub/procurement',{**payload,'business':{'projects':[{'name':'X','link':'data:text/html,evil'}]}})[0],400)
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM procurement_requests'),1)

    def test_plan_pricing_requires_money_permission_and_does_not_change_subscription(self):
        before=self.db.q('SELECT * FROM subscriptions')
        body={'tool_id':'chatgpt','name':'Reference plan','monthly_usd':20,'pricing_url':'https://example.test/pricing','flat_rate':True}
        self.assertEqual(self.rig.api('POST','/hub/plans',body,who='operations')[0],403)
        state,p=self.rig.api('POST','/hub/plans',body);self.assertEqual(state,200)
        self.assertEqual(self.staff('GET','/hub/plans')[1]['items'][0]['name'],'Reference plan')
        self.assertEqual(self.db.q('SELECT * FROM subscriptions'),before)
        self.assertEqual(self.rig.api('POST',f'/hub/plans/{p["id"]}/archive')[0],200)
        self.assertEqual(self.staff('GET','/hub/plans')[1]['items'],[])

    def test_cross_source_reconciliation_does_not_duplicate_or_resurrect(self):
        data=[{'id':'source-1','toolName':'ChatGPT','submittedAt':'2026-08-01T10:00:00Z','reason':'Campaign'}]
        self.assertTrue(import_entries(self.db,data,'tracker-browser-recovered',apply=True)['applied'])
        rid=self.db.scalar('SELECT id FROM hub_reports')
        self.rig.api('POST','/hub/reports/archive',{'ids':[rid],'reason':'Archived duplicate'})
        out=import_entries(self.db,data,'tracker-authoritative',apply=True)
        self.assertEqual((out['matched'],out['archived_matches']), (1,1))
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM hub_reports'),1)
        self.assertIsNotNone(self.db.scalar('SELECT archived_at FROM hub_reports'))
        data[0]['reason']='Different value'
        self.assertEqual(import_entries(self.db,data,'third-source',apply=True)['conflicts'],1)
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM tracker_imports'),2)

    def test_export_labels_estimates_and_escapes_formulas(self):
        self.adoption(impact='=danger')
        status,_,csv=self.rig.request('GET','/api/hub/business/export',headers=self.headers)
        self.assertEqual(status,200);self.assertIn(b'staff-reported estimate',csv);self.assertIn(b"'=danger",csv)

    def test_purchase_draft_restores_normalised_fields_and_submits_once(self):
        self.assertEqual(self.staff('GET','/hub/procurement/draft')[1],{'version':0,'data':None})
        body={'draft_version':0,'tool_name':'Draft tool','purchase_type':'credits','business':{'manual_hours':16,'manual_unit':'d','projects':[{'name':'','description':'Incomplete draft'}]}}
        status,saved=self.staff('PUT','/hub/procurement/draft',body)
        self.assertEqual(status,200);self.assertEqual(saved['data']['business']['manual_unit'],'d')
        self.assertEqual(self.staff('PUT','/hub/procurement/draft',body)[0],409)
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM procurement_requests'),0)
        body.update(draft_version=1,reason='Complete proposal');body['business']['projects'][0]['name']='Proposed project'
        self.assertEqual(self.staff('POST','/hub/procurement',body)[0],200)
        self.assertEqual(self.staff('POST','/hub/procurement',body)[0],200)
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM procurement_requests'),1)
        self.assertIsNone(self.staff('GET','/hub/procurement/draft')[1]['data'])
        self.assertEqual(self.rig.request('GET','/api/hub/procurement/draft')[0],401)

    def test_finance_role_can_correct_money_but_not_business_attribution(self):
        r=self.adoption();original=self.db.one('SELECT * FROM hub_report_versions WHERE report_id=?',(r['id'],))
        body={'version':1,'amendment_reason':'Reviewed finance estimate','subscription_cost':35}
        self.assertEqual(self.rig.api('POST',f'/hub/reports/{r["id"]}/pricing',body,who='billing')[0],200)
        self.assertEqual(self.db.one('SELECT * FROM hub_report_versions WHERE report_id=? AND version=1',(r['id'],)),original)
        self.assertEqual(self.rig.api('POST',f'/hub/reports/{r["id"]}/pricing',{**body,'version':2,'reason':'Rewrite purpose'},who='billing')[0],400)
        self.assertEqual(self.rig.api('POST',f'/hub/reports/{r["id"]}/amend',{**body,'version':2,'reason':'Rewrite purpose'},who='billing')[0],403)
        self.assertEqual(self.db.scalar('SELECT financial_basis FROM hub_reports WHERE id=?',(r['id'],)),'administrative estimate')

    def test_scenarios_convert_work_units_without_writing_reports(self):
        body={'manual_time':2,'manual_unit':'d','ai_time':1,'ai_unit':'h','frequency':3,'frequency_period':'month','currency':'USD'}
        status,result=self.staff('POST','/hub/business/calculate',body)
        self.assertEqual(status,200);self.assertEqual(result['calculation']['time_saved_hours'],45)
        self.assertIsNone(result['calculation']['roi_percent']);self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM hub_reports'),0)
        self.assertEqual(self.staff('POST','/hub/business/calculate',{**body,'manual_unit':'elapsed-day'})[0],400)

    def test_document_and_structured_exports_are_safe_and_scope_limited(self):
        r=self.adoption(impact='<script>alert(1)</script>')
        status,headers,body=self.rig.request('GET','/api/hub/business/export?format=html',headers=self.headers)
        self.assertEqual(status,200);self.assertIn(b'&lt;script&gt;',body);self.assertNotIn(b'<script>',body)
        self.assertIn('sandbox',headers['content-security-policy'])
        status,headers,body=self.rig.request('GET','/api/hub/business/export?format=json',headers=self.headers)
        out=json.loads(body);self.assertEqual(len(out['declarations']),1);self.assertEqual(out['declarations'][0]['id'],r['id'])
        self.assertEqual(self.staff('GET','/hub/business/export?format=unknown')[0],400)

    def test_v19_import_projection_backfill_is_idempotent_and_preserves_versions(self):
        from gateway.hub_import import backfill_v20
        data=[{'id':'backfill-report','toolName':'ChatGPT','submittedAt':'2026-08-01T10:00:00Z','reason':'Work','status':'Piloting','tradTime':2,'tradTimeUnit':'d'}, {'id':'backfill-request','tag':'request','toolName':'ChatGPT','submittedAt':'2026-08-01T10:00:00Z','reason':'Proposed work','projects':[{'name':'Proposed pilot','aiWay':'Draft'}]}]
        self.assertTrue(import_entries(self.db,data,'source',apply=True)['applied'])
        original=self.db.q('SELECT * FROM hub_report_versions');self.db.x("UPDATE hub_reports SET manual_unit='h',adoption_stage=''")
        self.db.x('DELETE FROM procurement_projects');self.db.x('DELETE FROM procurement_business')
        dry=backfill_v20(self.db);self.assertEqual((dry['adoption_metadata'],dry['procurement_business']),(1,1));self.assertFalse(dry['applied'])
        self.assertTrue(backfill_v20(self.db,True)['applied']);self.assertEqual(self.db.q('SELECT * FROM hub_report_versions'),original)
        again=backfill_v20(self.db,True);self.assertEqual((again['adoption_metadata'],again['procurement_business']),(0,0))
        self.assertEqual(self.db.scalar('SELECT ai_way FROM procurement_projects'),'Draft')

    def test_department_report_access_is_scoped_reviewed_revocable_and_not_tool_access(self):
        self.adoption()
        self.db.x("INSERT INTO people(name,email,department,created) VALUES('Other team','other@swangzavenue.com','Operations',?)",(time.time(),))
        self.assertEqual(self.staff('GET','/hub/department-business?department=Operations')[0],403)
        self.assertEqual(len(self.staff('GET','/hub/department-business?department=Creative')[1]['reports']),1)
        self.assertEqual(self.staff('GET','/hub/department-business?department=Creative')[1]['licences'],[])
        original=self.db.q('SELECT * FROM entitlements')
        body={'departments':['Operations'],'reason':'Cross-team production planning'}
        status,r=self.staff('POST','/hub/department-requests',body);self.assertEqual(status,200)
        self.assertEqual(self.staff('POST','/hub/department-requests',body)[1]['id'],r['id'])
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM procurement_requests'),0)
        from gateway import notify
        self.assertIn('hub-departments',[c['key'] for c in notify.conditions(self.rig.gw)])
        self.assertEqual(self.rig.api('POST',f'/hub/department-requests/{r["id"]}/review',{'state':'approved','note':'Verified business need'},who='billing')[0],403)
        self.assertEqual(self.rig.api('POST',f'/hub/department-requests/{r["id"]}/review',{'state':'approved','note':'Verified business need'})[0],200)
        self.assertEqual(self.staff('GET','/hub/department-business?department=Operations')[0],200)
        self.assertEqual(self.db.q('SELECT * FROM entitlements'),original)
        self.assertEqual(self.rig.api('POST','/hub/department-grants/revoke',{'person_id':self.pid,'department':'Operations','reason':'Engagement ended'})[0],200)
        self.assertEqual(self.staff('GET','/hub/department-business?department=Operations')[0],403)

    def test_department_scope_never_exposes_other_departments_or_drafts(self):
        r=self.adoption();self.db.x("UPDATE hub_reports SET department='Operations' WHERE id=?",(r['id'],))
        self.assertEqual(self.staff('GET','/hub/department-business?department=Creative')[1]['reports'],[])
        self.assertEqual(self.staff('GET',f'/hub/department-reports/{r["id"]}')[0],404)
        self.db.x("UPDATE hub_reports SET department='Creative',state='draft' WHERE id=?",(r['id'],))
        data=self.staff('GET','/hub/department-business?department=Creative')[1]
        self.assertEqual(data['reports'],[]);self.assertEqual(data['projects'],[])
        self.assertEqual(self.staff('GET',f'/hub/department-reports/{r["id"]}')[0],404)

    def test_imported_department_request_requires_reviewed_scope_and_never_grants_access(self):
        entry={'id':'historic-scope','kind':'access','tag':'request','toolName':'Department access: Creative','submittedAt':'2026-08-01T10:00:00Z','submittedByEmail':'grace@swangzavenue.com','reason':'Shared work','requestStatus':'approved'}
        self.assertTrue(import_entries(self.db,[entry],apply=True)['errors'])
        entry['reviewed_departments']=['Creative']
        summary=import_entries(self.db,[entry],apply=True);self.assertEqual(summary['new']['department'],1)
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM hub_department_grants'),0)
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM procurement_requests'),0)
        self.assertEqual(import_entries(self.db,[entry],apply=True)['duplicates'],1)

    def test_notification_retry_never_reports_sent_or_duplicates_success(self):
        self.adoption()
        self.db.x("UPDATE hub_notifications SET email_state='failed',attempts=3")
        status,out=self.rig.api('GET','/hub/delivery');self.assertEqual(status,200);nid=out['items'][0]['id']
        self.assertEqual(self.rig.api('POST',f'/hub/delivery/{nid}/retry',{},who='billing')[0],403)
        status,out=self.rig.api('POST',f'/hub/delivery/{nid}/retry',{});self.assertEqual(status,200);self.assertFalse(out['sent'])
        self.db.x("UPDATE hub_notifications SET email_state='sent' WHERE id=?",(nid,))
        self.assertEqual(self.rig.api('POST',f'/hub/delivery/{nid}/retry',{})[0],409)

    def test_administrative_hourly_and_currency_values_do_not_change_staff_claims(self):
        r=self.adoption();original=self.db.q('SELECT * FROM hub_report_versions')
        self.assertIsNone(self.staff('GET','/hub/business')[1]['reports'][0]['allocated_time_value_usd'])
        body={'hourly_rate_usd':10,'usd_ugx':3700,'reason':'Synthetic administrative allocation, not market FX'}
        self.assertEqual(self.rig.api('PUT','/hub/business/settings',body,who='operations')[0],403)
        self.assertEqual(self.rig.api('PUT','/hub/business/settings',body,who='billing')[0],200)
        value=self.staff('GET','/hub/business')[1]['reports'][0]
        self.assertEqual(value['allocated_time_value_usd'],560)
        self.assertEqual(value['allocated_time_value_ugx'],2072000)
        self.assertEqual(value['net_savings_ugx'],1332000)
        self.assertEqual(self.db.q('SELECT * FROM hub_report_versions'),original)
        self.assertEqual(self.rig.api('PUT','/hub/business/settings',{'usd_ugx':0,'reason':'Invalid'})[0],400)

    def test_unused_declaration_does_not_generate_savings_and_roi_stays_finite(self):
        r=self.adoption(usage_confirmation='opened_not_used')
        self.assertIsNone(business.calculate(r)['time_saved_hours'])
        self.assertIsNone(business.calculate(r)['net_savings'])
        self.assertIsNone(business._roi(1e12,1e-300))

    def test_procurement_finance_correction_retains_original_proposal_and_denies_governance_only(self):
        status,r=self.staff('POST','/hub/procurement',{'tool_name':'New tool','purchase_type':'subscription','reason':'Proposal','estimated_monthly_cost':20})
        self.assertEqual(status,200);entitlements=self.db.q('SELECT * FROM entitlements');body={'version':0,'estimated_monthly_cost':30,'reason':'Reviewed vendor estimate'}
        self.assertEqual(self.rig.api('POST',f'/hub/procurement/{r["id"]}/pricing',body,who='operations')[0],403)
        self.assertEqual(self.rig.api('POST',f'/hub/procurement/{r["id"]}/pricing',body,who='billing')[0],200)
        out=self.staff('GET',f'/hub/procurement/{r["id"]}')[1]
        self.assertEqual(out['versions'][0]['snapshot']['estimated_monthly_cost'],20)
        self.assertEqual(out['estimated_monthly_cost'],30);self.assertEqual(out['submitter_email'],r['submitter_email'])
        self.assertEqual(self.rig.api('POST',f'/hub/procurement/{r["id"]}/pricing',body,who='billing')[0],409)
        self.assertEqual(self.db.q('SELECT * FROM entitlements'),entitlements)

    def test_procurement_repricing_requires_renewed_approval(self):
        _,r=self.staff('POST','/hub/procurement',{'tool_name':'Tool','purchase_type':'credits','reason':'Proposal','estimated_monthly_cost':20})
        self.rig.api('POST',f'/hub/procurement/{r["id"]}/review',{'state':'approved'})
        state,r=self.rig.api('POST',f'/hub/procurement/{r["id"]}/pricing',{'version':0,'reason':'Updated quote','estimated_monthly_cost':30})
        self.assertEqual(state,200);self.assertEqual(r['state'],'reviewed')
        self.assertEqual(self.rig.api('POST',f'/hub/procurement/{r["id"]}/review',{'state':'purchased','security_checked':True,'subscription_checked':True})[0],409)
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM procurement_reviews'),2)

    def test_procurement_association_preserves_author_and_does_not_create_access(self):
        _,r=self.staff('POST','/hub/procurement',{'tool_name':'Declared name','purchase_type':'licence','reason':'Proposal'})
        before=self.db.q('SELECT * FROM entitlements')
        status,out=self.rig.api('POST',f'/hub/procurement/{r["id"]}/attribution',{'version':0,'tool_id':'canva','person_id':None,'reason':'Historic matching'},who='operations')
        self.assertEqual(status,200);self.assertEqual(out['submitter_email'],r['submitter_email'])
        self.assertEqual(out['tool_name'],'Declared name');self.assertEqual(self.db.q('SELECT * FROM entitlements'),before)
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM procurement_versions'),2)

    def test_management_revisions_preserve_historical_snapshots_after_archival(self):
        r=self.adoption()
        period=reporting.week(self.rig.gw,time.time()-14*86400)
        self.db.x('UPDATE hub_reports SET created=? WHERE id=?',(period['starts']+60,r['id']))
        reporting.management_snapshot(self.rig.gw,period['week_start'])
        first=self.db.one('SELECT * FROM weekly_management_snapshots WHERE week_start=?',(period['week_start'],))
        self.assertEqual(len(json.loads(first['snapshot_json'])['adoption_declarations']),1)
        self.assertEqual(self.rig.api('POST','/hub/reports/archive',{'ids':[r['id']],'reason':'Historical duplicate'})[0],200)
        snapshots=self.db.q('SELECT * FROM weekly_management_snapshots WHERE week_start=? ORDER BY revision',(period['week_start'],))
        self.assertEqual(len(snapshots),2)
        self.assertEqual(snapshots[0],first)
        self.assertEqual(json.loads(snapshots[-1]['snapshot_json'])['adoption_declarations'],[])
