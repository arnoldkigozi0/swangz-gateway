#!/usr/bin/env bash
# Assemble the staff app + admin console into dist/ for Netlify.
#
# Default — the "front door": Netlify serves the pages and passes /api, /admin/api, /auth, /go and
# /icons straight through to the gateway, so the browser only ever talks to the Netlify address.
# Cookies stay first-party (works on iPhone Safari too), and Google sign-in gets one fixed return
# address. Set the gateway's address as SWANGZ_GATEWAY (a Netlify environment variable, or inline):
#
#   SWANGZ_GATEWAY=https://ai.swangz.com bash build-netlify.sh
#
# Then on the gateway: GATEWAY_WEB_URL=https://<your-site>.netlify.app (see deploy/NETLIFY.md).
#
# SWANGZ_CROSS_ORIGIN=1 instead builds pages that call the gateway directly across origins (needs
# GATEWAY_CORS_ORIGINS on the gateway; password sign-in only).
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
STATIC="$REPO/gateway/static"
DIST="${1:-$HERE/dist}"
GATEWAY="${SWANGZ_GATEWAY:-}"

if [ -z "$GATEWAY" ]; then
  echo "Set SWANGZ_GATEWAY to the gateway's address, e.g. https://ai.swangz.com" >&2
  exit 1
fi
GATEWAY="${GATEWAY%/}"
case "$GATEWAY" in https://*) ;; *) echo "SWANGZ_GATEWAY must start with https://" >&2; exit 1 ;; esac

rm -rf "$DIST"
mkdir -p "$DIST/static"
# assets keep their /static/ path (that's how the pages reference them)
cp -r "$STATIC/." "$DIST/static/"
# the two page shells sit at the site root
mv "$DIST/static/index.html" "$DIST/index.html"
mv "$DIST/static/admin.html" "$DIST/admin.html"

if [ "${SWANGZ_CROSS_ORIGIN:-0}" = "1" ]; then
  API=""            # the pages call the gateway directly
  PAGES_GATEWAY="$GATEWAY"
  CONNECT="'self' $GATEWAY"
else
  API="$GATEWAY"    # Netlify proxies to it; the pages stay same-origin
  PAGES_GATEWAY=""
  CONNECT="'self'"
fi

# config.js tells the pages where the gateway API is ("" = this same site); it loads before the apps
printf 'window.SWANGZ_GATEWAY = "%s";\n' "$PAGES_GATEWAY" > "$DIST/config.js"
sed -i 's#<script src="/static/portal.js"></script>#<script src="/config.js"></script>\n  <script src="/static/portal.js"></script>#' "$DIST/index.html"
sed -i 's#<script src="/static/admin.js"></script>#<script src="/config.js"></script>\n  <script src="/static/admin.js"></script>#' "$DIST/admin.html"

# Routing. First match wins: the gateway paths, then the two single-page apps.
{
  if [ -n "$API" ]; then
    for p in /api /admin/api /auth /go /icons; do
      printf '%-14s %s%s/:splat  200!\n' "$p/*" "$API" "$p"
    done
    printf '%-14s %s/healthz  200!\n' "/healthz" "$API"
  fi
  printf '%-14s /admin.html  200\n' "/admin"
  printf '%-14s /admin.html  200\n' "/admin/*"
  printf '%-14s /index.html  200\n' "/*"
} > "$DIST/_redirects"

# The same protections the gateway gives its own pages
cat > "$DIST/_headers" <<EOF
/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer
  X-Frame-Options: DENY
  Content-Security-Policy: default-src 'self'; img-src 'self' data: https:; media-src 'self' https: blob:; style-src 'self'; script-src 'self'; font-src 'self'; connect-src $CONNECT; frame-ancestors 'none'; base-uri 'none'; form-action 'self'
EOF

echo "Built $DIST  →  gateway $GATEWAY  ($([ -n "$API" ] && echo 'front door: Netlify proxies to it' || echo 'cross-origin'))"
if [ -n "$API" ]; then
  echo "Next: on the gateway set GATEWAY_WEB_URL to this Netlify site's address, and restart it."
else
  echo "Next: on the gateway set GATEWAY_CORS_ORIGINS to this Netlify site's address, and restart it."
fi
