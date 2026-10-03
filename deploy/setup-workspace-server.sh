#!/usr/bin/env bash
# Set up the workspace server — the company browsers for shared paid accounts — on a fresh Ubuntu server
# (22.04 or 24.04). Run as root, from a copy of the repo on that server:
#
#   sudo bash deploy/setup-workspace-server.sh workspace.swangzavenue.com <the gateway server's IP>
#
# The name must already point at this server (or use <this-ip-with-dashes>.sslip.io). Installs Docker,
# Caddy and the Swangz Workspace Agent, writes /etc/swangz-workspace/agent.json the first time (with a
# new random token; edit its "tools" to choose which tools get browsers and how many, then run this
# again), pulls the browser image, writes the Caddy routes and starts the agent. Safe to run again.
# Read deploy/WORKSPACE.md first.
set -euo pipefail

DOMAIN="${1:?usage: setup-workspace-server.sh <domain, e.g. workspace.swangzavenue.com> <gateway IP>}"
GATEWAY_IP="${2:?usage: setup-workspace-server.sh <domain> <IP address of the gateway server>}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
CONF_DIR=/etc/swangz-workspace
CONF="$CONF_DIR/agent.json"
DATA=/var/lib/swangz-workspace
APP=/opt/swangz-workspace
[ "$(id -u)" = 0 ] || { echo "Run it as root: sudo bash $0 $*" >&2; exit 1; }

# read one thing from the agent's config: tools | image | token | ports
conf() {
  python3 - "$CONF" "$1" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    cfg = json.load(f)
what = sys.argv[2]
if what == "tools":
    print(", ".join(f"{tool} {spec['browsers']}" for tool, spec in cfg["tools"].items()))
elif what == "image":
    print(cfg.get("image", "ghcr.io/m1k1o/neko/chromium:latest"))
elif what == "token":
    print(cfg["token"])
elif what == "ports":
    base = cfg.get("webrtc_port_base", 59100)
    print("\n".join(f"      {base + n}" for spec in cfg["tools"].values() for n in spec["browsers"]))
PY
}

echo "== packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 curl gnupg docker.io debian-keyring debian-archive-keyring apt-transport-https >/dev/null
systemctl enable -q --now docker
if ! command -v caddy >/dev/null; then  # Caddy's own package repository (caddyserver.com/docs/install)
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy >/dev/null
fi

echo "== the agent, in $APP"
id swangz-ws >/dev/null 2>&1 || useradd --system --create-home --home-dir "$DATA" --groups docker --shell /usr/sbin/nologin swangz-ws
mkdir -p "$APP" "$CONF_DIR"
install -m 644 "$SRC/workspace_agent/agent.py" "$APP/agent.py"
if [ ! -f "$CONF" ]; then
  PUBLIC_IP="$(curl -fsS https://api.ipify.org || hostname -I | awk '{print $1}')"
  python3 - "$CONF" "$DOMAIN" "$PUBLIC_IP" "$GATEWAY_IP" "$DATA" "$SRC/workspace_agent/agent.example.json" <<'PY'
import json, secrets, sys
conf, domain, ip, gateway_ip, data, example = sys.argv[1:]
with open(example, encoding="utf-8") as f:
    cfg = json.load(f)
cfg.update(token=secrets.token_hex(32), public_url="https://" + domain, public_ip=ip, gateway_ip=gateway_ip, data=data)
with open(conf, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
PY
  echo "   wrote $CONF with a new token — browsers per tool: $(conf tools)"
fi
chown root:swangz-ws "$CONF"
chmod 640 "$CONF"
agent() { sudo -u swangz-ws python3 "$APP/agent.py" "$@" --config "$CONF"; }

echo "== the browser image"
docker pull -q "$(conf image)" >/dev/null
agent check

echo "== Caddy: https://$DOMAIN"
agent caddy > /etc/caddy/Caddyfile
systemctl enable -q caddy
systemctl restart caddy

echo "== the service"
cp "$SRC/deploy/swangz-workspace-agent.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable -q swangz-workspace-agent
systemctl restart swangz-workspace-agent
sleep 2
curl -fsS -H "Authorization: Bearer $(conf token)" http://127.0.0.1:8790/health >/dev/null \
  || { journalctl -u swangz-workspace-agent -n 30 --no-pager; exit 1; }

echo
echo "The workspace agent is running. Next:"
echo "  - open each browser's WebRTC port, UDP and TCP, in any firewall in front of this server:"
conf ports
echo "  - on the gateway server, add to /opt/swangz-gateway/.env and restart it (systemctl restart swangz-gateway):"
echo "      GATEWAY_WORKSPACE_AGENT=https://$DOMAIN/agent"
echo "      GATEWAY_WORKSPACE_AGENT_TOKEN=<the \"token\" in $CONF>"
echo "  - then in the console: the tool -> Settings -> Company browsers -> From the workspace server,"
echo "    and Who can use it -> sign each browser in to the tool, once"
echo "  - logs: journalctl -u swangz-workspace-agent -f"
