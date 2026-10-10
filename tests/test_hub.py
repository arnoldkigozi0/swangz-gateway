import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from gateway import catalog, hub_delivery, reporting, security
from gateway.admin import ApiError, Ctx
from gateway.config import Settings
from gateway.db import DB, SCHEMA
from gateway.hub_import import import_entries, backup
from .support import Rig


class HubServiceTests(unittest.TestCase):
    def setUp(self):
        self.db=DB(':memory:');self.addCleanup(self.db.close)
        self.gw=SimpleNamespace(db=self.db,settings=Settings(),public_url=lambda:'https://hub.example.test')
        self.gw.audit=lambda actor,action,target='',detail='',**kw:self.db.x('INSERT INTO audit(ts,actor,action,target,detail) VALUES(?,?,?,?,?)',(time.time(),actor,action,target,detail))
        catalog.seed(self.db)
        self.pid=self.db.x("INSERT INTO people(name,email,department,created) VALUES('Grace','grace@swangzavenue.com','Creative',?)",(time.time(),)).lastrowid
        self.start=reporting.week(self.gw)['starts']-7*86400
        self.period=reporting.week(self.gw,self.start)

    def launch(self,tid='chatgpt',offset=100,outcome='opened'):
        return self.db.x('INSERT INTO launches(tool_id,person_id,ts,outcome) VALUES(?,?,?,?)',(tid,self.pid,self.start+offset,outcome)).lastrowid

    def report(self):
        self.launch();ids=reporting.compile_closed(self.gw);return ids[0]

    def claims(self,**changes):
        return {'usage_confirmation':'used','reason':'Campaign research','impact':'Staff-reported quality improvement','manual_hours':4,'ai_hours':1,**changes}

    def test_kampala_half_open_week_and_year_change(self):
        a=reporting.week(self.gw,datetime.fromisoformat('2026-01-04T20:59:59+00:00').timestamp())
        b=reporting.week(self.gw,datetime.fromisoformat('2026-01-04T21:00:00+00:00').timestamp())
        self.assertEqual(a['week_start'],'2025-12-29');self.assertEqual(b['week_start'],'2026-01-05')
        self.assertEqual(a['ends'],b['starts']);self.assertEqual(a['week_end'],'2026-01-04')
        with self.assertRaises(ApiError):reporting.bounds(self.gw,'2026-01-06')

    def test_configurable_timezone_dst_week_is_not_assumed_168_hours(self):
        self.gw.settings.company_timezone='Europe/London'
        w=reporting.bounds(self.gw,'2026-03-23')
        self.assertEqual(w['ends']-w['starts'],167*3600)

    def test_one_obligation_and_snapshot_per_pair_and_not_current_week(self):
        self.launch();self.launch(offset=200);self.launch('canva');self.launch(offset=7*86400+1)
        ids=reporting.compile_closed(self.gw)
        self.assertEqual(len(ids),2);self.assertEqual(reporting.compile_closed(self.gw),[])
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM weekly_evidence'),2)
        self.assertEqual(self.db.scalar("SELECT launches FROM weekly_evidence WHERE tool_id='chatgpt'"),2)

    def test_blocked_only_activity_does_not_invent_obligation(self):
        self.launch(outcome='refused')
        self.assertEqual(reporting.compile_closed(self.gw),[])

    def test_all_sources_and_independent_cost_provenance(self):
        self.launch()
        self.db.x("INSERT INTO requests(ts,person_id,provider,method,path,kind,client,outcome,in_tok,out_tok,cost,cost_source) VALUES(?,?,'openai','POST','/v1/responses','responses','curl','ok',100,50,0.25,'price:test@1')",(self.start+200,self.pid))
        self.db.x("INSERT INTO site_usage(tool_id,person_id,started,ended,seconds) VALUES('chatgpt',?,?,?,90)",(self.pid,self.start+300,self.start+390))
        rid=reporting.compile_closed(self.gw)[0];e=reporting.detail(self.gw,rid)['evidence']
        self.assertEqual((e['api_requests'],e['launches'],e['access_events'],e['tab_open_seconds']),(1,1,1,90))
        self.assertEqual(e['estimated_api_cost'],0.25);self.assertEqual(e['input_tokens'],100)
        self.assertTrue(any(x['cost_source']=='price:test@1' for x in e['events']))
        self.assertNotIn('prompt',e);self.assertEqual(e['active_days'],1)

    def test_snapshot_does_not_change_after_late_activity_or_declaration(self):
        rid=self.report();first=reporting.detail(self.gw,rid)['evidence']
        self.launch(offset=250);reporting.compile_closed(self.gw)
        reporting.save(self.gw,self.pid,rid,self.claims(),True)
        self.assertEqual(first,reporting.detail(self.gw,rid)['evidence'])
        self.gw.settings.company_timezone='Europe/London'
        self.assertEqual(reporting.detail(self.gw,rid)['period']['timezone'],'Africa/Kampala')

    def test_draft_does_not_clear_gate_submission_does(self):
        rid=self.report();reporting.save(self.gw,self.pid,rid,{'usage_confirmation':'','reason':'Draft'})
        self.assertIsNone(reporting.detail(self.gw,rid)['usage_confirmation'])
        self.assertEqual(reporting.gate(self.gw,self.pid,'chatgpt')['code'],'weekly_report_required')
        self.assertIsNone(reporting.gate(self.gw,self.pid,'canva'))
        reporting.save(self.gw,self.pid,rid,self.claims(),True)
        self.assertIsNone(reporting.gate(self.gw,self.pid,'chatgpt'))

    def test_concurrent_submission_is_idempotent(self):
        rid=self.report();results=[];errors=[]
        def submit():
            try:results.append(reporting.save(self.gw,self.pid,rid,self.claims(),True))
            except Exception as e:errors.append(e)
        threads=[threading.Thread(target=submit) for _ in range(4)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(errors,[]);self.assertEqual(len(results),4)
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM hub_report_versions'),1)

    def test_returns_preserve_original_and_require_resubmission(self):
        rid=self.report();reporting.save(self.gw,self.pid,rid,self.claims(),True)
        aid=self.db.x("INSERT INTO admins(username,pw_hash,role,created) VALUES('reviewer@swangzavenue.com','x','owner',0)").lastrowid
        ctx=SimpleNamespace(db=self.db,gw=self.gw,body={'state':'returned','note':'Explain the project'},admin={'id':aid,'username':'reviewer@swangzavenue.com'},audit=lambda *a,**k:None)
        reporting.review(ctx,rid)
        self.assertIsNotNone(reporting.gate(self.gw,self.pid,'chatgpt'))
        out=reporting.save(self.gw,self.pid,rid,self.claims(reason='Corrected project'),True)
        self.assertEqual(out['state'],'resubmitted');self.assertEqual(len(out['versions']),2)
        self.assertEqual(out['versions'][0]['declaration']['reason'],'Campaign research')
        self.assertIsNone(reporting.gate(self.gw,self.pid,'chatgpt'))

    def test_review_cannot_silently_edit_staff_declaration(self):
        rid=self.report();reporting.save(self.gw,self.pid,rid,self.claims(),True)
        with self.assertRaises(ApiError):reporting.save(self.gw,self.pid,rid,{'reason':'rewrite'})
        self.assertEqual(reporting.detail(self.gw,rid)['reason'],'Campaign research')

    def test_other_person_cannot_read_or_submit(self):
        rid=self.report()
        with self.assertRaises(ApiError):reporting.detail(self.gw,rid,self.pid+1)
        with self.assertRaises(ApiError):reporting.save(self.gw,self.pid+1,rid,self.claims(),True)

    def test_unknown_zero_and_hostile_input_are_distinct(self):
        rid=self.report();out=reporting.save(self.gw,self.pid,rid,self.claims(revenue=None,manual_cost=0),True)
        self.assertIsNone(out['revenue']);self.assertEqual(out['manual_cost'],0)
        for body in ({'revenue':float('nan')},{'manual_hours':-1},{'claimed_days':8},{'projects':[{'name':'P','link':'javascript:alert(1)'}]}):
            with self.assertRaises(ApiError):reporting.validate(body)

    def test_reconciliation_explains_mismatch_and_does_not_prove_savings(self):
        e={'api_requests':10,'api_success':10,'launches':0,'access_events':0,'shared_turns':0,'active_days':3,'completeness':'api_observed'}
        self.assertEqual(reporting.reconcile({'usage_confirmation':'used','claimed_requests':10},e)[0],'matched')
        self.assertEqual(reporting.reconcile({'usage_confirmation':'used','claimed_requests':10,'manual_hours':20},e)[0],'partially_matched')
        result,why=reporting.reconcile({'usage_confirmation':'used','claimed_requests':100},e)
        self.assertEqual(result,'needs_review');self.assertIn('100',why);self.assertIn('10',why)
        self.assertEqual(reporting.reconcile({},None)[0],'insufficient_telemetry')
        e.update(api_requests=0,api_success=0,launches=1,completeness='access_only')
        self.assertEqual(reporting.reconcile({'usage_confirmation':'opened_not_used'},e)[0],'insufficient_telemetry')
        e['launches']=0
        self.assertEqual(reporting.reconcile({},e)[0],'no_observed_activity')

    def test_override_has_exact_scope_and_expiry(self):
        rid=self.report();aid=self.db.x("INSERT INTO admins(username,pw_hash,role,created) VALUES('owner@swangzavenue.com','x','owner',0)").lastrowid
        now=time.time()
        self.db.x('INSERT INTO weekly_overrides(person_id,tool_id,starts,expires,admin_id,reason) VALUES(?,?,?,?,?,?)',(self.pid,'chatgpt',now-1,now+60,aid,'Incident response'))
        self.assertIsNone(reporting.gate(self.gw,self.pid,'chatgpt'))
        self.assertIsNotNone(reporting.gate(self.gw,self.pid,'chatgpt',now+61))

    def test_management_snapshots_are_historical_and_csv_safe(self):
        rid=self.report();before=self.db.q('SELECT * FROM weekly_management_snapshots')
        reporting.save(self.gw,self.pid,rid,self.claims(),True)
        after=self.db.q('SELECT * FROM weekly_management_snapshots')
        self.assertEqual(after[0],before[0]);self.assertGreater(len(after),len(before))
        csv=reporting.csv_bytes([{'value':'=HYPERLINK("evil")','unknown':None}],('value','unknown')).decode('utf-8-sig')
        self.assertIn("'=HYPERLINK",csv)

    def test_optional_email_failure_is_not_claimed_sent(self):
        reporting.notify_person(self.gw,self.pid,'x','An update','#/weekly')
        def fail(*a):raise OSError('server refused')
        with mock.patch.dict(os.environ,{'GATEWAY_SMTP_HOST':'smtp.test'}):
            self.assertEqual(hub_delivery.deliver(self.gw,fail),0)
        row=self.db.one('SELECT * FROM hub_notifications')
        self.assertEqual(row['email_state'],'failed');self.assertIsNone(row['emailed'])
        with mock.patch.dict(os.environ,{'GATEWAY_SMTP_HOST':'smtp.test'}):
            self.assertEqual(hub_delivery.deliver(self.gw,lambda *a:None),1)
        self.assertEqual(self.db.scalar('SELECT email_state FROM hub_notifications'),'sent')

    def test_historic_import_dry_run_idempotency_and_no_weekly_conversion(self):
        data=[{'id':'r1','tag':'report','toolName':'ChatGPT','submittedBy':'Grace','submittedByEmail':'grace@swangzavenue.com','department':'Creative','reason':'Research','tradTime':2,'tradTimeUnit':'d','aiTime':1,'aiTimeUnit':'h','submittedAt':'2026-08-01T10:00:00Z'},
              {'id':'p1','tag':'request','toolName':'New Tool','reason':'Need video','requestStatus':'new','submittedAt':'2026-08-02T10:00:00Z'},
              {'id':'t1','kind':'registry','toolName':'ChatGPT','officialUrl':'https://chatgpt.com/'}]
        before=self.db.q('SELECT * FROM tools');subs=self.db.q('SELECT * FROM subscriptions')
        dry=import_entries(self.db,data);self.assertEqual(dry['new'],{'adoption':1,'procurement':1,'registry':1})
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM hub_reports'),0)
        actual=import_entries(self.db,data,apply=True);self.assertTrue(actual['applied'])
        self.assertEqual(self.db.scalar('SELECT manual_hours FROM hub_reports'),16)
        self.assertEqual(self.db.scalar('SELECT purchase_type FROM procurement_requests'),'other')
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM weekly_evidence'),0)
        self.assertEqual(import_entries(self.db,data,apply=True)['duplicates'],3)
        self.assertEqual(self.db.q('SELECT * FROM tools'),before);self.assertEqual(self.db.q('SELECT * FROM subscriptions'),subs)
        data[0]['reason']='Changed upstream'
        self.assertEqual(len(import_entries(self.db,data,apply=True)['errors']),1)
        self.assertEqual(self.db.scalar('SELECT reason FROM hub_reports'),'Research')

    def test_import_validation_is_transactional_and_demo_skipped(self):
        data=[{'id':'demo','isDemo':True},{'id':'bad','toolName':'X','tag':'wrong'}]
        out=import_entries(self.db,data,apply=True)
        self.assertFalse(out['applied']);self.assertEqual(out['demo_skipped'],1)
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM tracker_imports'),0)

    def test_existing_v18_data_survives_migration_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=tmp+'/gateway.db'
            with mock.patch('gateway.db.SCHEMA',SCHEMA[:18]):old=DB(path)
            catalog.seed(old)
            old.x("INSERT INTO people(name,email,created) VALUES('Legacy','legacy@swangzavenue.com',1)")
            old.x("INSERT INTO entitlements(tool_id,person_id,granted) VALUES('codex',1,1)")
            old.x("INSERT INTO access_requests(tool_id,person_id,created) VALUES('chatgpt',1,1)")
            original={table:old.q('SELECT * FROM '+table) for table in ('people','tools','subscriptions','entitlements','access_requests')};old.close()
            info=backup(path,tmp+'/verified.db');self.assertEqual(info['integrity'],'ok')
            new=DB(path)
            self.assertEqual(new.scalar("SELECT v FROM meta WHERE k='schema'"),'19')
            for table,rows in original.items():self.assertEqual(new.q('SELECT * FROM '+table),rows)
            new.close();again=DB(path);again.close()
            with self.assertRaises(FileExistsError):backup(path,tmp+'/verified.db')


    def test_identity_recovery_requires_backup_preserves_ids_and_revokes_sessions(self):
        from gateway.hub_identity import migrate_admin, preflight
        with tempfile.TemporaryDirectory() as tmp:
            path=tmp+'/gateway.db';db=DB(path)
            aid=db.x("INSERT INTO admins(username,pw_hash,role,created) VALUES('legacy@gmail.com','hash','owner',1)").lastrowid
            db.x("INSERT INTO admin_sessions(token_hash,admin_id,created,expires) VALUES('session',?,1,9999999999)",(aid,));db.close()
            self.assertFalse(preflight(path)['administrators'][0]['allowed'])
            with self.assertRaises(ValueError):migrate_admin(path,aid,'outsider@gmail.com',tmp+'/invalid.db')
            result=migrate_admin(path,aid,'verified@swangzavenue.com',tmp+'/backup.db')
            self.assertEqual(result['id'],aid);db=DB(path)
            self.assertEqual(db.one('SELECT id,username,pw_hash,role FROM admins WHERE id=?',(aid,)),{'id':aid,'username':'verified@swangzavenue.com','pw_hash':'hash','role':'owner'})
            self.assertEqual(db.scalar('SELECT COUNT(*) FROM admin_sessions'),0)
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM audit WHERE action='migrated administrator identity'"),1);db.close()

    def test_import_preserves_project_methods_and_business_value(self):
        data=[{'id':'project-history','tag':'report','toolName':'ChatGPT','submittedByEmail':'grace@swangzavenue.com','submittedAt':'2026-08-01T10:00:00Z','reason':'Campaign','currency':'USD','selectedPlanName':'Production','usageIncluded':100,'usageUnitCostUSD':0.5,'usageCostUSD':20,'usageFlatRate':False,'projects':[{'name':'Campaign','traditional':'Manual drafts','aiWay':'AI outlines','benefit':'Faster iteration'}]}]
        result=import_entries(self.db,data,'project-test',{},True)
        self.assertFalse(result['errors']);row=self.db.one("SELECT * FROM hub_reports WHERE kind='adoption'")
        detail=reporting.detail(self.gw,row['id'])
        self.assertEqual((detail['selected_plan'],detail['usage_included'],detail['usage_unit_cost_usd'],detail['usage_cost_usd']),('Production',100,0.5,20))
        self.assertEqual(detail['usage_flat_rate'],0)
        p=detail['projects'][0]
        self.assertEqual((p['traditional'],p['ai_way'],p['benefit']),('Manual drafts','AI outlines','Faster iteration'))


    def test_shared_browser_turns_cannot_roll_over_into_unreported_week(self):
        from gateway import turns
        sunday_end=self.period['ends']
        tool=self.db.one("SELECT * FROM tools WHERE id='midjourney'");person=self.db.one('SELECT * FROM people WHERE id=?',(self.pid,))
        with mock.patch('gateway.turns.time.time',return_value=sunday_end-30):
            turn,_=turns.take(self.db,tool,person,week_ends=sunday_end)
        self.assertEqual(turn['expires'],sunday_end)
        self.assertEqual(reporting.close_week_turns(self.gw,sunday_end+1),1)
        self.assertEqual(self.db.one('SELECT ended,reason FROM tool_turns WHERE id=?',(turn['id'],)),{'ended':sunday_end,'reason':'weekly reporting boundary'})
        self.assertEqual(reporting.close_week_turns(self.gw,sunday_end+1),0)


    def test_submission_actor_uses_current_verified_identity_without_rewriting_snapshot(self):
        rid=self.report()
        self.db.x("UPDATE people SET email='renamed@swangzavenue.com' WHERE id=?",(self.pid,))
        result=reporting.save(self.gw,self.pid,rid,self.claims(),True)
        self.assertEqual(result['versions'][0]['actor'],'renamed@swangzavenue.com')
        self.assertEqual(result['submitter_email'],'grace@swangzavenue.com')


    def test_import_refuses_ambiguous_legacy_currency_without_writing(self):
        data=[{'id':'currency-history','tag':'report','toolName':'ChatGPT','submittedAt':'2026-08-01T10:00:00Z','tradCost':380000}]
        result=import_entries(self.db,data,apply=True)
        self.assertTrue(result['errors']);self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM tracker_imports'),0)
        data[0]['currency']='UGX';result=import_entries(self.db,data,apply=True)
        self.assertFalse(result['errors']);self.assertEqual(self.db.one("SELECT currency,manual_cost FROM hub_reports WHERE kind='adoption'"),{'currency':'UGX','manual_cost':380000})


    def test_tracker_department_access_is_not_misclassified_as_procurement(self):
        data=[{'id':'legacy-access','kind':'access','tag':'request','toolName':'Department access: Creative','submittedAt':'2026-08-01T10:00:00Z'}]
        result=import_entries(self.db,data,apply=True)
        self.assertTrue(result['errors']);self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM procurement_requests'),0)


    def test_management_separates_adoption_value_from_weekly_usage(self):
        rid=self.report();reporting.save(self.gw,self.pid,rid,self.claims(),True)
        aid=self.db.x("INSERT INTO hub_reports(kind,person_id,tool_id,submitter_name,tool_name,created,updated,state,impact) VALUES('adoption',?,'chatgpt','Grace','ChatGPT',?,?,'submitted','Campaign value')",(self.pid,self.start+10,self.start+10)).lastrowid
        reporting.management_snapshot(self.gw,self.period['week_start'])
        raw=self.db.one('SELECT snapshot_json FROM weekly_management_snapshots ORDER BY id DESC LIMIT 1')
        snapshot=json.loads(raw['snapshot_json'])
        self.assertEqual([r['id'] for r in snapshot['reports']],[rid]);self.assertEqual([r['id'] for r in snapshot['adoption_declarations']],[aid])
        self.assertEqual(snapshot['totals']['observed']['launches'],1)


    def test_compilation_watermarks_skip_full_history_but_keep_late_events_and_rollover(self):
        self.report()
        with mock.patch('gateway.reporting._events',wraps=reporting._events) as events:
            self.assertEqual(reporting.compile_closed(self.gw),[]);events.assert_not_called()
            self.assertEqual(reporting.gate(self.gw,self.pid,'chatgpt')['code'],'weekly_report_required');events.assert_not_called()
        self.launch(offset=7*86400+60)
        self.assertEqual(reporting.compile_closed(self.gw),[])
        self.launch('canva')
        self.assertEqual(len(reporting.compile_closed(self.gw)),1)
        self.assertEqual(len(reporting.compile_closed(self.gw,now=self.period['ends']+7*86400+1)),1)
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM weekly_evidence'),3)


class HubHTTPTests(unittest.TestCase):
    def setUp(self):
        self.rig=Rig();self.addCleanup(self.rig.close)
        self.db=self.rig.gw.db;self.pid=self.rig.person_id
        self.token='hub-staff-token';now=time.time()
        self.db.x('INSERT INTO staff_sessions(token_hash,person_id,created,expires) VALUES(?,?,?,?)',(security.sha256(self.token),self.pid,now,now+3600))
        self.headers={'authorization':'Bearer '+self.token,'x-swangz-app':'1'}
        self.start=reporting.week(self.rig.gw)['starts']-7*86400

    def staff(self,method,path,body=None):
        status,headers,data=self.rig.request(method,'/api'+path,body,self.headers)
        return status,json.loads(data)

    def obligation(self,tid='chatgpt'):
        self.db.x('INSERT INTO launches(tool_id,person_id,ts,outcome) VALUES(?,?,?,?)',(tid,self.pid,self.start+100,'opened'))
        return reporting.compile_closed(self.rig.gw)[0]

    def test_launch_extension_and_proxy_gate_and_post_submission_independent_controls(self):
        rid=self.obligation('codex')
        self.assertEqual(self.rig.request('GET','/go/codex',headers={'cookie':'sgw_staff='+self.token})[0],303)
        denied=self.rig.openai('/responses',{'model':'gpt-5','input':'hi'})
        self.assertEqual(denied[0],403);self.assertEqual(json.loads(denied[2])['error']['code'],'weekly_report_required')
        # A spoofed user agent cannot bypass an outstanding report on an unscoped old key.
        denied=self.rig.openai('/responses',{'model':'gpt-5','input':'hi'},extra={'user-agent':'curl'})
        self.assertEqual(denied[0],403)
        self.assertEqual(self.staff('PUT',f'/hub/reports/{rid}',{'reason':'draft'})[0],200)
        self.assertEqual(self.staff('POST',f'/hub/reports/{rid}/submit',{'usage_confirmation':'used','reason':'Code review'})[0],200)
        self.assertEqual(self.rig.openai('/responses',{'model':'gpt-5','input':'hi'})[0],200)
        self.db.x("UPDATE people SET status='suspended' WHERE id=?",(self.pid,))
        self.assertEqual(self.rig.openai('/responses',{'model':'gpt-5','input':'hi'})[0],403)
        self.assertEqual(self.staff('GET','/hub/reports')[0],200) # reports/help remain accessible

    def test_extension_and_studio_machine_readable_denials(self):
        rid=self.obligation('elevenlabs')
        self.rig.api('POST',f'/people/{self.pid}/tools/elevenlabs')
        state,data=self.staff('POST','/gate/open',{'host':'elevenlabs.io'})
        self.assertEqual(state,200);self.assertFalse(data['allowed']);self.assertEqual(data['report_gate']['report_id'],rid)
        state,data=self.staff('POST','/studio/voice',{'text':'Test','voice_id':'voice123'})
        self.assertEqual(state,403);self.assertEqual(data['code'],'weekly_report_required')

    def test_procurement_does_not_grant_access_and_roles_are_enforced(self):
        status,item=self.staff('POST','/hub/procurement',{'tool_name':'Canva','purchase_type':'subscription','reason':'Design work','tool_id':'canva'})
        self.assertEqual(status,200)
        self.assertEqual(self.rig.api('POST',f'/hub/procurement/{item["id"]}/review',{'state':'approved'},who='viewer')[0],403)
        status,out=self.rig.api('POST',f'/hub/procurement/{item["id"]}/review',{'state':'approved'})
        self.assertEqual(status,200);self.assertFalse(out['access_granted'])
        self.assertFalse(self.db.one("SELECT 1 FROM entitlements WHERE person_id=? AND tool_id='canva'",(self.pid,)))
        self.assertEqual(self.db.scalar('SELECT COUNT(*) FROM access_requests'),0)
        self.assertEqual(self.rig.api('POST',f'/hub/procurement/{item["id"]}/review',{'state':'purchased'})[0],400)

    def test_report_review_and_emergency_override_need_authority_and_reason(self):
        rid=self.obligation()
        self.assertEqual(self.rig.api('POST',f'/hub/reports/{rid}/review',{'state':'reviewed'},who='viewer')[0],403)
        self.assertEqual(self.rig.api('POST','/hub/override',{'person_id':self.pid,'tool_id':'chatgpt'},who='owner')[0],400)
        status,out=self.rig.api('POST','/hub/override',{'person_id':self.pid,'tool_id':'chatgpt','reason':'Incident response','hours':1})
        self.assertEqual(status,200);self.assertIsNone(reporting.gate(self.rig.gw,self.pid,'chatgpt'))
        self.assertTrue(self.db.one("SELECT 1 FROM audit WHERE action='authorised an emergency reporting override'"))

    def test_exact_domain_for_admin_staff_sessions_keys_and_named_exceptions(self):
        allowed=('a@swangzavenue.com',' ArnoldKigozi0@gmail.com ','marvinmusokessekatawa@gmail.com')
        denied=('x@gmail.com','webdev02022007@gmail.com','x@swangzavenue.com.evil.test','x@sub.swangzavenue.com','x@@swangzavenue.com')
        for email in allowed:self.assertTrue(self.rig.settings.email_allowed(email))
        for email in denied:self.assertFalse(self.rig.settings.email_allowed(email))
        self.rig.settings.email_exceptions=frozenset({'evil@gmail.com'})
        self.assertFalse(self.rig.settings.email_allowed('evil@gmail.com'))
        self.assertEqual(self.rig.api('POST','/admins',{'username':'outsider@gmail.com','password':'a-long-password','role':'owner'})[0],400)
        self.db.x("UPDATE people SET email='outsider@gmail.com' WHERE id=?",(self.pid,))
        self.assertEqual(self.staff('GET','/hub/reports')[0],401)
        self.assertEqual(self.rig.openai('/responses',{'model':'gpt-5','input':'hi'})[0],401)


    def test_no_role_creates_an_additional_personal_email_exception(self):
        from gateway import authz
        for role in authz.ROLES:
            with self.subTest(role=role):
                status,_=self.rig.api('POST','/admins',{'username':role+'@gmail.com','password':'a-long-password','role':role})
                self.assertEqual(status,400)
                status,_=self.rig.api('POST','/admins',{'username':role+'-new@swangzavenue.com','password':'a-long-password','role':role})
                self.assertEqual(status,200)
        self.assertEqual(self.rig.api('POST','/admins',{'username':'custom@gmail.com','password':'a-long-password','role':'custom','areas':['govern']})[0],400)
        aid=self.db.x("INSERT INTO admins(username,pw_hash,role,created) VALUES('legacy@gmail.com','x','viewer',0)").lastrowid
        self.assertEqual(self.rig.api('PATCH',f'/admins/{aid}',{'role':'owner'})[0],400)
        self.assertEqual(self.rig.api('POST','/people',{'name':'Outside','email':'outside@gmail.com'})[0],400)
        self.assertEqual(self.rig.request('POST','/admin/api/people',{'name':'No email'},{'cookie':self.rig.cookies['owner'],'x-gateway-admin':'1'})[0],400)
        self.assertEqual(self.rig.api('PATCH',f'/people/{self.pid}',{'email':'outside@gmail.com'})[0],400)

    def test_both_named_owners_can_sign_in_but_other_legacy_admins_cannot(self):
        password='approved-owner-password'
        for email in ['arnoldkigozi0@gmail.com','marvinmusokessekatawa@gmail.com','other-owner@gmail.com']:
            self.db.x("INSERT INTO admins(username,pw_hash,role,created) VALUES(?,?,'owner',0)",(email,security.hash_password(password,1000)))
            status,_,_=self.rig.request('POST','/admin/api/login',{'username':email,'password':password},headers={'x-gateway-admin':'1'})
            self.assertEqual(status,401 if email.startswith('other') else 200)


    def test_management_exports_are_authenticated_and_preserve_historical_revision(self):
        rid=self.obligation();reporting.save(self.rig.gw,self.pid,rid,{'usage_confirmation':'used','reason':'<script>unsafe</script>','impact':'<b>estimate</b>'},True)
        week=self.db.one('SELECT week_start FROM hub_reports WHERE id=?',(rid,))['week_start']
        status,data=self.rig.api('GET','/hub/management?week='+week);self.assertEqual(status,200)
        revision=data['revision'];self.assertIn('totals',data['snapshot'])
        status,html=self.rig.api('GET',f'/hub/print?week={week}&revision={revision}');self.assertEqual(status,200)
        self.assertNotIn(b'<b>estimate</b>',html);self.assertIn(b'&lt;b&gt;estimate&lt;/b&gt;',html)
        self.assertEqual(self.staff('GET','/hub/management')[0],404)
        reporting.review(SimpleNamespace(db=self.db,gw=self.rig.gw,body={'state':'returned','note':'Correct it'},admin={'id':self.db.scalar("SELECT id FROM admins WHERE role='owner' LIMIT 1"),'username':'owner@swangzavenue.com'},audit=lambda *a,**kw:None),rid)
        status,csv=self.rig.api('GET',f'/hub/export?week={week}&revision={revision}');self.assertEqual(status,200)
        self.assertIn(b'submitted',csv);self.assertNotIn(b'returned',csv)
        self.assertEqual(self.rig.request('GET','/admin/api/hub/print?week='+week)[0],401)
        self.assertEqual(self.rig.api('GET','/hub/trends')[0],200)
