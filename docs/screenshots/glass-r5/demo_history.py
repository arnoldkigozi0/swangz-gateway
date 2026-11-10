"""Local fixture for the R5 chart check: the usual UI demo plus 30 days of synthetic tool opens (test database only)."""
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
    rnd = random.Random(7)
    now = time.time()
    for d in range(30):
        for _ in range(0 if d % 9 == 4 else rnd.randint(2, 22)):
            rig.gw.db.x("INSERT INTO launches(tool_id,person_id,ts,outcome) VALUES(?,?,?,'opened')",
                        (rnd.choice(("canva", "chatgpt", "claude", "midjourney")), rig.person_id, now - d * 86400 - rnd.randint(0, 40000)))
    print(json.dumps({"url": rig.settings.public_url}), flush=True)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set()); signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()
finally:
    rig.close()
