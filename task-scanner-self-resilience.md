# Task: Make SkillGuard itself resilient to prompt-injection & malformed-unicode

**Status:** research / design-only — DO NOT build until greenlit
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

## Completion criteria (for the FUTURE build)

- [ ] Malicious fixtures CAUGHT: hidden `curl|bash` via single zero-width; a bidi
      Trojan-Source line; an ANSI-escape line — each flagged with category+severity.
- [ ] FP guard SILENT: a clean skill using legit emoji / accents / CJK / one
      decorative full-width heading yields zero findings (per contribution contract).
- [ ] Output proven defanged: a `context` carrying ANSI cannot move the cursor /
      spoof output when rendered; invisibles show as `<U+XXXX>`.
- [ ] Hook stdout proven safe (mirror or cache-sourced), with a mirror test if
      `hook.py` gets an inline sanitizer.
- [ ] **Mutation-proven**: break each new rule / the fold step, confirm RED, revert.
- [ ] `install.sh` MODULES + version sync updated if a new module lands.
