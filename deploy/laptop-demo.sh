#!/usr/bin/env bash
# Run the Swangz AI Gateway on this laptop and put it online through a free https tunnel.
#   bash deploy/laptop-demo.sh            # real providers: keys come from the .env you point it at
#   DEMO_MODEL=1 bash deploy/laptop-demo.sh   # no provider keys needed: a stand-in model answers
# The link changes whenever the free tunnel reconnects; the gateway follows it automatically.
set -u
cd "$(dirname "$0")/.."
ENV_FILE="${GATEWAY_ENV_FILE:-$HOME/swangz-gateway-demo/.env}"
PORT=$(grep -E '^GATEWAY_PORT=' "$ENV_FILE" | cut -d= -f2); PORT=${PORT:-8787}
LOGS="$(dirname "$ENV_FILE")"
pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null; }
trap cleanup EXIT INT TERM

if [ "${DEMO_MODEL:-0}" = "1" ]; then
  python3 tests/fake_upstream.py 18902 --demo >"$LOGS/demo-model.log" 2>&1 & pids+=($!)
fi
GATEWAY_ENV_FILE="$ENV_FILE" python3 -m gateway serve >"$LOGS/gateway.log" 2>&1 & pids+=($!)
sleep 1
echo "Gateway running on port $PORT. Opening the tunnel…"
while true; do
  ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
      -R 80:localhost:"$PORT" nokey@localhost.run 2>&1 | while read -r line; do
    url=$(grep -oE 'https://[a-z0-9.-]+\.(lhr\.life|localhost\.run)' <<<"$line" | tail -1)
    if [ -n "$url" ]; then
      echo
      echo "  Staff app:     $url/"
      echo "  Control room:  $url/admin"
      echo
    fi
  done
  echo "Tunnel dropped — reconnecting in 5 seconds (the link will change)…"
  sleep 5
done
