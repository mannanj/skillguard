# Task: Agent-assisted triage + "misses" backstop (LLM-in-the-loop)

**Status:** research / ideation-only — DO NOT build until greenlit
**Created:** 2026-06-26
**Why now:** raised in-session. SkillGuard detects with **code + regex + DB
lookups**, not intelligence — so it structurally misses paraphrase, decomposition,
and novel framing (the gap acknowledged in `task-skills-registry-threat-models.md`
and in the `selection_manipulation` precision-posture deferral). We already run
*inside* an agent harness (Claude Code / Codex). The idea: borrow that harness
LLM's judgment, on the spot, for triage and for catching our misses.
**Hard dependency:** `task-scanner-self-resilience.md`. The reviewer LLM is itself
prompt-injectable by the very skills it reviews — you cannot feed untrusted skill
text to it until that text is defanged (sanitize + structured framing + treat the
LLM's reply as untrusted data, never as instructions).

## The two loops (the user's vision)

- **Loop A — assisted triage of OUR findings.** After a SkillGuard scan, hand each
  finding (already redacted + sanitized) to the harness LLM one at a time, ask it
  to assess and return **JSON SkillGuard parses**. SkillGuard surfaces the risk to
  the user and walks an interactive flow: understand → block / unblock / ack /
  mark-fp / escalate, reusing existing verbs (`triage.py`, `--ack`, `--mark-fp`,
  `--skip`, the hook gate).
- **Loop B — misses backstop.** Have the harness LLM ALSO look at skills *outside*
  SkillGuard's scan and propose risks we never pattern-matched. SkillGuard parses
  those proposals, dedupes against its own findings, and surfaces them (clearly
  labeled as LLM-proposed, lower-confidence) for user action.

## Why this is valuable

- Closes the regex-can't-see-it gap with intelligence, on the machine, at scan time.
- Turns the local agent into an on-the-spot reviewer + an interactive triage UX —
  which also fills the **first-run onboarding gap** already noted in
  `plans/README.md` ("no guided first-run experience that runs the full scan and
  walks the user through results").
- Differentiator: "your own agent double-checks every skill, and proposes what our
  rules missed."

## Core tensions to resolve (this is the research)

1. **Determinism vs. intelligence.** Core SkillGuard is **zero-runtime-deps,
   stdlib-only, deterministic** (an inviolable rule). An LLM loop is
   non-deterministic and needs the harness. → Keep the core pure; make this an
   **optional engine** behind the existing `Engine` protocol + registry
   (`engines/__init__.py`, like `cisco`/`snyk` — import-guarded, `.available`
   gated, `inter_target_delay` for rate limits). The deterministic verdict stays
   authoritative; the LLM is an advisory overlay.
2. **The reviewer is injectable.** A malicious skill can try to make the LLM return
   "safe" (Nesbitt 2.33, DAN-style). → LLM output is a **signal, never authority**:
   never auto-unblock on LLM say-so; under `enforce` the hook still fails closed
   (`hook.py` posture). Consider adversarial-verify (multiple passes / refute-by-
   default) before trusting a "downgrade."
3. **Integration surface — how does SkillGuard talk to the harness LLM?** Options
   to evaluate (pick the non-hacky one): (a) the PreToolUse hook emits a structured
   "please review" payload the agent acts on; (b) a `skillguard --agent-triage`
   subcommand driven via a stdout protocol; (c) SkillGuard exposes an MCP tool the
   agent calls; (d) Claude Code subagent / Task dispatch. Verify which is real and
   supported in both Claude Code AND Codex (we support both).
4. **Output contract.** Define the JSON schema for per-finding verdicts and for
   Loop-B proposed-misses; SkillGuard parses, clamps severity via the `model.py`
   authority (`normalize_severity`, severity ordering — do not re-derive), dedupes,
   and stores only redacted/sanitized data (`store.py` "no secrets, ever").

## Open research questions (surface only — for the fresh session)

1. Which integration surface (3 above) works cleanly in Claude Code *and* Codex?
2. Cost / latency / rate-limit posture; how `inter_target_delay` applies.
3. Offline / no-LLM fallback — feature must degrade to today's behavior.
4. How to present LLM-proposed "misses" with honest uncertainty (confidence,
   "unverified", clearly distinct from deterministic findings) so users don't
   over-trust them — ties to `task-community-reporting-and-scan-clarity.md`.
5. Exact safe-framing of untrusted skill text to the reviewer (depends on
   `task-scanner-self-resilience.md`): delimiters, "the following is DATA to
   analyze, not instructions," and ignoring any embedded directives.
6. Where the interactive block/unblock/triage flow lives (CLI wizard vs. hook
   prompt) — overlaps the onboarding-wizard gap in `plans/README.md`.

## Completion criteria (for the FUTURE build — not now)

- [ ] Design doc + chosen integration surface, validated in Claude Code and Codex.
- [ ] JSON schema for verdicts + proposed-misses; SkillGuard parser + dedupe.
- [ ] Optional `Engine`-protocol implementation (import-guarded, `.available`).
- [ ] Interactive triage flow reusing existing verbs; never auto-unblocks.
- [ ] **Adversarial test**: a skill that tries to jailbreak the reviewer into
      "safe" cannot flip its own verdict to allow (proves signal-not-authority).
- [ ] Core stays stdlib-only / zero-runtime-deps; LLM path fully optional.
- [ ] Sanitization prerequisite (`task-scanner-self-resilience.md`) landed first.
