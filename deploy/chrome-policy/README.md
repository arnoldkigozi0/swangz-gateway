# Chrome policy pack for company devices

`swangz-company-chrome.json` is a Google Chrome managed-policy file for **computers Swangz owns**. It is not for
personal devices: those keep the Swangz AI Hub Access extension as their only gate, installed by the person.

Status: **written and checked for shape only.** It has not been installed on a real device. The bypass tests
below have not been run. Nothing in this folder is applied by the gateway, the Swangz app or any setup script.

## Before installing: three values to fill in

| Placeholder | Replace with | Who provides it |
|---|---|---|
| `SWANGZ_HUB_HOST` | the Hub's first-party host, for example `ai.swangzavenue.com` (no `https://`) | Arnold (domain) |
| `SWANGZ_EXTENSION_ID` | the 32-letter id of the published Swangz AI Hub Access extension (two places) | Arnold (Chrome Web Store listing, or a signing key for a self-hosted copy) |
| `SWANGZ_EXTENSION_UPDATE_URL` | `https://clients2.google.com/service/update2/crx` for a Web Store listing, or the address of a self-hosted update manifest | same |

Chrome ignores a force-install entry it cannot read, so a file with the placeholders left in **blocks websites
but installs no extension**. The extension has no fixed id today (`extension/manifest.json` has no key and it is
not published), so the pack cannot be complete until it is. On Windows and macOS, Chrome force-installs an
extension from outside the Chrome Web Store only on a managed (domain-joined or MDM-enrolled) computer; an
unlisted Web Store listing avoids that.

## Installing (an administrator of the computer, by hand)

- **Linux:** copy the filled-in file to `/etc/opt/chrome/policies/managed/` (Chromium: `/etc/chromium/policies/managed/`).
- **Windows:** the same names under `HKLM\Software\Policies\Google\Chrome` (Group Policy or a `.reg` file). A
  single-value policy is a value of that key; a **list policy** (`URLAllowlist`, `URLBlocklist`, the three
  `ExtensionInstall…` lists) is a **subkey** of that name holding one string value per entry, named `1`, `2`, `3`, …
  A list pasted as one value is ignored.
- **macOS:** the same names and values in a configuration profile for `com.google.Chrome`.

Then open `chrome://policy`, press *Reload policies* and confirm every row says OK with no "unknown policy" or
error. These locations are the standard ones and were not re-checked on a device for this pack.

## What it enforces

| Policy | Effect |
|---|---|
| `URLBlocklist: ["*", …]` with `URLAllowlist` | Default deny. A page opens only on the Hub, a catalogue provider's domain (and its subdomains), or one of the sign-in addresses below. Gmail, Drive, YouTube, Google account settings (`myaccount.google.com`) and every other site are refused because they are not on the list. `file://`, `chrome://flags` and `chrome://inspect` are refused by name |
| Sign-in addresses | `accounts.google.com` and `accounts.youtube.com` (exact hosts, written with a leading dot so no other Google host matches), Microsoft and Apple sign-in, GitHub's sign-in paths, reCAPTCHA and Cloudflare challenge pages. Without these, "Continue with Google" on the Hub and on providers stops working |
| `BrowserSignin: 0`, `SyncDisabled` | Nobody can sign Chrome itself into a Google account or sync bookmarks, passwords and history out of the computer |
| `BrowserAddPersonEnabled: false`, `BrowserGuestModeEnabled: false`, `IncognitoModeAvailability: 1` | No new profiles, no guest window, no incognito window (the extension gate does not run in those) |
| `DeveloperToolsAvailability: 2`, `RemoteDebuggingAllowed: false` | No developer tools and no remote-debugging port, so a signed-in session cannot be copied out that way |
| `PasswordManagerEnabled: false` | Chrome does not offer to save provider passwords on a company computer |
| `ExtensionInstallBlocklist: ["*"]`, allow list and force list | Only the Swangz extension is installed, it is installed automatically and it cannot be removed or switched off |

The split of work: this file decides **which sites a company computer can reach at all**; the extension still
decides **which of those tools this person is entitled to** and records access-level use. Every catalogue
provider is on the list, so removing a person's grant is still done in the control room, not here.

