"""Explicit synthetic staging entrypoint; never called by production gateway serve."""
import os
import signal
import sqlite3
import threading
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from gateway import catalog, reporting, security
from gateway.config import Provider, Settings
from gateway.server import make_server
from tests.fake_upstream import FakeUpstream


def settings():
    if os.environ.get('GATEWAY_STAGING')!='synthetic':
        raise ValueError('This entrypoint requires GATEWAY_STAGING=synthetic and a dedicated volume.')
    if any(os.environ.get(k) for k in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','ELEVENLABS_API_KEY','HIGGSFIELD_CREDENTIALS','GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GATEWAY_SMTP_HOST')):
        raise ValueError('Staging refuses production providers, OAuth and outbound notifications.')
    data=Path(os.environ.get('GATEWAY_DATA','/data')).resolve()
    if str(data) in ('/','/opt/swangz-gateway/data'):
        raise ValueError('Use a dedicated staging data directory.')
    existing=data/'gateway.db'
    if existing.exists():
        # Read-only preflight happens before make_server can run migrations or bootstrap.
        with sqlite3.connect(existing.as_uri()+'?mode=ro',uri=True) as check:
            marker=check.execute("SELECT v FROM settings WHERE k='synthetic_staging'").fetchone()
            if not marker or marker[0]!='1':
                raise ValueError('Unmarked database refused before opening or migrating it.')
    public=os.environ.get('GATEWAY_PUBLIC_URL','')
    host=urlsplit(public).hostname or ''
    if host not in ('localhost','127.0.0.1') and not host.endswith('.up.railway.app'):
        raise ValueError('Configure the separate Railway staging URL; production hosts are refused.')
    cfg=Settings.from_env()
    cfg.host='0.0.0.0';cfg.data_dir=str(data);cfg.public_url=public;cfg.web_url=public
    cfg.bootstrap_admin='';cfg.bootstrap_password=''
    return cfg


def seed(gw):
    db=gw.db
    owner=os.environ.get('STAGING_OWNER_EMAIL','').strip().lower()
    owner_pw=os.environ.get('STAGING_OWNER_PASSWORD','')
    staff_pw=os.environ.get('STAGING_STAFF_PASSWORD','')
    if not gw.settings.email_allowed(owner) or len(owner_pw)<14 or len(staff_pw)<14:
        raise ValueError('Configure an allowed staging owner and separate passwords of at least 14 characters.')
    # Prevent accidental seeding into an existing live volume. Only this marker authorises resumed staging.
    if db.scalar('SELECT COUNT(*) FROM people') and db.get_setting('synthetic_staging','')!='1':
        raise ValueError('Nonempty unmarked database refused; mount a dedicated empty staging volume.')
    with db.tx():
        db.set_setting('synthetic_staging','1')
        if not db.one('SELECT id FROM admins WHERE username=?',(owner,)):
            db.x("INSERT INTO admins(username,pw_hash,role,created) VALUES(?,?,'owner',?)",(owner,security.hash_password(owner_pw,gw.settings.pbkdf2_iterations),time.time()))
        email='staging-fixture@swangzavenue.com'
        person=db.one('SELECT id FROM people WHERE email=?',(email,))
        if not person:
            pid=db.x("INSERT INTO people(name,email,department,pw_hash,created) VALUES('Synthetic staging staff',?,'Staging fixtures',?,?)",(email,security.hash_password(staff_pw,gw.settings.pbkdf2_iterations),time.time())).lastrowid
            for tool in ('chatgpt','canva'):
                db.x("INSERT INTO subscriptions(tool_id,state,monthly_cost,seats,updated) VALUES(?,'active',30,2,?) ON CONFLICT(tool_id) DO NOTHING",(tool,time.time()))
                db.x('INSERT INTO entitlements(tool_id,person_id,granted) VALUES(?,?,?)',(tool,pid,time.time()))
            start=reporting.week(gw)['starts']-7*86400
            db.x("INSERT INTO launches(tool_id,person_id,ts,outcome) VALUES('chatgpt',?,?,'opened')",(pid,start+60))
        else:pid=person['id']
    reporting.compile_closed(gw)
    return pid


def main():
    cfg=settings();fake=FakeUpstream()
    os.environ['STAGING_FAKE_TOKEN']='local-stand-in'
    cfg.providers={name:Provider(name,fake.url,'STAGING_FAKE_TOKEN',name) for name in ('anthropic','openai','elevenlabs','higgsfield')}
    server,gw=make_server(cfg)
    try:
        seed(gw)
        signal.signal(signal.SIGTERM,lambda *_:threading.Thread(target=server.shutdown,daemon=True).start())
        print('Swangz AI Hub synthetic staging ready; persistent volume verified.',flush=True)
        server.serve_forever()
    finally:
        server.server_close();gw.db.close();fake.close()


if __name__=='__main__':main()
