# Task: Make SkillGuard itself resilient to prompt-injection & malformed-unicode

**Status:** BUILT 2026-06-26 — the local guard (gaps 1 & 2) is implemented,
tested, and mutation-proven; see "Implementation" below. Gap 3 (remote SkillAudit
hardening) and homoglyph/mixed-script detection remain follow-ons, as scoped.
**Created:** 2026-06-26
**Why now:** raised in-session — "is our scanner itself hijackable by prompts or
malformed unicode, and can we guard against it + surface those as alerts?" Maps
to Nesbitt threats 2.30–2.33 (scanner truncation/paraphrase/decomposition/
jailbreak evasion) and the Trojan-Source class (CVE-2021-42574).
**Companion task:** `task-agent-assisted-triage.md` — that LLM-in-the-loop idea
has THIS task as a hard prerequisite (you cannot safely feed untrusted skill text
to a reviewer LLM until the text is defanged here).

## The susceptibility (analyzed this session — RE-VERIFY before building, drift)

Two real local gaps + one remote, found by reading live code 2026-06-26:

1. **Evasion — regex has no unicode normalization.** `engines/local.py` matches
   `LOCAL_PATTERNS` against raw lines. The *only* obfuscation defense is one rule
   in `patterns.py`: `_p("obfuscation","high", r"[​‌‍﻿]{3,}", …)`
   (≥3 consecutive zero-width chars). So these EVADE every pattern today:
   - a **single** zero-width char mid-token: `cu​rl | bash` ≠ `curl|bash`;
   - **homoglyphs** (Cyrillic `с`/`о` for Latin) — NFKC does *not* fold across
     scripts, so this needs a confusables/TR39 skeleton, not just NFKC;
   - **bidi / RTL overrides** (`‪–‮`, `⁦–⁩`) — Trojan Source;
     reorders displayed text vs. logical bytes.
2. **Self-injection — our own output is unsanitized.** `Finding.context` carries
   raw skill text (`engines/local.py::_context_excerpt` only trims length). It is
   `print()`ed to the terminal (`render/reports.py`) and to the hook's stdout
   (`hook.py` print paths). No ANSI/control-char stripping. So a skill line with
   embedded ANSI (`\x1b[…`) can **spoof/erase SkillGuard's own output** (hide a
   finding, fake a clean line), and injection prose in a `context` excerpt is fed
   straight into the **agent harness that reads the hook output**. This is the
   vector that matters most for `task-agent-assisted-triage.md`.
3. **Remote engine surface (note, lower priority).** `engines/skillaudit.py`
   POSTs skill content to `skillaudit.vercel.app`. If that endpoint is LLM-backed,
   the skill can jailbreak the reviewer (Nesbitt 2.33). Out of scope for the local
   guard but worth a hardening note on the service side.

## Proposed guard (directions for the fresh agent to design + scope — not a spec)

A single **text-safety authority** (suggest new `skillguard/sanitize.py`,
analogous to `mcp/secrets.py` being the redaction authority). Likely shape:

- `fold_for_detection(text)` — NFKC-normalize + strip invisibles/bidi, so regex
  sees through obfuscation. LocalEngine scans **raw + folded** and merges. FP
  guard: only fold lines that actually contain invisible/bidi chars, so benign
  full-width/ligature/CJK text isn't NFKC-folded into spurious matches.
- New **detection rules** (surface the alert the user asked for): bidi controls,
  embedded ANSI/terminal escapes, broadened invisible-char usage. Homoglyph /
  mixed-script detection is a bigger piece (confusables map) — scope separately.
- `sanitize_for_display(text)` — strip ANSI + C0/C1 control chars, render
  invisibles/bidi as visible `<U+XXXX>` tokens. Apply at a **single chokepoint**
  that reaches render + cache + hook output.

## Key research / open questions (answer before building)

1. Where is the single sanitization chokepoint that covers render, cache-stored
   findings, AND hook stdout? `hook.py` is **standalone** (import-guards the
   package, mirrors constants like `_safe_name`) — so its output sanitization must
   be a mirrored inline helper, pinned by a `test_branding`/`test_hook` mirror
   test, OR sanitize at finding-creation/cache-write so the hook gets safe text
   for free from the cache. Decide which.
