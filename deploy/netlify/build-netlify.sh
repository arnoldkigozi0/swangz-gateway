#!/usr/bin/env bash
# Assemble the static staff + admin front-ends into dist/ for Netlify, pointed at the gateway API.
#
# Set the gateway's public address as SWANGZ_GATEWAY (a Netlify environment variable, or inline):
#   SWANGZ_GATEWAY=https://ai.swangz.com bash build-netlify.sh
#
# Then, on the gateway host, allow this Netlify site's origin:
#   GATEWAY_CORS_ORIGINS=https://swangz-ai.netlify.app
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

rm -rf "$DIST"
mkdir -p "$DIST/static"
# assets keep their /static/ path (that's how the pages reference them)
cp -r "$STATIC/." "$DIST/static/"
# the two page shells sit at the site root
mv "$DIST/static/index.html" "$DIST/index.html"
mv "$DIST/static/admin.html" "$DIST/admin.html"

# config.js tells the pages where the gateway API is; it loads before the app scripts
printf 'window.SWANGZ_GATEWAY = "%s";\n' "$GATEWAY" > "$DIST/config.js"
sed -i 's#<script src="/static/portal.js"></script>#<script src="/config.js"></script>\n  <script src="/static/portal.js"></script>#' "$DIST/index.html"
sed -i 's#<script src="/static/admin.js"></script>#<script src="/config.js"></script>\n  <script src="/static/admin.js"></script>#' "$DIST/admin.html"

cp "$HERE/netlify.toml" "$DIST/../netlify.toml" 2>/dev/null || true
echo "Built $DIST  →  gateway $GATEWAY"
echo "Next: set GATEWAY_CORS_ORIGINS on the gateway to this Netlify site's URL."
