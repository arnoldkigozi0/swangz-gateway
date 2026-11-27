# Fixed browsers — dormant field

Scope: Control room → Tools → a one-company-login tool → Account limitation.

Required captures (pending): 390x844 and 1440x900, light and dark, synthetic local demo only. No production sign-in.

Visible difference: the field label and explanatory copy identify dormant configuration (BRIEF §10.1.1 words/data; §10.1.4 product-specific settings). Existing controls/styles are reused; saved values and owner editing remain. No new visual pattern or matching reference still for this legacy field.

Runtime check: confirm the dormant help is visible, the textarea keeps a seeded saved address, an owner can clear it and save an empty workspace_url, and the 4 viewports/themes have no horizontal clipping. Confirm the accessible description points at the visible help. Do not test provider launches or claim the routing fix is present before #373 lands.
