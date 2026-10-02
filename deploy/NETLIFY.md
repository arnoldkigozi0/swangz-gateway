# Hosting the staff app and admin console on Netlify

Netlify can host the **web pages** (staff app and admin console) — they're static files, so they get
Netlify's CDN, a custom domain, and no dependence on the laptop for the interface.

What Netlify **cannot** host is the gateway itself: it's a long-running server that proxies and
streams AI requests, holds the SQLite database, powers the kill switch, and keeps rate-limit state.
Netlify has no persistent process or database. So the split is:

- **Netlify** → the staff app (`/`) and admin console (`/admin`), static.
- **An always-on host** → the gateway API. A small VPS (`ai.swangz.com`) for real use; the laptop
  demo tunnel works for a demo.
- The browser extension already points straight at the gateway, so it's unaffected.

The pages talk to the gateway cross-origin, which needs two matching settings: the pages must know the
gateway's address, and the gateway must allow the Netlify site's origin.

## Steps

1. **Pick the gateway address.** It must be reachable over **https** (Netlify pages are https, and the
   session cookie is `Secure`). For production that's your VPS behind Caddy (`deploy/Caddyfile`); for a
   demo it's the Cloudflare tunnel URL the laptop script prints.

2. **On the gateway**, allow the Netlify origin and trust the proxy headers:

   ```
   GATEWAY_CORS_ORIGINS=https://swangz-ai.netlify.app     # your Netlify site (or custom domain)
   GATEWAY_PUBLIC_URL=https://ai.swangz.com               # the gateway's own address
   GATEWAY_TRUST_PROXY=1
   ```

   Restart the gateway. (Multiple origins are comma-separated, e.g. a `*.netlify.app` preview URL and
   the final custom domain.)

3. **Deploy the pages to Netlify.** Point Netlify at this repo with:

   - **Base directory:** `deploy/netlify`
   - **Build command:** `bash build-netlify.sh`
   - **Publish directory:** `deploy/netlify/dist`
   - **Environment variable:** `SWANGZ_GATEWAY=https://ai.swangz.com`

   The build copies the front-ends, writes a `config.js` pointing them at the gateway, and keeps the
   assets under `/static/`. `netlify.toml` (in `deploy/netlify`) handles the hash-routed deep links.

   Or build locally and drag the folder into Netlify:

   ```bash
   SWANGZ_GATEWAY=https://ai.swangz.com bash deploy/netlify/build-netlify.sh
   # then upload deploy/netlify/dist/
   ```

4. **Check it.** Open the Netlify URL, sign in as a staff member (their email + the password they set
   from the invite link). The admin console is at `<netlify-url>/admin`.

## Notes

- **Keep the admin console private.** It's served at `/admin` of the same Netlify site. If you'd rather
  it not share a URL with staff, deploy a second Netlify site from the same build and only hand staff
  the first URL — both still talk to the one gateway.
- **The gateway can also keep serving the pages itself** (at its own address). Hosting them on Netlify
  is optional; the two aren't mutually exclusive.
- **Custom domains:** set the Netlify domain (e.g. `ai.swangz.com` for the pages) and a separate
  gateway domain (e.g. `api.swangz.com`). Put both the pages' domain in `GATEWAY_CORS_ORIGINS` and the
  gateway's domain in `GATEWAY_PUBLIC_URL` and `SWANGZ_GATEWAY`.
