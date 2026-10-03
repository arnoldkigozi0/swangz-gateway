#!/usr/bin/env bash
# Set up the Swangz AI Gateway on a fresh Ubuntu server (22.04 or 24.04). Run as root, from a copy of
# the repo on that server:
#
#   sudo bash deploy/setup-gateway-server.sh ai.swangzavenue.com
#
# The name must already point at this server (an A record). No domain to hand? Use the server's IP
# written with dashes plus .sslip.io — e.g. 203-0-113-7.sslip.io points at 203.0.113.7 — and Caddy
# still gets a real https certificate for it.
#
# Installs Python and Caddy, puts the gateway in /opt/swangz-gateway under its own user, writes .env
# from .env.example the first time (never overwrites it, or the database), and starts both services.
# Safe to run again after pulling new code: it updates the code and restarts the gateway.
set -euo pipefail

DOMAIN="${1:?usage: setup-gateway-server.sh <domain, e.g. ai.swangzavenue.com> [web address, default https://swangz-ai.netlify.app]}"
WEB_URL="${2:-https://swangz-ai.netlify.app}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/swangz-gateway
[ "$(id -u)" = 0 ] || { echo "Run it as root: sudo bash $0 $*" >&2; exit 1; }

echo "== packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 rsync curl gnupg debian-keyring debian-archive-keyring apt-transport-https >/dev/null
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Python 3.10+ is needed")'
if ! command -v caddy >/dev/null; then  # Caddy's own package repository (caddyserver.com/docs/install)
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy >/dev/null
fi

echo "== the gateway, in $APP"
id swangz >/dev/null 2>&1 || useradd --system --home-dir "$APP" --shell /usr/sbin/nologin swangz
mkdir -p "$APP/data"
rsync -a --delete --exclude .git --exclude data --exclude .env --exclude __pycache__ "$SRC/" "$APP/"
if [ ! -f "$APP/.env" ]; then
  sed -e "s#^GATEWAY_PUBLIC_URL=.*#GATEWAY_PUBLIC_URL=https://$DOMAIN#" \
      -e "s#^GATEWAY_WEB_URL=.*#GATEWAY_WEB_URL=$WEB_URL#" \
      "$SRC/.env.example" > "$APP/.env"
  echo "   wrote $APP/.env — add the provider keys and the Google client to it"
fi
chown -R swangz:swangz "$APP/data" "$APP/.env"
chmod 600 "$APP/.env"

echo "== Caddy: https://$DOMAIN"
sed "s#^ai.example.com {#$DOMAIN {#" "$SRC/deploy/Caddyfile" > /etc/caddy/Caddyfile
systemctl enable -q caddy
systemctl restart caddy

echo "== the service"
cp "$SRC/deploy/swangz-gateway.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable -q swangz-gateway
systemctl restart swangz-gateway
for _ in $(seq 1 20); do
  curl -fsS http://127.0.0.1:8787/healthz >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS http://127.0.0.1:8787/healthz >/dev/null || { journalctl -u swangz-gateway -n 30 --no-pager; exit 1; }

echo
echo "The gateway is running. Next:"
echo "  - https://$DOMAIN/healthz should answer {\"ok\": true} (the certificate can take a minute)"
echo "  - Netlify: set SWANGZ_GATEWAY=https://$DOMAIN and redeploy"
echo "  - moving from another machine? stop the gateway there, then copy its data/gateway.db to"
echo "    $APP/data/ (chown swangz:swangz) and run: systemctl restart swangz-gateway"
echo "  - logs: journalctl -u swangz-gateway -f"
