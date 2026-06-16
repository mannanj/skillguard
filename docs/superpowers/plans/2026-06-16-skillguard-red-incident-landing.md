# SkillGuard Red Incident Landing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current green console-style landing page with a red-led incident-report landing page that positions SkillGuard as the runtime refusal gate for Claude Code skills and MCP servers.

**Architecture:** Keep the landing as a single static HTML file with inline CSS and vanilla JS. The hero product demo becomes a CSS-only PreToolUse refusal receipt instead of the current green shield conveyor, while the terminal video remains available lower on the page as supporting proof.

**Tech Stack:** Static HTML, inline CSS custom properties, CSS keyframes, vanilla copy-to-clipboard JS, Cloudflare Worker static asset deployment.

---

### Task 1: Save Future Evidence Idea

**Files:**
- Create: `task-rising-malicious-skill-counts.md`

- [x] **Step 1: Create the task file**

```markdown
# Task: Represent rising malicious skill counts

**Status:** future
**Created:** 2026-06-16

## Idea

Explore a future landing-page or product surface that shows malicious skill counts rising over time, then connects those counts to SkillGuard's reproduced third-party detections and local blocking behavior.

## Why This Is Not In The Current Revamp

The current landing needs a tighter runtime-gate story. A live or rising counter could be useful, but only after we decide which published numbers, reproduced samples, and SkillGuard-found samples we want to show.

## Questions To Answer

1. What data source is trustworthy enough to cite or refresh?
2. Is the count manually curated, periodically fetched, generated from SkillGuard's own scan corpus, or split across those buckets?
3. Should the presentation be a static evidence strip, a timeline, a counter, or a product demo that replays detections?
4. Which third-party samples has SkillGuard reproduced, and which samples did SkillGuard find independently?
5. Does the count belong on the marketing page, in docs, or inside the CLI/report output?

## Completion Criteria

- Pick a source and update policy.
- Define exact copy constraints for claims.
- Prototype at least two presentations.
- Publish or link the reproducible sample/methodology set behind any SkillGuard-specific count.
- Verify every number against primary sources before shipping.
```

### Task 2: Redesign Static Landing

**Files:**
- Replace: `landing/public/index.html`

- [x] **Step 1: Rewrite the page around the approved copy**

Use the section order `Nav -> Hero/Product Demo -> Proof -> Terminal Demo -> How -> FAQ -> CTA -> Footer`.

- [x] **Step 2: Replace the visual system**

Use black, white, gray, and red only. Do not use green for pass/cleared states.

- [x] **Step 3: Keep progressive enhancement**

Preserve skip link, focus styles, native `details`, reduced-motion handling, video fallback, and copy-to-clipboard fallback.

### Task 3: Verify

**Files:**
- Read: `landing/public/index.html`

- [x] **Step 1: Check for green remnants**

Run:

```bash
rg -n "#3DDC97|green|--accent: #3|27C93F|✓|✔" landing/public/index.html
```

Expected: no matches.

- [x] **Step 2: Start a local static server**

Run from `landing/public`:

```bash
python3 -m http.server 4173 --bind 127.0.0.1
```

Expected: server responds at `http://127.0.0.1:4173/`.

- [x] **Step 3: Browser smoke test**

Load the page with Playwright or a browser automation tool, capture desktop and mobile screenshots, and check for console errors.

- [x] **Step 4: Verify copy button behavior**

Click the hero copy button and confirm its text changes to `Copied`.

- [x] **Step 5: Verify reduced-motion and JS-disabled coherence**

Confirm the CSS demo freezes under reduced motion and the page remains readable without JavaScript.
