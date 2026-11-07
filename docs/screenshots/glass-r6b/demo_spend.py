"""Local fixture for the R6b chart check: the usual UI demo plus 30 days of synthetic priced requests (test database only)."""
import json, random, signal, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
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
    rig.gw.db.x("INSERT INTO admins(username,pw_hash,role,areas,created) VALUES(?,?,?,?,?)",
                ("operations@swangzavenue.com", security.hash_password("operations-password", 1000), *authz.stored("operations"), time.time()))
    rnd = random.Random(11)
    now = time.time()
    for d in range(30):
        for _ in range(0 if d % 11 == 6 else rnd.randint(3, 14)):
            # a gently rising spend with noise; costs are invented fixtures, not measured
            cost = round(rnd.uniform(0.04, 0.5) * (1.6 - d / 30), 4)
            rig.gw.db.x("INSERT INTO requests(ts,person_id,provider,method,path,kind,model,status,outcome,cost,in_tok,out_tok)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (now - d * 86400 - rnd.randint(0, 40000), rig.person_id, "anthropic", "POST", "/v1/messages", "chat",
                         "claude-sonnet", 200, "ok", cost, 800, 400))
    print(json.dumps({"url": rig.settings.public_url}), flush=True)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set()); signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()
finally:
    rig.close()
