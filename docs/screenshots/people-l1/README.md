# People on the control kit

Captured by `tests/browser/people.cjs` in CI at 1440x852 and 390x844, in dark and light, against synthetic data.
The rows named "Kit Test" and "Kit Variant" are people the test adds as it goes.

- `people-*`: the list, with the search and status filter, one ⋯ per row, and the split Add person button.
- `people-add-*`: Add person with both required fields refused, each marked invalid.
- `person-sheet-*`: the side sheet a row opens, with links into the record.
- `person-tools-give-*`: their tools on the record's Access tab, one ⋯ per row, with the kit picker open to give another.
- `person-record-*`: the record, with the trail and one Next step line under the description.
- `person-next-suspended-*`: the same line on a suspended person, pointing at their security signals.

Differences from BRIEF 10.10, left for following PRs:

- [later] The record's Overview still holds the recent-activity preview, and its Access tab holds two blocks. `docs/UI.md` moves the preview to the Activity tab.
- [kept] The full record stays a page at `#/people/<id>`, as `docs/UI.md` says. The side sheet is the preview, and add and issue key are sheets.
- [absent] There is no import option on Add person, because no import endpoint exists.
