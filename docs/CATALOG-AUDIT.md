# Catalog audit: 49 built-in tools against the final directive

Audited: 2026-11-20, main `046f6e5`. Auditor: Probe. Read-only: no code, row or grant was changed, no provider was
contacted and nothing was signed in to. Source of every cell is `gateway/catalog.py` plus the rows a **fresh database**
holds after `catalog.seed()` and `catalog.refine()` (run in a scratch directory; production data was not read).

Verdicts: **PASS** = the file shows it. **FAIL** = the file shows it is missing or wrong. **NOT TESTED** = the file cannot
tell and no provider documentation was opened for it. No deep link is proposed here: a URL is only a defect when the file
itself shows it is a marketing, pricing or product page, and the replacement is a task for someone who can read the
provider's own documentation.

## Summary

| Directive item | PASS | FAIL | NOT TESTED | What the file has |
|---|---|---|---|---|
| Official app URL, not marketing/pricing | 3 | 14 | 32 | `tools.url` only; `launch_url` is `''` for all 49 on a fresh database, so Open falls back to `url` (`launch_target()`) |
| Mode (web / native / CLI / API) | 0 | 49 | 0 | No field. Only `kind` (api / dev / site) exists, which is a billing route, not a mode |
| Approved OAuth hosts | 0 | 44 | 5 | `SIGNIN_HOSTS` in code for 3 tools (`chatgpt`, `claude`, `gemini`); not a column, built-ins only, not admin-editable, marked "to be confirmed" |
| Last-verified date | 0 | 49 | 0 | No field anywhere in `tools` or in the seed |
| Enable / disable | 49 | 0 | 0 | `tools.archived` + `POST /tools/<id>/archive|restore`; covered by tests (below) |

"NOT TESTED" for OAuth: `claude-code` and `codex` (command-line agents on the company key, probably none needed) plus the three
tools that have a list that nobody has confirmed.

## Other defects found while reading the rows (each reproduced on a fresh database)

