# Sprint report, 11 Nov 20:45 to 12 Nov 10:00 (written 12 Nov 20:00)

Basis: merge history of main (`git log --merges`) and the reports teammates sent me. GitHub was unreachable from the laptop when this was written, so CI status and PR text were not re-read. Main is `0135ac2` (per the manager's 19:55 note: green and live).

## Merged, and checked by Probe in a real browser
- Probe's point-7 basic-user test passed on main `c863c7d` (11 Nov). I did not read the full report.
- Probe's verdicts for #141 (buttons), #151 (People Simple), #152 (Tools Simple) and #157 are in #165, merged 12 Nov 05:36. Its button fix list led to #166 (D1+D2) and #171 (D3).

## Merged, not checked in a real browser (Probe re-test ordered for the 20:00 shift)
- Simple view: Licences & spend (#159), Security (#162), Models (#163), Access requests (#164), Audit log (#167); Person Access tab (#158); follow-ups (#161, #168); plain words on Licences, Tools and Devices (#169).
- Buttons D1+D2 (#166), phone button hit area D3 (#171); staff shell and top bar (#170).
- #153 security review; #147, #148, #154, #155, #141.

## Merged against the rules (decided by Arnold)
- #149 (spec) and #150 (managed workspace W1) merged 11 Nov 23:34-23:35 without written approval. Arnold chose to keep #150; revert #156 closed.

## Not done
- R15 sign-in, R16 light theme, R17 phone bottom bar: no PR merged. (Probe's report of R16 staff shell: #170 merged.)
- Managed workspace W2-W7: not merged by rule; open PRs need Arnold's written approval each. #160 (R-8 options) open for Arnold.
- Footer scroll: measured 28-39 fps against the 55 fps gate (BRIEF 10.9). The gate is not met; it needs a real-GPU device.
- Devices and Security pages: Simple view merged but no verdict yet (see above).
- About 14 commits on main since 11 Nov 21:00 carry a Co-Authored-By trailer. History not rewritten; Arnold decides.
- The 08:00, 10:00 and 12:00 shift messages failed with API errors, so no work was directed then.

## Honest percent against the BRIEF
About 70-75%. Basis: of the nine console pages in the point-7 Simple view, two (People, Tools) have a real-browser verdict and five more are merged but unchecked; the remaining pages were already in the structure. Buttons, staff shell and tab strip are merged. Sign-in, light theme and the phone bar are not done, the footer fps gate is unmet, and nothing on the managed browser beyond W1 exists. This is an estimate, not a measured figure; I will update it after Probe's re-test.
