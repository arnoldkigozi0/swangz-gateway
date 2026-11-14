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
