# Automatic laptop hosting

`laptop-service.py` supervises the gateway, Cloudflare quick tunnel and (only when the existing demo
configuration enables it) the stand-in provider. It uses the existing `~/swangz-gateway-demo/.env`,
database and provider definitions; it does not create accounts or call real provider models.

The public staff address remains **https://swangz-ai.netlify.app**. When the quick-tunnel address
changes, the service updates `SWANGZ_GATEWAY` for all Netlify contexts, starts a build and verifies
Netlify's `/healthz`. It resumes pending deployment checks after a service restart. Healthy unchanged
addresses do not trigger another build. Failed syncs retry after two minutes. A missing/expired Netlify
login is reported in the journal; local service continues running.

Credentials come from `NETLIFY_AUTH_TOKEN` in the existing environment, or the active Netlify CLI
login at `~/.config/netlify/config.json`. Neither credentials nor provider error bodies are printed or
stored in deployment state. State files use mode 0600; the unit creates logs/files with umask 0077.

## Install on this Linux PC

After reviewing `deploy/swangz-laptop.service` and adjusting the repository path if needed:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/swangz-laptop.service ~/.config/systemd/user/
loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now swangz-laptop.service
```

Stop any manually started `deploy/laptop-demo.sh` before starting the service so only one gateway
owns the configured port. The user service starts at boot (lingering), stays running after logout,
and survives closing a terminal or this chat. During sleep the PC cannot serve requests; Cloudflare
reconnects when its network returns. Exited children are restarted within about five seconds. The
health watchdog restarts a stuck gateway after three failed checks, and recreates a persistently
broken tunnel only when outbound internet is available. Netlify repairs may take a few minutes after
a changed tunnel address while its deployment completes.

```bash
systemctl --user status swangz-laptop.service
journalctl --user -u swangz-laptop.service -n 30 --no-pager
systemctl --user restart swangz-laptop.service  # after changing .env or Python server code
systemctl --user disable --now swangz-laptop.service  # stop automatic hosting
cat ~/swangz-gateway-demo/tunnel-url.txt
```

The child logs are in `~/swangz-gateway-demo/logs/{gateway,model,tunnel}.log`; the current tunnel is
saved in `tunnel-url.txt`, and pending/verified Netlify state is in `netlify-sync.json`. Logs are replaced
when that child restarts. The SQLite database remains in its existing configured data directory.

To repair the front door for a manually running tunnel without starting services:

```bash
python3 deploy/laptop-service.py --sync https://your-current-link.trycloudflare.com
```

## Permanent availability

Automatic laptop hosting keeps the Netlify address stable but cannot serve while the laptop is
asleep, switched off or offline. True continuous availability requires an always-on gateway host with
a persistent database. A named Cloudflare Tunnel additionally requires a Cloudflare account and a
domain on Cloudflare; it offers a fixed origin hostname instead of a temporary quick-tunnel hostname.
See Cloudflare's [setup guide](https://developers.cloudflare.com/tunnel/get-started/) and the existing
`GO-LIVE.md`, `setup-gateway-server.sh` and `WORKSPACE.md` deployment guides. Do not move or duplicate
the active database onto another host without planning the cutover.

## Verification

The recovery tests mock Netlify: crashed-child recovery, URL selection, all-context environment updates, build ordering,
pending-deployment resumption, failed-build retry, health validation and duplicate-build avoidance.
The installed service is separately checked against the real gateway and Netlify front door.
