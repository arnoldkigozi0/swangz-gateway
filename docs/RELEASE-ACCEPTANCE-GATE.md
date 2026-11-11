# Swangz AI Hub — evidence-based 100% release gate

Status: **NOT YET SATISFIED**. Prepared 11 November 2026. This is a release-acceptance plan, not a claim that tests, installations, or deployment have passed.

## Meaning of 100%

Mark a gate **PASS** only when there is a dated link to a passing test, an approved review, a real-device record, or a verified production observation **for the exact release commit**. Record **FAIL**, **BLOCKED** or **NOT TESTED** otherwise. A green unit-test suite is necessary but not sufficient. Do not convert estimates of completion to facts.

Evidence record for each item: owner; release commit; environment/device; date; test or procedure; result; evidence URL/path; reviewer; remediation and retest reference. Do not record passwords, access tokens, provider cookies, recovery codes or private signing keys.

| Gate | Acceptance evidence | Current evidence / gap at creation |
|---|---|---|
| G1 — Canonical product model | Reviewed blueprint and authorization test for individual workspaces, personal contexts/automations, assigned seats vs individual subscriptions, supported API credentials, and approved organization plans | Amendment 01 merged; end-to-end provider authorization verification still required |
| G2 — Main and review hygiene | Exact release SHA; required CI green; no unresolved blocking review comments; dependency chains reconciled; security findings closed or accepted explicitly | Main CI green at `c863c7d7`; this does not establish production readiness |
| G3 — Individual identity and device lifecycle | Two different employees cannot read or change one another's private workspace data; separate OS accounts/profiles where applicable; enrollment, revocation, logout, rotated keys and session invalidation tested on intended environments | Automated device and user-journey tests exist; representative real-device cross-user evidence required |
| G4 — Providers and billing | Documented matrix per provider: approved sign-in, individual subscription/seat/API/organization authorization, unsupported capabilities marked unavailable, billing owner, account/usage metadata provenance; live tests only with authorized test accounts | Manual registry exists; no claim of live quota/credit synchronization or vendor webhooks |
| G5 — Managed Chrome | Real Windows/macOS/Linux company-device trials as applicable, policy actually applied, distinct user profiles, provider-only access, Gmail/Drive/unrelated Google surfaces blocked, account switch/sync/export routes tested, OAuth exceptions preserved, network/OS enforcement assessed, privilege limitations documented | Chrome policy pack and Linux bypass checks exist; real managed-device and network evidence still required |
| G6 — Small-server control plane | Verify purchased server's identity/ownership and access; domain/TLS; actual deployed SHA/schema; signed webhook verification and replay handling where implemented; health monitoring; backup and restore rehearsal; rollback plan | Server has reportedly been purchased. **Do not purchase another server by default**; no verified running deployment evidence here |
| G7 — Desktop platforms | Windows x64, macOS ARM64 and Linux x64 packaged-app install, device enrollment, update, logout/revocation and uninstall checked on actual supported systems; archives/checksums verified; release signing/notarization where required | Older unsigned CI builds passed; no signed production release; updater disabled |
| G8 — Mobile/PWA | Android Chrome and iOS Safari test record following `docs/MOBILE-READINESS.md`: sign-in, install, standalone mode, use, clean sign-out, offline behavior, icon usability; recheck after final release | Mock/synthetic checks, not real phone acceptance |
| G9 — Design, accessibility and performance | Independent review against `docs/design/BRIEF.md`; supported widths; 44px tap targets; contrast, focus, zoom, keyboard access; real-device performance and acceptable scrolling/CLS; approved screenshots/overlays | UI implementation advanced; unverified device/performance acceptance remains |
| G10 — Security, operations and recovery | Secrets outside Git; permissions and audit review; incident response and administrator recovery; privacy/data retention; network restrictions; backup restore; monitoring alerts; explicit production change approval | Some automated coverage and tooling; real infrastructure operational verification outstanding |
| G11 — Release and rollback | Release manifest with SHA, build and artifact provenance, checksums, signatures, version, distribution channels, tested rollback and named release approvers | No published GitHub Release at creation; unsigned test artifacts are not production distribution |
| G12 — Staff pilot | Authorized pilot users with their own accounts and automations; consented issue logging; zero unresolved release-blocking incidents; owner acceptance against the same SHA | Not demonstrated by GitHub CI |

## Decision and spending boundaries

- Keep existing paid provider subscriptions/accounts where terms permit. API and enterprise billing remain **optional**; do not migrate automatically.
- A Swangz login is not a provider seat. Never share individual account credentials, extract cookies, inject passwords, or bypass provider access rules.
- Model inference remains on providers' hosted services. The **already purchased small server** is for the lightweight control plane, metadata hooks/webhooks and essential application services. Do not add GPU inference, a new VPS, or a browser fleet without a separately approved reason and budget.
- Maintain each employee's own workspace, context and authorized automations. Admin usage oversight must be permission-scoped.
- No production schema migration, key activation, extension rollout, purchase or deployment without Arnold's explicit decision and a recovery plan.

## Owner inputs needed, without inventing or collecting secrets

1. Identify the **existing purchased server** and confirm who can securely run the setup; do not assume another server purchase is necessary. Record only non-secret deployment evidence.
2. Approve the domain/DNS, OAuth return address, initial owners, and provider-account/seat inventory. API keys are only necessary for gateways intentionally using API billing.
3. Decide managed Chrome policy owners, domain/OAuth exceptions and distribution method; provide devices with least-privilege staff OS accounts for testing.
4. Provide a Windows PC, a Mac, a Linux PC as appropriate, an Android phone and an iPhone for actual acceptance trials; specify the supported OS/version matrix.
5. Approve release signing credentials, production database cutover, rollback window, and any purchases **individually**.

## Release verdict template

- Release SHA:
- Release candidate / date:
- G1–G12 status and evidence URLs:
- Open blocking issues and owners:
- Security reviewer:
- Platform owners:
- Operations/deployment reviewer:
- Arnold's explicit go-live approval:
- **Final verdict: NOT READY / READY FOR STAFF PILOT / READY FOR PRODUCTION**

A release is **READY FOR PRODUCTION** only when all applicable gates pass with evidence and approval. Exceptions require a documented owner-approved risk acceptance, not a percentage target.
