# SkillGuard Landing Revamp Design

Date: 2026-06-16

## Goal

Revamp the SkillGuard landing page into a smaller, sharper single-scroll page.
Every word should earn its place. Color should communicate state, not decorate.
Animation should be sparse and product-specific.

## Current Truth

SkillGuard supports Claude Code skills and MCP servers today.

It scans skill files, bundled scripts, MCP configs, launch commands, endpoint
metadata, and env/header names while keeping secret values off disk. The hook
blocks unscanned or changed skills. MCP tool calls are governed by `mcp_policy`;
the current default is `enforce`, which blocks unscanned or critical/high MCP
verdicts.

The page must not imply Codex, Gemini, or all-agent support yet. That future work
is tracked in `task-agent-harness-expansion.md`.

## Positioning

Primary line:

> Scan skills. Block unscanned.

Supporting line:

> SkillGuard checks Claude Code skills and MCP servers before runtime, then
> refuses what has not cleared.

The lead noun is `skills`; MCP appears as a first-class badge and in proof/how
sections. Avoid roadmap phrasing like "all agents", "agent harnesses", "coming
soon", or "works everywhere".

## Structure

1. Sticky nav
   - Wordmark only on the left.
   - Right side: `Install` and `GitHub`.
   - No extra section nav.
2. Hero
   - Gate animation above or beside the headline.
   - Headline: two short clauses, one accent word.
   - One-sentence subhead.
   - Command rail CTA.
   - Trust strip: `Skills · MCP · local by default · secrets never cached · source`.
3. Proof
   - Keep the Koi and Snyk evidence, but shorten it.
   - Use exact numbers only: 341 malicious skills and 13.4% critical issues.
   - Frame as a shared trust model, not as a Claude Code incident.
4. How it works
   - Three terse cards:
     - `Read` — skill files and MCP surfaces.
     - `Gate` — block unscanned, changed, or high-risk verdicts.
     - `Remember` — cache/history with redaction and false-positive triage.
5. FAQ
   - Native `details`.
   - 4-5 questions max.
   - Nuance lives here: MCP policy, secret handling, engines, install methods,
     license.
6. Footer
   - Wordmark, GitHub, licenses, human signature.

## Command Rail

The hero CTA should use one stable install command first:

```sh
curl -fsSL https://skillguard.sh/install | sh
skillguard --target all --engines local
```

Under the command box, use small selectable or auto-rotating labels that describe
real modes:

- `Install`
- `Scan skills`
- `Scan MCP`
- `Hook gate`

Do not include Codex or Gemini entries until those commands are implemented and
tested.

Claude Code plugin commands can move to a secondary "More install methods" link
or a FAQ answer. The first impression should not look Claude-plugin-only.

## Visual Direction

Use a disciplined security-console palette:

- Background: near-black, slightly warm.
- Text: soft off-white.
- Muted text: cool gray.
- Green: only for cleared, active, copied, or supported.
- Red: only for blocked or critical.
- Amber: only for evidence, warnings, or secondary attention.

Remove the broad green glow and most ornamental shadows. Keep panels flat and
dense. Border radius stays modest, 8px or less except small pills.

## Animation

Keep the gate animation, but make it quieter and more literal:

- Chips: `SKILL.md`, `scripts/setup.sh`, `.mcp.json`, `webhook MCP`.
- Clean chips pass once.
- One bad chip stops, shakes briefly, and receives a red label.
- Animation is CSS-only.
- `prefers-reduced-motion` freezes the gate into a readable tableau.

Do not add decorative or continuous ambient motion elsewhere. The command rail
may rotate labels slowly only if it remains readable and stops under reduced
motion.

## Accessibility And Progressive Enhancement

- Keep skip link and visible focus rings.
- Page remains coherent with JavaScript disabled.
- Copy button has a legacy fallback.
- FAQ uses native `details`.
- Video fallback transcript remains available.
- Reduced-motion disables video autoplay and freezes CSS animation.

## Verification

Before calling the revamp complete:

- Run local static/browser checks.
- Capture desktop and mobile screenshots.
- Verify no horizontal overflow.
- Verify reduced-motion render.
- Verify copy button behavior.
- Verify JS-disabled content remains coherent.
- Confirm links and install command are accurate.

## Out Of Scope

- Shipping Codex, Gemini, or generic all-agent support.
- Rewriting scanner or hook behavior.
- Changing Cloudflare deployment plumbing.
- Adding new libraries or build steps to the static landing page.
