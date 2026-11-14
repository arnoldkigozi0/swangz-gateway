# W3 threat note: the workspace launcher, the profile folder and the provider address

Written against `docs/MANAGED-WORKSPACE.md` at PR #175 head `d1d4df9` (§2 hard limits, W3, §9.1, §9.3) and the
integration branch `feature/managed-workspace` at `88338ac`. Builders follow it; a deviation needs a recorded reason.

**Scope:** what happens when someone presses **Open** on the device: the client asks the Hub for the provider
address, checks it, finds Chrome or .deb Chromium, and starts it with the person's single workspace folder. It also
covers the `open_url` caller inventory. Revocation, purge and closing the browser are W4 and are not covered here.
Policy install is W5 and W6.

## Assets

- **A1 The device key.** It must never appear on the browser's command line, in its environment, in a URL, in a
  log or in a crash report.
- **A2 The workspace folder.** It holds the person's provider sessions. Only that person, as that OS user on that
  device, may launch it. The app never reads anything inside it.
- **A3 The person's default browser and personal Chrome profile.** They are never launched for providers, never
  read and never modified.
- **A4 The access decision and launch record.** The server decides, the same way `/go/` does.
- **A5 The provider address.** Only `https`, and only on the tool's allowed hosts.

## Entry points

- **E1 Open triggers:** the app button, the tray, deep links and links in Hub pages. Assume any web page can fire a
  deep link.
- **E2 The new device-key endpoint** that turns a tool id into an address.
- **E3 Finding the browser binary.**
- **E4 The command line and environment of the launched browser.**
- **E5 The profile folder and its marker** (`browser_profiles.Profiles`, `.swangz-profile.json`).
- **E6 Opening a second time** while the browser is already running.
- **E7 Any remaining `open_url` or `webbrowser` path** to the default browser.

## Abuse cases → required controls (STRIDE)

**S1, spoofing: the address request is made for someone else.**

- The endpoint takes the person only from the device row behind the Bearer key. It ignores any `person`, `email`
  or `device` field in the request.
- It refuses when any of these hold:
  - the key is revoked or expired;
  - the person is paused, deleted or past `access_until`;
  - the device's workspace state is not `active` (from W2's migration, schema v26);
  - the device is signed out;
  - entitlement (`entitle.py`) is anything but `enabled`, or a policy denies it (policies only take access away;
    an unreadable one fails closed).
- Refusals use the same plain reasons as `/go/` and carry no address.

**S2, tampering: the address is wrong or hostile.** Bad addresses include `javascript:`, `http:`, `file:`,
`https://user:pw@…`, a non-provider host, a newline or space, or text starting with `-`.

- **Server:** take the address from `catalog.launch_target` but require `https`. `launch_target` accepts `http`;
  the device path must not. Also require:
  - no userinfo;
  - at most 2048 characters;
  - no whitespace or control characters;
  - the host is one of the tool's `hosts`, or a subdomain of one, or one of the sign-in domains in the policy pack
    (`deploy/chrome-policy`).

  If any check fails, refuse with "This tool's address isn't allowed. Ask your admin." and never return the
  address.
- **Client:** run the same check again, against the hosts in the authenticated contract-2 manifest entry for that
  tool. If the manifest has no `hosts` for apps today, ask Forge to add them to contract 2 only, so contract 1 stays
  byte-identical.
- The address is passed to the browser as one item in an argument list, never through a shell. It is always the
  last argument, and it cannot start with `-` because of the `https://` check.

**S3, tampering or elevation: the wrong browser runs.** Examples are a fake `google-chrome` placed earlier in
`PATH`, snap Chromium, Edge or Brave.

- Look only in fixed absolute locations, never in `PATH`:
  - Linux: `/opt/google/chrome/chrome`, or Debian or Ubuntu .deb Chromium at `/usr/lib/chromium/chromium` or
    `/usr/lib/chromium-browser/chromium-browser`.
  - macOS: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
  - Windows: `%ProgramFiles%` or `%ProgramFiles(x86)%` `\Google\Chrome\Application\chrome.exe`, then
    `%LocalAppData%\Google\Chrome\Application\chrome.exe`.