2. Sanitize `Finding.context` only, or `message` too? (engine-authored messages
   are mostly trusted; remote-engine messages may not be.)
3. FP cost of NFKC folding on real skills (emoji, accents, CJK, full-width)?
4. Homoglyph approach: full Unicode confusables/TR39 skeleton vs. a targeted
   Latin/Cyrillic/Greek subset? (Separate sub-task if heavy.)
5. Is `skillaudit.vercel.app` LLM-backed? If yes, file a service-side hardening
   note (treat skill text as data, not instructions; structured framing).
6. Does adding `sanitize.py` need the `install.sh` MODULES list + hooks update?
   (Yes — `tests/test_install_sync.py` enforces it.) Confirm at build time.

## Follow-on work this spins off

- Homoglyph / mixed-script detection (confusables) — likely its own task.
- Remote-engine (SkillAudit) prompt-injection hardening — service-side.
- Truncation / paraphrase / decomposition evasion fixtures (Nesbitt 2.30–2.32) —
  tracked in `task-skills-registry-threat-models.md` (Option 1); coordinate so the
  unicode fixtures and those evasion fixtures share one suite.

## Implementation (2026-06-26)

New authority `skillguard/sanitize.py` (stdlib-only), mirroring `mcp/secrets.py`:
- `fold_for_detection(text)` — strips invisibles/bidi + NFKC, but ONLY when the
  line already contains an invisible/bidi char (so benign emoji/accents/CJK/
  full-width are never re-normalized). `engines/local.py` now scans **raw OR
  folded**, so an obfuscated payload (e.g. a zero-width split of `curl`) is caught
  by the existing rules.
- `sanitize_for_display(text)` — strips ANSI escapes + C0/C1 controls and renders
  invisible/bidi code points as visible `<U+XXXX>`. Idempotent.

Detection: three high-severity `obfuscation` rules in `patterns.py` (invisible
char splitting an ASCII token; bidi override; ANSI escape byte), built from
explicit code points to keep source ASCII. `obfuscation` joins
`selection_manipulation` in seeing YAML frontmatter (`_FRONTMATTER_SCANNED_CATEGORIES`).

Display chokepoint: `scan.py::_sanitize_findings_for_display` defangs every
finding's `context`/`file` (and remote-engine `message`) in place after triage,
before cache + history DB + render — one place covers all three. `render/reports.py`
also defangs attacker-controlled target `name`/`path` at each print site. The
standalone `hook.py` mirrors `sanitize_for_display` as inline `_sanitize` (pinned
by `test_sanitize_mirrors_package`) and defangs the skill/server names it prints.

Tests: `tests/test_text_safety.py` (+ 2 in `test_hook.py`), all byte-exact.

## Completion criteria

- [x] Malicious fixtures CAUGHT: hidden `curl|bash` via single zero-width (both
      `obfuscation` and folded `shell_pipe`); a bidi Trojan-Source line; an
      ANSI-escape line — each flagged high (`test_text_safety.py`).
- [x] FP guard SILENT: a clean skill using legit emoji / accents / CJK / one
      decorative full-width heading yields zero findings of any category.
- [x] Output proven defanged: a `context` carrying ANSI is stripped and invisibles
      show as `<U+XXXX>` through the full pipeline (cache + render).
- [x] Hook stdout proven safe via an inline mirror + `test_sanitize_mirrors_package`
      and a subprocess test driving a malicious skill name.
- [x] **Mutation-proven**: each new rule, the fold step, the scan-chokepoint call,
      and the hook/render defangs were mutated → RED, reverted → GREEN.
- [~] `install.sh` MODULES updated (`sanitize.py` added). Version sync left GREEN at
      0.3.1 (all 4 files agree); a bump is a release-marker decision (it threads into
      the landing page + `--version` + 3 tests) deliberately deferred to release.

## Follow-ons still open

- Homoglyph / mixed-script (confusables / TR39) detection — separate task, as scoped.
- Remote SkillAudit prompt-injection hardening (gap 3) — service-side.
- A pure full-width payload with no invisible char is intentionally NOT folded
  (the documented FP trade-off); it is covered by the homoglyph follow-on.