**Not on the allow list:** a tool added in the control room after this file was written, and the addresses of
company browsers (Neko). Each needs its exact host added here and the file re-installed. Never add
`*.trycloudflare.com` (or any other shared tunnel domain): anyone can get an address under it, so allowing it
allows every site someone chooses to put behind one. A company browser on a quick tunnel is not reachable from a
computer under this policy until it has a fixed first-party address.

`tests/test_chrome_policy.py` fails if a catalogue provider host is missing from the allow list, if a wider
Google address than the two sign-in hosts appears, or if one of the controls above is removed.

## What it cannot do

- **Another device or browser.** It governs Chrome on the computer it is installed on. Firefox, Edge, a phone
  or a personal laptop are untouched. Provider-side identity and assigned seats remain the real authority.
- **A local administrator.** Anyone with administrator rights on the computer can delete the file or the
  registry keys. Staff accounts on company computers must not be administrators.
- **Choosing the Google account.** `accounts.google.com` has to stay reachable, so a person can still type a
  personal Google account into a provider's sign-in page. Chrome's `AllowedDomainsForApps` policy can limit Google
  sign-in to `swangzavenue.com`; it is **left out** because it would also lock out the two approved owner
  exceptions. Adding it is Arnold's decision.
- **Parts of a page.** The lists are documented for page addresses. Whether a blocked address is also refused
  inside a frame, or as a script or image, is not stated in Chrome's filter documentation and was not tested.
- **Chrome's own pages.** A `*` entry does not cover `chrome://` or extension pages (Chrome's documentation says
  so), which is why two are blocked by name and the rest (settings, new tab) stay open.
- **Network or system level blocking.** None here; out of scope before 20 November.
- **Separating people who share one operating-system login.** The policy is per computer, and Chrome's profile,
  cookies and signed-in provider sessions belong to the OS account. Two people on one OS login see each other's
  sessions. A shared OS login is not isolation; each person needs their own OS account.
- **Links that open other programs, or Chrome started with switches.** Whether the URL lists stop `mailto:`,
  `zoommtg:` and similar external-protocol links, and whether a managed force-installed extension survives
  `--disable-extensions`, is not established here; both are in the checks below.
- **A provider that moves its sign-in.** A provider that sends people through a host not on the list will show
  Chrome's "blocked by your organisation" page until the host is added.

## Checks still to run on a real company computer (not run)

1. `chrome://policy` shows every row OK on Windows, macOS and Linux.
2. Gmail, Drive, `myaccount.google.com`, a direct IP address, a `file://` path and a new-tab search are refused.
3. "Continue with Google" completes on the Hub and on ChatGPT, Claude and Gemini; Microsoft sign-in on Copilot.
4. The extension is present, cannot be removed, and still blocks a tool the person is not assigned.
5. Add person, guest, incognito, Chrome sign-in and developer tools are unavailable.
6. Redirects, pop-ups and new tabs to a host off the list are refused.
7. A `mailto:` link and a `zoommtg:` link on an allowed page do not open another program (or note which do).
8. Chrome started with `--disable-extensions` still runs the Swangz extension, or opens no AI site without it.

Policy names (checked 10 Nov 2026): all thirteen names in the file exist, with these types and values, in
Chromium's policy definitions (`components/policy/resources/templates/policy_definitions`), none marked deprecated.
Two notes from those definitions: `BrowserSignin` applies on Linux only from Chrome 145 (Windows and macOS from 70);
and from Chrome 147 a `*` block entry no longer covers `chrome://` addresses, which this pack already assumes.
Google's rendered policy list and the Windows registry layout for list policies could not be opened for this check;
the numbered-subkey note above is unconfirmed until checked on a Windows computer (`chrome://policy` shows the lists).

Sources: Chrome Enterprise "URL blocklist filter format" (read 10 Nov 2026: subdomain matching, the leading
dot, path prefixes, and that `*` does not cover `chrome://`). The other policy names and values follow the pack
already used for company browsers in `workspace_agent/agent.py` and were not re-read from Google's policy list
for this change.
