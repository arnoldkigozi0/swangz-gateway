"""python3 -m gateway <command>

  serve                         run the gateway and the console
  add-admin USER [--viewer]     create a console user (asks for the password)
  add-person NAME [--department D] [--email E]
  issue-key PERSON_ID [--label L]
  revoke-key KEY_ID
  people                        list people and their keys
  pause | resume                stop / restart AI access for everyone
  purge                         apply the retention window now

The command line works on the same database as a running gateway. One difference: a revoke or
pause made here is enforced from the next request on; only the console can also cut requests
that are already streaming.
"""

import argparse
import getpass
import os
import sys
import time

from . import pricing, security, store
from .config import Settings, load_dotenv
from .db import DB


def main(argv=None):
    load_dotenv(os.environ.get("GATEWAY_ENV_FILE", ".env"))
    parser = argparse.ArgumentParser(prog="python3 -m gateway", description="Swangz AI Gateway")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    p = sub.add_parser("add-admin")
    p.add_argument("username")
    p.add_argument("--viewer", action="store_true", help="can see everything, change nothing")
    p = sub.add_parser("add-person")
    p.add_argument("name")
    p.add_argument("--department", default="")
    p.add_argument("--email", default="")
    p = sub.add_parser("issue-key")
    p.add_argument("person_id", type=int)
    p.add_argument("--label", default="key")
    p = sub.add_parser("revoke-key")
    p.add_argument("key_id")
    sub.add_parser("people")
    sub.add_parser("pause")
    sub.add_parser("resume")
    sub.add_parser("purge")
    args = parser.parse_args(argv)
    settings = Settings.from_env()

    if args.cmd == "serve":
        return serve(settings)

    db = DB(settings.db_path)
    pricing.seed(db)

    def audit(action, target="", detail=""):
        db.x("INSERT INTO audit(ts, actor, action, target, detail, ip) VALUES(?,?,?,?,?,?)",
             (time.time(), "command line", action, target, detail, ""))

    if args.cmd == "add-admin":
        if db.one("SELECT id FROM admins WHERE username = ?", (args.username,)):
            sys.exit(f"{args.username} already exists")
        pw = getpass.getpass("Password (10+ characters): ")
        if len(pw) < 10 or pw != getpass.getpass("Again: "):
            sys.exit("passwords must match and be at least 10 characters")
        role = "viewer" if args.viewer else "owner"
        db.x("INSERT INTO admins(username, pw_hash, role, created) VALUES(?,?,?,?)",
             (args.username, security.hash_password(pw, settings.pbkdf2_iterations), role, time.time()))
        audit("added a console user", args.username, role)
        print(f"{role} {args.username} created")
    elif args.cmd == "add-person":
        cur = db.x("INSERT INTO people(name, department, email, created) VALUES(?,?,?,?)",
                   (args.name, args.department, args.email, time.time()))
        audit("added a person", args.name)
        print(f"person #{cur.lastrowid} {args.name}")
    elif args.cmd == "issue-key":
        person = db.one("SELECT name FROM people WHERE id = ?", (args.person_id,))
        if not person:
            sys.exit("no such person")
        key_id, full, secret_hash, hint = security.new_key()
        db.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created, created_by) VALUES(?,?,?,?,?,?,?)",
             (key_id, args.person_id, args.label, secret_hash, hint, time.time(), "command line"))
        audit("issued a key", person["name"], f"{args.label} ({hint})")
        print(f"Key for {person['name']} — shown once, copy it now:\n\n  {full}\n")
        print(f"Claude Code:  ANTHROPIC_BASE_URL={settings.base_url()}/anthropic  ANTHROPIC_AUTH_TOKEN=<key>")
        print(f"Codex / OpenAI tools:  base_url {settings.base_url()}/openai/v1  key <key>")
    elif args.cmd == "revoke-key":
        row = db.one("SELECT k.*, p.name FROM keys k JOIN people p ON p.id = k.person_id WHERE k.id = ?", (args.key_id,))
        if not row:
            sys.exit("no such key")
        db.x("UPDATE keys SET revoked = ?, revoked_by = ? WHERE id = ? AND revoked IS NULL",
             (time.time(), "command line", args.key_id))
        audit("revoked a key", row["name"], f"{row['label']} ({row['hint']})")
        print(f"revoked {row['hint']} ({row['name']})")
    elif args.cmd == "people":
        for p in db.q("SELECT * FROM people ORDER BY name"):
            print(f"#{p['id']:<4} {p['name']:<28} {p['department']:<16} {p['status']}")
            for k in db.q("SELECT * FROM keys WHERE person_id = ? ORDER BY created", (p["id"],)):
                state = "revoked" if k["revoked"] else "active"
                print(f"        {k['id']}  {k['label']:<20} {k['hint']:<28} {state}")
    elif args.cmd in ("pause", "resume"):
        db.set_setting("paused", "1" if args.cmd == "pause" else "0")
        audit("paused AI access for everyone" if args.cmd == "pause" else "resumed AI access for everyone")
        print("paused" if args.cmd == "pause" else "resumed")
    elif args.cmd == "purge":
        days = int(db.get_setting("retention_days", "90") or 0)
        removed, orphans = store.purge(db, days)
        print(f"removed {removed} records older than {days} days and {orphans} unreferenced bodies")


def serve(settings):
    from .server import make_server

    server, gw = make_server(settings)
    gw.start_maintenance()
    from . import icons

    icons.start(gw.db, gw.log)  # tool logos for the catalog, fetched once in the background
    configured = [p.name for p in settings.providers.values() if p.api_key()]
    missing = [p.name for p in settings.providers.values() if not p.api_key()]
    gw.log(f"Swangz AI Gateway on {settings.base_url()}  (listening {settings.host}:{settings.port})")
    gw.log(f"providers with keys: {', '.join(configured) or 'none'}" + (f"; without: {', '.join(missing)}" if missing else ""))
    if not gw.db.scalar("SELECT COUNT(*) FROM admins"):
        gw.log("no console users yet — run: python3 -m gateway add-admin <name>")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