1. **Two tools share a gate host, so one of them can never be recognised.** `host_index()` keeps one row per host and the
   later row wins. `sora.com` is on both `chatgpt` and `sora` (resolves to `sora`), `adobe.com` is on both `photoshop` and
   `adobe-premiere` (resolves to `adobe-premiere`, so a Photoshop visit is gated and logged as Premiere), and `higgsfield.ai`
   is on both `higgsfield-ai` and `seedance` (resolves to `seedance`, so the API tool's website is logged as Seedance).
2. **`github.com/copilot` is not a hostname.** `match_host()` compares hostnames only, so the second Copilot host never
   matches (`match_host(index, "github.com")` returns nothing). Only `copilot.microsoft.com` is gated.
3. **`openai.com` governs the whole OpenAI domain for DALL-E.** `platform.openai.com`, `auth.openai.com` and the rest of
   `*.openai.com` resolve to `dall-e`. `tests/test_device_open.py:169` pins this on purpose ("as before: openai.com is DALL-E"),
   so it is a known trade-off, but it conflicts with a per-tool OAuth host list: the sign-in host `auth.openai.com` belongs to
   `chatgpt` in `SIGNIN_HOSTS` and to `dall-e` in the gate.
4. **`claude-code` and `codex` are `signin = 'seat'` on a freshly built database.** The v6 migration sets `api` for
   `kind = 'dev'`, but it runs before the seed inserts those rows, so only a database that already held them was fixed.
   `registry.py` refuses `api` and `shared` tools, so the two rows behave differently on a new install than on the live one.
   Whether the live database is affected is **NOT TESTED** (it may not be read).
5. **`url == pricing_url`** for `davinci-resolve` and `topaz-video-ai`: the "tool address" is a product/pricing page. Both are
   desktop applications, so there is no web app to open; this is the same gap as the missing Mode field.
6. **`runway`'s gate lists `runwayml.com` and `app.runwayml.com` but its `pricing_url` is on `runway.com`**, a host the gate does
   not govern. Which domain is current is NOT TESTED.

## Per tool

| # | Tool | kind | Launch URL (`url`; `launch_url` is empty on all 49) | Mode | OAuth hosts | Last verified | Enable/disable | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | `chatgpt` | api | **PASS**: `https://chatgpt.com/` is the product's own app host | **FAIL** (no field; kind `api`) | **NOT TESTED**: auth.openai.com, accounts.google.com (in `SIGNIN_HOSTS`; code comment says "to be confirmed", no source or date) | **FAIL** (no field) | **PASS** (`archived`) | host `sora.com` is also on `sora` |
| 2 | `claude` | api | **PASS**: `https://claude.ai/` is the product's own app host | **FAIL** (no field; kind `api`) | **NOT TESTED**: accounts.google.com (in `SIGNIN_HOSTS`; code comment says "to be confirmed", no source or date) | **FAIL** (no field) | **PASS** (`archived`) |  |
| 3 | `higgsfield-ai` | api | **NOT TESTED**: `https://higgsfield.ai/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `api`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) | host `higgsfield.ai` is also on `seedance` |
| 4 | `elevenlabs` | api | **NOT TESTED**: `https://elevenlabs.io/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `api`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 5 | `claude-code` | dev | **FAIL**: `https://claude.com/claude-code` is a product page; the tool is a command-line agent, the row has no app/install target | **FAIL** (no field; kind `dev`) | **NOT TESTED**: none listed; CLI/API on the company key, so likely none needed | **FAIL** (no field) | **PASS** (`archived`) | `signin` is `seat` on a freshly built database (the v6 `UPDATE ... kind=dev` runs before the seed) |
| 6 | `codex` | dev | **FAIL**: `https://openai.com/codex` is a product page; the tool is a command-line agent, the row has no app/install target | **FAIL** (no field; kind `dev`) | **NOT TESTED**: none listed; CLI/API on the company key, so likely none needed | **FAIL** (no field) | **PASS** (`archived`) | `signin` is `seat` on a freshly built database (the v6 `UPDATE ... kind=dev` runs before the seed) |
| 7 | `social-insider` | site | **NOT TESTED**: `https://www.socialinsider.io/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 8 | `gemini` | site | **PASS**: `https://gemini.google.com/` is the product's own app host | **FAIL** (no field; kind `site`) | **NOT TESTED**: accounts.google.com (in `SIGNIN_HOSTS`; code comment says "to be confirmed", no source or date) | **FAIL** (no field) | **PASS** (`archived`) |  |
| 9 | `make` | site | **NOT TESTED**: `https://www.make.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 10 | `zapier` | site | **NOT TESTED**: `https://zapier.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 11 | `n8n` | site | **NOT TESTED**: `https://n8n.io/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 12 | `heygen` | site | **NOT TESTED**: `https://www.heygen.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 13 | `synthesia` | site | **NOT TESTED**: `https://www.synthesia.io/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 14 | `copilot` | site | **NOT TESTED**: `https://copilot.microsoft.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) | host `github.com/copilot` can never match (the gate compares hostnames only) |
| 15 | `cursor` | site | **NOT TESTED**: `https://www.cursor.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 16 | `canva` | site | **NOT TESTED**: `https://www.canva.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 17 | `figma-ai` | site | **FAIL**: `https://www.figma.com/ai/` has a product/marketing path, not an app entry | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 18 | `photoshop` | site | **FAIL**: `https://www.adobe.com/products/photoshop.html` has a product/marketing path, not an app entry | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) | host `adobe.com` is also on `adobe-premiere` |
| 19 | `adobe-firefly` | site | **NOT TESTED**: `https://firefly.adobe.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 20 | `dall-e` | site | **FAIL**: `https://openai.com/dall-e-3` has a product/marketing path, not an app entry | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) | host `openai.com` governs every `*.openai.com` page not claimed by `chat.openai.com` |
| 21 | `ideogram` | site | **NOT TESTED**: `https://ideogram.ai/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 22 | `krea` | site | **NOT TESTED**: `https://www.krea.ai/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 23 | `magnific` | site | **NOT TESTED**: `https://magnific.ai/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 24 | `midjourney` | site | **NOT TESTED**: `https://www.midjourney.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 25 | `stable-diffusion` | site | **NOT TESTED**: `https://stability.ai/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 26 | `suno` | site | **NOT TESTED**: `https://suno.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 27 | `udio` | site | **NOT TESTED**: `https://www.udio.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 28 | `heyeddie` | site | **NOT TESTED**: `https://heyeddie.ai/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 29 | `airtable-ai` | site | **FAIL**: `https://www.airtable.com/platform/ai` has a product/marketing path, not an app entry | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 30 | `loom-ai` | site | **FAIL**: `https://www.loom.com/ai` has a product/marketing path, not an app entry | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 31 | `notion-ai` | site | **FAIL**: `https://www.notion.so/product/ai` has a product/marketing path, not an app entry | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 32 | `otter-ai` | site | **NOT TESTED**: `https://otter.ai/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 33 | `perplexity` | site | **NOT TESTED**: `https://www.perplexity.ai/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 34 | `kling-ai` | site | **NOT TESTED**: `https://kling.kuaishou.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 35 | `luma-dream-machine` | site | **FAIL**: `https://lumalabs.ai/dream-machine` has a product/marketing path, not an app entry | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 36 | `pika-labs` | site | **NOT TESTED**: `https://pika.art/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 37 | `runway` | site | **FAIL**: `url` is the root `runwayml.com`, while `hosts` names `app.runwayml.com` as the app host | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 38 | `seedance` | site | **FAIL**: `https://higgsfield.ai/seedance` has a product/marketing path, not an app entry | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) | host `higgsfield.ai` is also on `higgsfield-ai` |
| 39 | `sora` | site | **NOT TESTED**: `https://sora.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) | host `sora.com` is also on `chatgpt` |
| 40 | `adobe-premiere` | site | **FAIL**: `https://www.adobe.com/products/premiere.html` has a product/marketing path, not an app entry | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) | host `adobe.com` is also on `photoshop` |
| 41 | `capcut` | site | **NOT TESTED**: `https://www.capcut.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 42 | `davinci-resolve` | site | **FAIL**: `url` equals `pricing_url` (`https://www.blackmagicdesign.com/products/davinciresolve`): a marketing/pricing page | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 43 | `opus-clip` | site | **NOT TESTED**: `https://www.opus.pro/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 44 | `topaz-video-ai` | site | **FAIL**: `url` equals `pricing_url` (`https://www.topazlabs.com/topaz-video-ai`): a marketing/pricing page | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 45 | `descript` | site | **NOT TESTED**: `https://www.descript.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 46 | `copy-ai` | site | **NOT TESTED**: `https://www.copy.ai/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 47 | `deepl` | site | **NOT TESTED**: `https://www.deepl.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 48 | `grammarly` | site | **NOT TESTED**: `https://www.grammarly.com/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |
| 49 | `jasper` | site | **NOT TESTED**: `https://www.jasper.ai/` is a bare domain; whether it is the app entry or a marketing home was not checked against the provider's documentation | **FAIL** (no field; kind `site`) | **FAIL**: none listed | **FAIL** (no field) | **PASS** (`archived`) |  |

Reading the table: the Mode, Last verified and OAuth columns are the same everywhere because the fields do not exist; the
useful column is the launch URL. The 14 FAIL rows are the ones the directive calls a marketing page: `claude-code`, `codex`,
`photoshop`, `adobe-premiere`, `dall-e`, `figma-ai`, `airtable-ai`, `loom-ai`, `notion-ai`, `luma-dream-machine`,
`seedance`, `davinci-resolve`, `topaz-video-ai`, `runway`.

## What to build (for Forge's metadata PRs)

Append-only migration adding to `tools`: `app_url`, `info_url` (keep `url`, `pricing_url`), `mode` (`web` / `native` / `cli` /
`api`, several allowed), `oauth_hosts`, `verified_on` (+ who and a source URL), all admin-editable and audited; never
`UPDATE` an existing row's `url`, `hosts` or grants, and fill only rows whose value is still empty. Move `SIGNIN_HOSTS` into the
column for built-ins so an admin can see and edit it. Per-tool values need the provider's own documentation; until then the new
fields stay empty and the Hub should show "not verified" rather than a guess. The shared-host collisions in defect 1 need a
decision on which tool owns `sora.com`, `adobe.com` and `higgsfield.ai` (suggested: one row per host, longer host or path wins).

## Existing tests that touch this

| Behaviour | Test | Verdict |
|---|---|---|
| 49 built-ins seeded | `tests/test_gateway.py:878` (`>= 49`) | PASS |
| Archive / restore / delete a tool | `tests/test_portal.py:157`, `tests/test_gateway.py:923`, `tests/test_portal.py:85` (removed tools cannot be opened) | PASS; ran today: `test_portal` + `test_chrome_policy` 28 tests OK |
| Open goes to SSO link, else website; only web addresses | `tests/test_portal.py:46`, `:77` | PASS |
| Address off the tool's hosts refused; sign-in host never a start address | `tests/test_device_open.py:92`, `:149` | PASS |
| ChatGPT / Claude / Gemini open with their sign-in hosts; built-ins only | `tests/test_device_open.py:132`, `:173` | PASS |
| Every catalogue host reaches the Chrome policy pack | `tests/test_chrome_policy.py:45`, `:52` | PASS |
| Marketing vs app URL, mode, last-verified, per-tool OAuth list | none | NOT TESTED: no test, no field |
| Host collisions (`sora.com`, `adobe.com`, `higgsfield.ai`) or path hosts (`github.com/copilot`) | none | NOT TESTED: no test |
| Fresh-database sign-in of the two dev tools | none | NOT TESTED |

## Directive section 13, checks 1 to 10: what an existing test covers

The ten checks, as Chief gave them on 20 Nov 22:30. "Covered" means a test by that name exists on main `046f6e5` and asserts
the behaviour in its name. I read the names and spot-read the bodies of the device-open and workspace tests; I did **not** re-run
the whole suite for this table (CI does). Only `test_portal` and `test_chrome_policy` were run for this document. "No test"
means no test asserts it, not that the behaviour is wrong.

| # | Check | Existing tests | Verdict |
|---|---|---|---|
| 1 | Catalog metadata correct | `test_gateway.py:878` (49 seeded); `test_chrome_policy.py:45` (every catalogue host reaches the policy pack). Nothing asserts a URL is the official app, a mode, an OAuth list or a verified date | **No test** for correctness; PR #304 adds the fields, so its tests are the first |
| 2 | Valid verified launch destination, or native integration | `test_device_open.py:34, :92, :318, :323` (official address, off-host refused, unsafe addresses refused); `test_portal.py:46, :77` | Covered for *safe*; **no test** that the destination is the *official* app, and no native-integration test for desktop tools |
| 3 | Access control enforced per employee | `test_user_journey.py:41` (add, grant, open, revoke); `test_portal.py:54, :92`; `test_gateway.py:173`; `test_core_proof.py:130, :154, :222`; `test_v2.py:450` | Covered |
| 4 | Correct employee-specific browser profile | `test_browser_profiles.py` (43 tests, e.g. `test_different_owners_do_not_reuse`); `test_w6_matrix.py` (one folder per person, device and OS user); `test_workspace_launcher.py:240` (exact argv); `test_workspace_revocation.py` | Covered (the real Chrome run is the browser job and `docs/RELEASE-EVIDENCE.md`, not a unit test) |
| 5 | Approved auth redirect behaviour | `test_device_open.py:132, :149, :173, :351`; `test_chrome_policy.py:52` (Google only for sign-in and catalogue tools) | Covered for the 3 tools in `SIGNIN_HOSTS`; **no test** for any other tool, and the hosts are unconfirmed (defect 3 above) |
| 6 | Reopen without losing an authorised session | `test_workspace.py:98, :166`; `test_workspace_revocation.py` (`test_2_active_again_with_the_same_generation_reuses_the_folder`); `test_continuity.py:194` | Covered for the Hub session and the workspace folder; **no test** that a *provider's* own session survives a reopen (needs a real provider; NOT TESTED by design) |
| 7 | Refusal for unassigned or revoked users | `test_portal.py:54, :85`; `test_continuity.py:59, :68`; `test_device_open.py:54, :69`; `test_core_proof.py:69` (revoke, next request refused); `test_turns.py:193` | Covered |
| 8 | No cross-user workspace leakage | `test_workspace_revocation.py` (`test_9_another_owners_folder_survives_a_retired`); `test_workspace.py:348`; `test_probe_managed_gaps.py:25`; `test_core_proof.py:130, :149`; `test_provider_registry.py:122`; `test_device_open.py:209` | Covered |
| 9 | No credentials in CLI args, URLs, audit logs or uploads | URLs: `test_device_open.py:323` (`access_token`, `API_KEY`, `id_token`, `password`, userinfo refused); args: `test_workspace_launcher.py:240`; audit: `test_continuity.py:234`, `test_core_proof.py` (audited without the key), `test_w7_existing_contexts.py` (no key audit line); `test_managed_workspace.py:418` (no provider credential); uploads: `test_secret_scan.py` plus the release scan | Covered for URLs, args, audit and release artifacts; **no test** for admin or staff uploads (only `test_portal.py:242`, which checks size and type, not content) |
| 10 | No regression to gateway, reports, admin, device lifecycle | `test_gateway.py`, `test_hub.py`, `test_business.py`, `test_device_lifecycle.py`, `test_core_proof.py`, `test_w7_existing_contexts.py`, and the browser suites (`tests/browser/*.cjs`) | Covered by the full suite on CI; this document changes no code |

Gaps to close with tests: check 1 (metadata correctness) and check 2 (official, not just safe, destination) once PR #304 has
the fields; check 5 beyond three tools; check 9 uploads.
