# Task: Universal Site Header and Footer

**Status:** open
**Created:** 2026-06-17

## Goal

Create a consistent site header and footer across the static Gandalf site.

## Direction

- The universal header should match the current home page header:
  - right-aligned navigation
  - `Install` primary button
  - `Docs` text link
  - GitHub icon link
- The universal footer should match the requested cleaned-up footer:
  - remove the bottom-left red `G` mark
  - remove the footer `Gandalf` brand text
  - keep the useful footer links and attribution
- Apply the same header/footer treatment to all current site pages:
  - `landing/public/index.html`
  - `landing/public/docs/index.html`

## Implementation Notes

- Preserve the static no-build deployment model.
- If true shared partials are not practical in the current static setup, keep
  the duplicated markup intentionally identical and document that constraint.
- Use root-safe links so the header works from both `/` and `/docs/`.
- Do not change hero widths, docs content width, or install box width as part of
  this task.
- Keep the GitHub icon accessible with an `aria-label` and screen-reader text.

## Files

- Home page: `landing/public/index.html`
- Docs page: `landing/public/docs/index.html`
- Tests: `tests/test_landing_page.py`

## Acceptance Criteria

- Home and docs pages share the same visible header navigation pattern.
- Home and docs pages share the same visible footer link pattern.
- The footer no longer shows the red `G` mark or `Gandalf` text at bottom left.
- Header links work correctly from both `/` and `/docs/`.
- Existing landing/docs tests pass after updating any intentional assertions.
- No unrelated layout, copy, favicon, or social-preview changes are included.
