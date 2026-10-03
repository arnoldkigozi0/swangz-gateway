# The shared workspace — a company browser on your own server

For tools where Swangz has **one account** and no per-person plan, you can run a browser on the
company's own server, sign it in to that tool **once**, and have the portal send whoever holds the
turn straight into it. They arrive already signed in, and the password never leaves the server.

This is a real, mainstream category: it is called **remote browser isolation**, or a hosted browser
workspace. It is what Island and Cloudflare Browser Isolation sell, and what Kasm Workspaces,
Apache Guacamole and Neko do as open source you can host yourself.

```
staff browser → Swangz AI (checks the turn, logs it) → the workspace on your server → the tool
```

## Read this before you build it

**It does not make account sharing allowed.** ChatGPT, Midjourney, Canva and most others forbid one
subscription being used by several people, whatever screen those people are looking at. A remote
browser changes *where* the session lives, not *how many people* are on the account. If a vendor
notices, they can suspend the account. Where a tool sells a Team or Business plan, **buy seats
instead** — it is cheaper than losing the account, and nobody has to queue.

**What it does fix,** and these are real:
- staff never see or hold the shared password;
- one person at a time, enforced, with a log of who and when;
- the session lives on the server, so nothing is left signed in on anyone's laptop.

**What it costs, honestly:**
- **RAM.** A running browser needs roughly 1–2 GB. The $5 VPS that runs the gateway cannot also run
  browsers. Budget a separate 4–8 GB machine, about **$12–30/month**, for two or three people at once.
- **Speed.** You are streaming a desktop. From a European or American server to Kampala over a MiFi
  it will feel slower than using the tool directly — fine for prompting and reviewing, painful for
  dragging things around in Canva. Pick the nearest region you can.
- **Bot checks.** Some AI sites challenge sign-ins from datacentre addresses. Expect to answer a
  verification the first time, and occasionally again.

**My advice:** use the workspace only for the tools that have no team plan. For everything else, seats
or SSO. And keep turns switched on either way — that is what gives you the attribution.

## Setting it up

1. **A machine for it.** 4 GB RAM minimum, nearest region to Kampala you can get. Separate from the
   gateway's machine.
2. **Install a workspace server.** [Kasm Workspaces](https://kasmweb.com/docs) fits best: it runs each
   browser in its own container, has its own user accounts, and can keep a persistent profile so a
   tool stays signed in between sessions. `curl -O https://kasm-static-content.s3.amazonaws.com/kasm_release_*.tar.gz`
   and follow their install guide. Neko is lighter if you only need one shared browser.
3. **Give it a name and a certificate.** Point `workspace.swangzavenue.com` at the machine and put
   Caddy in front of it, the same way `deploy/Caddyfile` does for the gateway.
4. **Sign in, once, by hand.** Open the workspace yourself as an admin, go to the tool, sign in with
   the Swangz subscription account, and let the profile persist. Nobody else ever types that password.
5. **Lock it down.** The workspace must not be open to the internet — put it behind its own login, and
   allow only the gateway's address and your own if you can. Anyone who reaches it reaches the account.
6. **Point the tool at it.** In the control room: **Tools → the tool → Settings**, set *How people sign
   in* to **Shared company account**, then paste the workspace address into **Shared workspace
   address**. Set *People at a time* (usually 1) and how long a turn lasts.

From then on, **Open** in the staff app checks the turn, writes the launch to the log, and sends that
one person to the workspace. Everyone else is told who has it and until when.

## Checking it works

- Open the tool from the staff app as a normal staff member → you land in the workspace, signed in.
- Have a second person press Open → they are told who holds it.
- Hand it back in the staff app → the second person can take it.
- Control room → **Live** shows who is on a shared account; **Staff activity → Tools opened** has the
  history; **Licences & spend** shows whether the seat is worth keeping.
