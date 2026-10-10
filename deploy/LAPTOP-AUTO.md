# Automatic laptop hosting

`laptop-service.py` supervises Swangz AI Hub, its direct Cloudflare quick tunnel and the stand-in provider only when the existing demo configuration enables it. It uses the existing `~/swangz-gateway-demo/.env`, database and provider definitions; it does not create accounts or call live models to check health.

The direct tunnel serves both staff `/` and admin `/admin`. Read its current HTTPS address from `~/swangz-gateway-demo/tunnel-url.txt`. Neither Netlify credits nor a Netlify login is required. A quick-tunnel address can change after reconnection. Existing Google callback registrations and `GATEWAY_WEB_URL` remain configured until a verified first-party hostname is deliberately selected; password sign-in uses the direct host.

## Install on this Linux PC

Review `deploy/swangz-laptop.service` and adjust the repository path if needed:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/swangz-laptop.service ~/.config/systemd/user/
loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now swangz-laptop.service
```

Stop any manually started `deploy/laptop-demo.sh` before starting the service so only one gateway owns the configured port. The service starts at boot with lingering, remains running after logout, and survives closing a terminal. During sleep the PC cannot serve requests; Cloudflare reconnects when its network returns. Exited children restart within about five seconds. The health watchdog restarts a stuck gateway after three failed checks and reconnects a persistently broken tunnel only when outbound internet is available.

```bash
systemctl --user status swangz-laptop.service
journalctl --user -u swangz-laptop.service -n 30 --no-pager
systemctl --user restart swangz-laptop.service
cat ~/swangz-gateway-demo/tunnel-url.txt
```

Child logs are in `~/swangz-gateway-demo/logs/{gateway,model,tunnel}.log` and are replaced when that child restarts. The database stays in its existing configured data directory. Follow [Hub delivery](../docs/HUB-DELIVERY.md) before any schema upgrade: verified SQLite backup, scratch rehearsal, approved code, stopped writes, additive migration/backfill, preservation checks and recovery procedure.

## Optional legacy Netlify front door

Automatic synchronisation is disabled by default. `GATEWAY_NETLIFY_SYNC=1` explicitly enables the historical proxy/build integration. It updates `SWANGZ_GATEWAY`, resumes pending deployment checks and verifies Netlify health; a failed build never becomes a successful delivery claim. Legacy failures leave direct Hub hosting running.

If opted in, credentials come from the existing environment or active Netlify CLI login and never enter logs or deployment state. State files use mode 0600 and the installed unit uses umask 0077. The explicit maintenance command remains available:

```bash
python3 deploy/laptop-service.py --sync https://your-current-link.trycloudflare.com
```

## Permanent availability

Automatic recovery cannot serve requests while the PC is asleep, switched off or disconnected. Use the existing Caddy/systemd VPS architecture and a configured first-party hostname for continuous availability. Do not change DNS or OAuth callbacks until the actual deployment settings are verified. Do not duplicate the active database across two writable hosts. [Hub delivery](../docs/HUB-DELIVERY.md) contains cutover, backup and recovery steps; Railway configuration is isolated optional staging.

## Verification

Eight laptop-service regressions cover child recovery, URL publication, opt-in Netlify scheduling, legacy sync ordering, failed/pending deployments, health validation and duplicate-build avoidance. Actual service/tunnel checks and activation status are recorded separately in [Hub completion](../docs/HUB-COMPLETION.md).