- On Linux, refuse when any of these hold:
  - the real path is under `/snap/` or `/var/lib/snapd/`;
  - the file is a script (first bytes `#!`) rather than ELF;
  - the file is writable by group or others.
- If no browser is found, show the plain message with one install-page button (§9.1). **Never fall back to the
  default browser.**

**T1, tampering: the profile folder is swapped.** Someone could replace the folder or the root above it with a
symlink or junction to another user's folder, or to the person's own Chrome profile.

- Resolve the folder through `Profiles` (the O_NOFOLLOW chain already reviewed).
- Immediately before launch:
  - re-check that the folder is a real directory, not a symlink or reparse point;
  - on POSIX, check it belongs to the current user and has mode 0700;
  - on Windows, check it has an owner-only ACL, and **refuse if this cannot be verified** (W3 text). The inert
    slice states the ACL is not verified, so this is new work. Use stdlib `ctypes` (`GetNamedSecurityInfoW`), and
    add a test on the Windows CI runner.
- The marker must exist and must match **all** of these:
  - `origin` equals the normalised server address;
  - `person_id` and `device_id` equal the enrolled device store;
  - `os_user` equals the current user, using the uid on POSIX and the SID on Windows, not a username string.
- A mismatch refuses launch and never purges. Purge happens only through W4's authenticated `retired`.
- Extending the marker's allowed states beyond `prepared` is a change to the strict key and state check. Do it
  explicitly and test it.
- The remaining gap between the check and Chrome opening the folder can only be exploited by a process already
  running as the same OS user, which is out of scope (same-user malware owns everything).

**I1, information disclosure: the key or tokens leak through the process.**

- The command line is exactly:
  - the binary;
  - `--user-data-dir=<folder>`;
  - `--no-first-run`;
  - `--no-default-browser-check`;
  - the URL.

  A test asserts the full argument list.
- **Forbidden switches:**
  - `--remote-debugging-port` and `--remote-debugging-pipe`, because any local process could then read the
    cookies, which breaks hard limit 1;
  - `--load-extension`, because the extension comes only from policy;
  - `--disable-web-security`;
  - `--proxy-server` and `--proxy-pac-url`;
  - `--enable-automation`;
  - `--disable-extensions`;
  - `--incognito`;
  - `--user-agent`;
  - `--profile-directory` with anything other than the default.
- **Environment:** start from the parent's environment and remove every `SWANGZ_*` variable, `ANTHROPIC_*`,
  `OPENAI_*`, and every key, base-URL or proxy variable that `agents.py` sets. A test asserts none survive.
- Start the process with `shell=False`, `close_fds=True` and stdin, stdout and stderr set to `DEVNULL`. Chrome's
  own messages must not end up in the app's logs.
- **Client log:** write `open <tool_id>` only, with no URL, query or fragment, following the bounded
  `credential-access.log` pattern.
- The server reply includes `{url}` and nothing else, with `Cache-Control: no-store`.

**I2, information disclosure: the app reads provider data.**

- No code path opens, lists or copies anything under the workspace folder except the marker file. Locks, cookies,
  `Local State`, `Preferences` and `SingletonLock` are not read, not even to detect a running browser (see D1).
- No backup, support bundle, crash report or diagnostics export includes the workspace folder or any path inside
  it. `bundles.py` and any "send logs" action exclude the profiles root explicitly; a test asserts it.
- The heartbeat reports only what W2 defined (state, generation, policy sha256 and mode). It never reports
  provider names seen in the browser, tab URLs, history or session status.

**R1, repudiation: a launch with no record.**

