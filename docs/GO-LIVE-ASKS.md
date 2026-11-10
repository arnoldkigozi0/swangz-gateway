# Go-live: what only Arnold can provide

The code can be made ready without these, but the Hub cannot go live until each one exists. Nothing here has been bought, created or changed by the team. Values go into the server's environment file, never into Git or chat.

| # | What | Why it is needed | Where it goes |
|---|---|---|---|
| 1 | **A server (VPS) and its login** | The laptop only serves while it is awake and online. | `deploy/setup-gateway-server.sh` on that server |
| 2 | **A domain name and a DNS record** pointing at the server (for example `ai.swangzavenue.com`) | People need one permanent https address; Google sign-in needs a fixed one. | `GATEWAY_WEB_URL` and `GATEWAY_PUBLIC_URL` |
| 3 | **A Google OAuth web client** in the Swangz Google Cloud project, with the return address the check prints (`https://<domain>/auth/google/callback`) | "Continue with Google" for staff and admins. | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| 4 | **Provider API keys**, only for tools that run through the gateway (Anthropic, OpenAI, ElevenLabs, Higgsfield) | API and developer tools cannot answer without them. Website tools do not need a key. | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `HIGGSFIELD_CREDENTIALS` |
| 5 | **Vendor subscriptions and seats**: which plans Swangz pays for, how many seats, and who holds each | A tool opens only when its subscription is active and the person is assigned. | Entered in the console (Tools, People); no passwords are stored |
| 6 | **Code-signing certificates**: a Windows publisher certificate and an Apple Developer ID with notarization | Unsigned installers show a warning, and desktop auto-update stays off until builds are signed. | `packaging/README.md` |
| 7 | **Backup destination** (optional): a second machine or storage account for off-server copies | A backup on the same server is lost with the server. | `GATEWAY_BACKUP_REMOTE` |
| 8 | **Email sending account** (optional): SMTP host, user and password | Emails for high and critical notifications; without it they stay in-app. | `GATEWAY_SMTP_*`, `GATEWAY_NOTIFY_TO` |
| 9 | **Two real phones for an hour**: one Android, one iPhone | The installable staff app must be tried on real devices before release. | `docs/MOBILE-READINESS.md` |

Decisions only Arnold makes: the go-live date and cutover window, who the first owners are, and approval of each purchase above (prices need current vendor quotations).

Once items 1 to 3 exist, run `python3 -m gateway preflight` against the server's environment file (see `docs/HUB-DELIVERY.md`); it says exactly what is still missing without contacting anything.
