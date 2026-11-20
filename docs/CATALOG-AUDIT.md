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

## Directive section 13, checks 1 to 10

NOT TESTED. The text of section 13 was not in the repository, the mission files or the handoff Probe received, and the checks
are not guessed here. Send the ten checks and Probe will map each to a test, or to "no test", in a follow-up commit on this
branch. The existing journey and catalog tests are listed above; the end-to-end journey is `tests/test_user_journey.py:41`
(add, grant, sign in, open, see, revoke, sign out).
