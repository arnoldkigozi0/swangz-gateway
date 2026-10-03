# Netlify front door + Sign in with Google

Netlify hosts the **pages** (staff app at `/`, admin console at `/admin`) on a fixed address such as
`https://swangz-ai.netlify.app`, and passes the gateway's paths (`/api`, `/admin/api`, `/auth`, `/go`,
`/icons`) straight through to the gateway. The browser only ever talks to the Netlify address, so:

- the link never changes, even when the laptop tunnel does;
- sign-in cookies are first-party (works on iPhone Safari too);
- Google gets one fixed return address.

Netlify **cannot** run the gateway itself (it streams AI calls, holds the database and the kill
switch). The gateway stays on the laptop (demo) or a small server (`ai.swangz.com`, real use).
Coding tools (Claude Code, Codex) and the browser extension keep talking to the gateway directly —
Netlify's proxy cuts requests off after 26 seconds, which is fine for the web apps but not for long
AI streams.

## Part 1 — Netlify

1. Log in at <https://app.netlify.com> → **Add new project** → **Import an existing project** →
   **GitHub** → allow access to `arnoldkigozi0/swangz-gateway` (a private repo is fine).
2. Build settings:
   - **Base directory:** `deploy/netlify`
   - **Build command:** `bash build-netlify.sh`
   - **Publish directory:** `deploy/netlify/dist`
3. **Environment variables** → add `SWANGZ_GATEWAY` = the gateway's https address
   (the laptop demo's tunnel link, e.g. `https://floral-britney-velvet-coming.trycloudflare.com`).
4. **Deploy.** Then **Project configuration → Change project name** to something like `swangz-ai`, so
   the address is `https://swangz-ai.netlify.app`. (A custom domain works the same way.)

**When the gateway address changes** (the laptop tunnel restarts): Netlify → Project configuration →
Environment variables → edit `SWANGZ_GATEWAY` → **Deploys → Trigger deploy → Deploy project**.

No GitHub? Build on the laptop and drag the folder in instead:
`SWANGZ_GATEWAY=https://<gateway> bash deploy/netlify/build-netlify.sh`, then drag
`deploy/netlify/dist` onto the project's **Deploys** page.

## Part 2 — Google

1. <https://console.cloud.google.com> → project picker → **New project** → name it `Swangz AI` → Create.
2. Menu → **APIs & Services → OAuth consent screen** (shown as **Google Auth Platform**) → **Get started**:
   - App name `Swangz AI`, support email your Gmail → **Audience: External** → contact email → Create.
   - **Audience** → **Publish app** (only email/profile are asked for, so Google needs no review).
     Or leave it in Testing and add each person's Gmail under **Test users**.
3. **Clients → Create client** → type **Web application**, name `Swangz AI`:
   - **Authorized redirect URIs** → add `https://swangz-ai.netlify.app/auth/google/callback`
     (your exact Netlify address + `/auth/google/callback`).
   - Create → copy the **Client ID** and **Client secret**.

## Part 3 — the gateway (laptop)

Add three lines to `~/swangz-gateway-demo/.env`, then restart the gateway:

```
GATEWAY_WEB_URL=https://swangz-ai.netlify.app
GOOGLE_CLIENT_ID=<the client id>
GOOGLE_CLIENT_SECRET=<the client secret>
```

`GATEWAY_WEB_URL` is the address people open; sign-in links and Google's return address use it.

## Who can sign in with Google

- **Staff:** anyone with a person record whose email is their Google address — a `@swangzavenue.com`
  address, or one of the named exceptions. Suspended people and ended accounts are refused.
- **Admins:** a console user whose **username is their Google email** (Settings → Console users).
- Email + password sign-in keeps working alongside Google.

## Check it

Open `https://swangz-ai.netlify.app` → **Continue with Google** → you land in the staff app.
Open `https://swangz-ai.netlify.app/admin` → **Continue with Google** → the console.
If Google says `redirect_uri_mismatch`, the address in Part 2 step 3 doesn't exactly match
`GATEWAY_WEB_URL` + `/auth/google/callback`.

## The other mode (cross-origin)

`SWANGZ_CROSS_ORIGIN=1` builds pages that call the gateway directly instead of through Netlify. The
gateway then needs `GATEWAY_CORS_ORIGINS=https://<netlify-site>`. Password sign-in only, and Safari's
cross-site cookie blocking can break it — prefer the front door.
