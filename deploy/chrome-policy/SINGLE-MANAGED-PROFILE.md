# One administrator-managed Chrome profile per employee/device

**Status:** Policy preparation only; **not** a remotely authenticated or deployed browser. This complements [README.md](README.md) and the client’s currently **inert** `swangz_client/browser_profiles.py`. It does not change `swangz_client.open_app`, spawn Chromium, grant provider access, or activate a policy on any staff device.

## Already included in the Hub

- The Chrome policy template blocks creating more profiles, guest browsing, incognito, Chrome sign-in/sync, remote debugging, password saving and unapproved extensions; it limits navigations to catalogued providers and necessary login hosts.
- Hub device enrolment/revocation, per-person entitlements and provider-seat declarations are separate server-side controls. A device enrolment **is not** a provider sign-in.
- An isolated-profile **preparation** module exists, but it deliberately never starts Chrome and does not verify Windows ACLs.

## Intended experience

1. An administrator enrols a managed company computer with an individual employee OS account; Swangz binds the authorized person and their own work/automations to that device. The administrator remotely assigns **policies and access**, not their own cookies or a provider password.
2. Exactly one company-managed Chrome profile is made available inside **each employee's separate OS account**. The administrator checks for pre-existing local Chrome profiles before rollout. Blocking **creation of more profiles** does not delete or hide pre-existing profiles and does not stop a computer administrator from changing policy.
3. The employee signs into their own provider account, or an individually assigned company seat, using the provider-approved OAuth/SSO/login interface. Administrators may initiate supported enterprise seat assignment/SSO, but may not remotely inject passwords, cookies or copied sessions.
4. The Hub checks a person's tool grant and device status before opening a provider. Revocation stops Hub access; provider-side sessions must be revoked through the provider's supported mechanism separately.
5. On personal computers, do not install OS-wide policy automatically. Chrome Enterprise/MDM rollout on company devices requires explicit owner approval and device-administrator action.

**One visible profile per employee/device is not one provider identity shared by the organization.** Staff retain their separate workspaces, histories and authorized automations. Shared OS accounts cannot provide isolation.

## Prepare a checked policy for the administrator

First obtain the actual production DNS hostname, a fixed extension ID from an approved distribution channel and an approved HTTPS update endpoint. **No credentials, provider cookies or extension signing keys** are required by this command.

```bash
python3 deploy/chrome-policy/prepare.py \
  --hub-host ai.swangzavenue.com \
  --extension-id aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --update-url https://clients2.google.com/service/update2/crx \
  --output ./swangz-company-chrome.prepared.json
```

The ID above is an **example string, not Swangz's real extension ID**. The tool validates required single-profile/default-deny controls, replaces placeholders, and refuses to overwrite the original policy, existing output or system Chrome policy locations. **It never installs or enforces a policy.** On company-managed Windows/macOS/Linux, the administrator uses Group Policy/MDM or the OS policy method in [README.md](README.md), then checks `chrome://policy`. JSON cannot simply be copied unchanged to Windows Registry or a macOS configuration profile.

## Release acceptance checks before rollout

- Use separate non-administrator OS accounts for two employees. Verify neither can read or edit the other's browser profile, provider sessions or private Hub data.
- Verify every applicable policy at `chrome://policy` shows **OK**, the extension is force-installed and its real ID/update URL are correct.
- Confirm that exactly one usable managed profile remains per employee OS account; handle any existing profiles with the employee's consent rather than silently deleting them.
- Test adding a person, profile picker, guest mode, incognito, sync, account switching, credential export, developer tools, remote debugging and disabling extensions on real Windows/macOS/Linux machines.
- Test navigation, redirects, pop-ups, new tabs, frames, downloads, subresources and external protocols. Verify Gmail/Drive/unrelated Google surfaces stay inaccessible while legitimate provider OAuth flows function. **URL navigation policies alone cannot enforce network isolation.**
- Test revoked devices, lost devices, reassigned seats, reauthentication, app sign-out and provider-side session termination where supported.
- Record the release commit and actual test evidence in `docs/RELEASE-ACCEPTANCE-GATE.md` or the canonical go-live record. Treat this as **not production ready** until real-device checks pass.

Keep inference on the AI providers' infrastructure; the already purchased small server remains the lightweight control plane and account/usage metadata service—not a remote Chrome fleet or GPU host.
