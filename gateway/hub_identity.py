"""Read-only identity preflight and explicit, backed-up administrator recovery.

python3 -m gateway.hub_identity --database data/gateway.sqlite3
python3 -m gateway.hub_identity --database ... --admin-id N --email verified@swangzavenue.com --apply --backup /private/new-backup.sqlite3
"""
import argparse
import json
import sqlite3
import time
from pathlib import Path
from .config import Settings
from .db import DB
from .hub_import import backup


def preflight(path):
    settings = Settings()
    conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        result = {'policy': 'Exact @swangzavenue.com, plus only the two approved owner identities',
                  'administrators': [], 'staff': []}
        for table, field, output in [('admins', 'username', 'administrators'), ('people', 'email', 'staff')]:
            for row in conn.execute(f'SELECT id,{field} AS email FROM {table} ORDER BY id'):
                result[output].append({'id': row['id'], 'email': row['email'], 'allowed': settings.email_allowed(row['email'])})
        return result
    finally:
        conn.close()


def migrate_admin(path, admin_id, email, backup_path):
    email = email.strip().lower()
    if not Settings().email_allowed(email):
        raise ValueError(Settings().email_rule())
    verified = backup(path, backup_path)
    db = DB(path)
    try:
        with db.tx():
            row = db.one('SELECT id,username FROM admins WHERE id=?', (admin_id,))
            if not row:
                raise ValueError('Administrator not found.')
            if db.one('SELECT id FROM admins WHERE lower(username)=? AND id!=?', (email, admin_id)):
                raise ValueError('That identity already belongs to another administrator.')
            db.x('UPDATE admins SET username=? WHERE id=?', (email, admin_id))
            db.x('DELETE FROM admin_sessions WHERE admin_id=?', (admin_id,))
            db.x('INSERT INTO audit(ts,actor,action,target,detail,ip) VALUES(?,?,?,?,?,?)',
                 (time.time(), 'command line', 'migrated administrator identity', str(admin_id),
                  json.dumps({'previous': row['username'], 'email': email, 'sessions_revoked': True}), ''))
        return {'id': admin_id, 'email': email, 'backup': verified, 'historical_records_preserved': True}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description='Swangz AI Hub identity preflight / recovery')
    parser.add_argument('--database', required=True)
    parser.add_argument('--admin-id', type=int)
    parser.add_argument('--email')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup')
    args = parser.parse_args()
    if args.apply:
        if not args.admin_id or not args.email or not args.backup:
            parser.error('--apply requires --admin-id, --email and a new --backup path')
        print(json.dumps(migrate_admin(args.database, args.admin_id, args.email, args.backup), indent=2))
    else:
        print(json.dumps(preflight(args.database), indent=2))


if __name__ == '__main__':
    main()
