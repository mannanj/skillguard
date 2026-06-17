# Task: Favicon and Social Preview Images

**Status:** open
**Created:** 2026-06-17

## Goal

Update the Gandalf landing page identity assets so browser tabs and social shares
use the current mascot consistently.

## Direction

- Create a favicon from the close-cropped mascot face/hat crop shown in the
  reference screenshot.
- Use the full mascot image for Open Graph and social preview images.
- Keep the landing page layout unchanged.
- Set reasonable default metadata for social sharing across Open Graph and
  Twitter/X cards.

## Files

- Landing page metadata: `landing/public/index.html`
- Current full mascot source: `landing/public/gandalf-mascot.png`
- Existing social preview image: `landing/public/og.png`
- Potential generated assets:
  - `landing/public/favicon.ico`
  - `landing/public/favicon-32x32.png`
  - `landing/public/apple-touch-icon.png`
  - `landing/public/og.png`

## Implementation Notes

- Do not use the old inline SVG favicon once the cropped mascot favicon exists.
- Preserve the current page width and visual layout.
- Prefer generating favicon variants from the production mascot asset rather
  than from a desktop screenshot.
- Ensure the OG image is large enough for social previews, ideally 1200x630.
- Include useful `alt` text for the mascot preview image.
- Keep metadata canonical to `https://gandalf.sh/`.

## Acceptance Criteria

- Browser tabs show a cropped Gandalf face/hat favicon.
- `og:title`, `og:description`, `og:image`, `og:image:alt`, and `og:url` are
  present and point at the correct production defaults.
- `twitter:card`, `twitter:title`, `twitter:description`, `twitter:image`, and
  `twitter:image:alt` are present and match the OG defaults.
- The OG image uses the full mascot, not the cropped favicon image.
- Existing landing-page tests pass.
- No unrelated copy, layout width, or hero spacing changes are included.
