# Audit O1 height

Recovered fixture measurements on `89e25eb` show Simple ending at y=686, with
a 352px table wrapper, in dark and light at 1440×852 (default and +80 rows).
Detailed ends at y=732 with a 462px wrapper. Both have zero document overflow.
These are baseline measurements from an interrupted review, not a verdict.

The Models-specific 500px height allowance no longer applies to Audit. Audit
uses the normal table allowance, increasing the Simple list by 110px at this
viewport. Its existing long-list browser check now also requires the panel to
use the free height above the footer. Fresh screenshots and reviewer evidence
are pending. This follows BRIEF 10.10.2/7; no Audit reference still exists.

## Correction after review of 4c896e3

That revision failed locally and on CI: with a pager, the 462px wrapper pushed
the panel to 796px and the page to 876px. The existing page needs 80px after
the panel for its footer and margins, so a panel bottom of 796 was too low.

The wide Simple table now reserves 360px for its header, filter and footer
allowance, plus 54px when SUI.table renders a pager sibling. At 1440×852 its
caps are 492px without a pager or 438px with one, targeting panel bottom 772px
in either case. Models, Detailed, phone and tablet caps retain main's rules.
The long-list test derives the available panel bottom from the page's actual
footer padding, and keeps its independent no-document-scroll check.

Fresh actual verification and new-head CI are required. The failed revision's
evidence stays labelled under head-4c896e3/; it is not a passing verdict.

The shared AGENT-PROGRESS checkpoint for #231/#233/#234 is carried by #231
to avoid competing appended logs. The actual passing Audit verdict is in
head-992a07a/NOTES.md with its screenshots, measurements and 164-check run.
