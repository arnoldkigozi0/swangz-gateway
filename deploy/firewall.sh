# Sourced by the setup scripts: a host firewall that only opens what the server serves.
#   open_firewall "80/tcp" "443/tcp" "443/udp" ...
# SSH stays open on whatever port(s) sshd actually listens on, so enabling it cannot lock you out.
# Skip it with SKIP_FIREWALL=1 (e.g. when the provider's own firewall is used instead).
open_firewall() {
  if [ "${SKIP_FIREWALL:-0}" = 1 ]; then
    echo "   SKIP_FIREWALL=1: leaving the host firewall alone — make sure the provider's firewall allows only: SSH $*"
    return 0
  fi
  apt-get install -y -qq ufw >/dev/null
  local ssh_ports
  ssh_ports="$( (sshd -T 2>/dev/null || true) | awk '$1 == "port" {print $2}' | sort -u)"
  [ -n "$ssh_ports" ] || ssh_ports=22
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  for port in $ssh_ports; do ufw allow "$port/tcp" comment 'ssh' >/dev/null; done
  for rule in "$@"; do ufw allow "$rule" >/dev/null; done
  ufw --force enable >/dev/null
  echo "   firewall on: SSH ($(echo $ssh_ports | tr '\n' ' ')) and $*"
}
