"""Temporary local fixtures for UI checks; all provider traffic uses FakeUpstream."""
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from gateway import authz, security
from tests.support import Rig

rig = Rig()
try:
    rig.settings.public_url = f"http://127.0.0.1:{rig.port}"
    rig.gw.db.x("UPDATE people SET email=?, pw_hash=? WHERE id=?",
                ("grace@swangzavenue.com", security.hash_password("demo-password", 1000), rig.person_id))
    for tool in ("canva", "chatgpt", "claude", "midjourney"):
        assert rig.api("PUT", f"/subscriptions/{tool}", {"state": "active", "monthly_cost": 30, "seats": 5})[0] == 200
        assert rig.api("POST", f"/people/{rig.person_id}/tools/{tool}")[0] == 200
    for role in ("operations", "security", "billing"):
        rig.gw.db.x("INSERT INTO admins(username,pw_hash,role,areas,created) VALUES(?,?,?,?,?)",
                    (role + "@swangzavenue.com", security.hash_password(role + "-password", 1000), *authz.stored(role), time.time()))
    for _ in range(3):
        assert rig.anthropic({"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "Local UI test fixture"}]},
                             extra={"x-claude-code-session-id": "local-ui-session"})[0] == 200
    reports=[]
    if os.environ.get("HUB_UI_FIXTURE"):
        from gateway import reporting
        start=reporting.week(rig.gw)['starts']-7*86400
        for tool in ('chatgpt','canva'):
            rig.gw.db.x("INSERT INTO launches(tool_id,person_id,ts,outcome) VALUES(?,?,?,'opened')",(tool,rig.person_id,start+60))
        reports=reporting.compile_closed(rig.gw)
    if os.environ.get("HUB_BUSINESS_FIXTURE"):
        from gateway import reporting
        for i,tool in enumerate(('chatgpt','canva','claude')):
            t=rig.gw.db.one('SELECT * FROM tools WHERE id=?',(tool,))
            rid=rig.gw.db.x("INSERT INTO hub_reports(kind,person_id,tool_id,department,submitter_name,submitter_email,tool_name,official_url,category,created,updated) VALUES('adoption',?,?,?,?,?,?,?,?,?,?)",(rig.person_id,tool,'Creative','Nansubuga Grace','grace@swangzavenue.com',t['name'],t['url'],t['category'],time.time()-i*30*86400,time.time())).lastrowid
            reporting.save(rig.gw,rig.person_id,rid,{'usage_confirmation':'used','reason':'Synthetic production research','impact':'A clearer client proposal','quality':'Reported faster iteration','manual_hours':16-i*2,'ai_hours':2,'manual_unit':'d','frequency':4,'frequency_period':'month','manual_cost':100,'ai_cost':5,'subscription_cost':30,'extra_credits':0,'other_expenses':0,'currency':'USD','projects':[{'name':'Synthetic project '+str(i+1),'description':'Client presentation deliverable','traditional':'Manual research and drafts','ai_way':'Assisted outlines','benefit':'More iterations in the same working time','link':'https://example.test/project'}]},True)
    print(json.dumps({"reports": reports, "url": rig.settings.public_url, "person": rig.person_id, "key": rig.key_id, "session": "local-ui-session"}), flush=True)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()
finally:
    rig.close()