- The address endpoint writes the same launch record `/go/` writes (person, tool, device, time, outcome), so
  Activity shows device launches beside web launches. A refused request is recorded with its reason, by the
  dispatcher's refusal audit or an explicit record, never silently.
- The client does not invent or replay launch records; the server's record is the only one.
- Records stay access-level only: no address query string, no fragment.

**D1, denial of service: opening twice, or a stuck folder.**

- A second **Open** while the browser the app started is still running hands the address to that same process
  (start the binary again with the same `--user-data-dir` and the URL; Chrome forwards it to the running
  instance). The app does not parse Chrome's lock files to decide this.
- The app keeps only the PID of the process it started, in memory, so W4 can close it. It never signals a process
  it did not start.
- A folder already in use by a browser the app did not start (R-2: someone launched Chrome on it by hand) is not a
  reason to delete, move or "repair" the folder. Show the plain message and stop.
- The address endpoint is rate-limited per device like other device-key routes; repeated refusals do not lock the
  person out of the web Hub.

**E1, elevation: a path around the managed workspace (E7).**

The inventory on `feature/managed-workspace` at `88338ac`; each caller ends at `shell.open_url` →
`webbrowser.open`, the person's default browser:

| Caller | What it opens | Required in W3 |
|---|---|---|
| `swangz_client/core.py:599` (`login`) | the device-code approval page on the Hub (`same_origin_url` checked) | **Keep.** Approval must happen in the person's own signed-in browser, never in the workspace. |
| `swangz_client/gui.py:215` ("Open the page again") | the same approval page | **Keep**, same reason. |
| `swangz_client/core.py:1054` (`open_app`) | `app["open"]`, the Hub `/go/<tool>` address | **Change.** For a tool the manifest marks as a managed-workspace tool, call the W3 launcher instead; it must never fall back to `open_url` when the launcher refuses. Other tools keep `/go/` in the default browser, as today. |

- A test asserts that, for a managed-workspace tool, `open_app` never reaches `shell.open_url` on any refusal path
  (no browser, bad address, marker mismatch, state not `active`).
- A deep link or a Hub page link to a provider tool goes through the app's launcher or through `/go/`; there is no
  third path. Deep-link handlers take only a tool id, never a URL.
- Nothing in W3 widens access: the launcher can only open what `/go/` would allow for the same person at the same
  time, and the server makes that decision.

## Tests that prove it (all against `tests/fake_upstream.py` and temporary folders; no real browser starts)

1. Server: each S1 refusal (revoked key, paused person, past `access_until`, state `suspended`/`retired`, not
   entitled, policy deny, unreadable policy) returns no address and leaves a record.
2. Server: each S2 bad address is refused; an `https` tool-host address passes; `Cache-Control: no-store` is set;
   fields in the request body cannot choose the person or device.
3. Client: the address check rejects the S2 list against manifest hosts.
4. Client: the binary finder ignores `PATH`, refuses snap paths, `#!` scripts and group/other-writable files, and
   never returns the default browser.
5. Client: symlinked folder, symlinked root, wrong owner, mode other than 0700, missing marker and each marker
   field mismatch refuse launch and leave the folder untouched.
6. Client (Windows CI runner): an ACL with any entry beyond the owner refuses launch; an unreadable ACL refuses
   launch.
7. Client: the exact argument list; none of the forbidden switches; no secret-bearing variable in the child
   environment; `shell=False`, `close_fds=True`, `DEVNULL` streams (assert the `Popen` call with a stub).
8. Client: the log line is `open <tool_id>` with no URL.
9. Client: `open_app` for a managed-workspace tool never calls `shell.open_url` on any refusal path.
10. Client: no code reads under the workspace folder except the marker (stub `open` and `os.scandir` and assert the
    paths touched).

## Out of scope here

W4 (closing, purge, generation), W5/W6 (policy read and install), and the open risks R-1 to R-8 in
`docs/MANAGED-WORKSPACE.md` §6. None of them is claimed closed by W3.
