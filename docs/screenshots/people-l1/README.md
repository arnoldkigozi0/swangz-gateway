# People on the control kit

Captured by `tests/browser/people.cjs` in CI at 1440x852 and 390x844, in dark and light, against synthetic data.
The rows named "Kit Test" and "Kit Variant" are people the test adds as it goes.

- `people-*`: the list, with the search and status filter, one ⋯ per row, and the split Add person button.
- `person-sheet-*`: the side sheet a row opens, with links into the record.

Differences from BRIEF 10.10, left for following PRs:

- [later] The Tools panel on the record still uses its own row buttons and picker.
- [later] The record's next-step line and the trail are not added; the trail waits on the frame change in #120.
- [kept] The full record stays a page at `#/people/<id>`, as `docs/UI.md` says. The side sheet is the preview, and add and issue key are sheets.
- [absent] There is no import option on Add person, because no import endpoint exists.
