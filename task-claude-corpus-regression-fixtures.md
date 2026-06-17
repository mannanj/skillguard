# Task: Claude corpus false-positive regression fixtures

**Status:** open
**Created:** 2026-06-16

## Problem

A fresh scan of the Claude skill set after reinstall found 28 active local-engine
findings across 7 skills. Several look like documentation or policy examples rather
than active malicious instructions.

Examples from the 2026-06-16 scan:

- `cloudflare`: reference docs mention `webhook.site`, `atob()`, `curl ... | sh`,
  `systemctl`, and IP-address limits.
- `prompt-engineering-skill`: security docs discuss jailbreak and prompt-injection
  examples.
- `security`: a rule about using OS keychains triggers keychain access detection.
- `sandbox-sdk`: Docker cleanup uses `rm -rf /var/lib/apt/lists/*`.
- `email-best-practices`: transactional email docs mention IP address/location.

These may be correct raw matches, but they need regression coverage before changing
heuristics.

## Goal

Build a small, versioned fixture set from representative real-world snippets so
SkillGuard can improve signal without weakening detection.

## Follow-up Work

1. Extract minimal snippets from the flagged Claude skills into `tests/fixtures/`.
2. Label each snippet as one of:
   - benign documentation
   - risky executable instruction
   - intentionally ambiguous
3. Add tests for local-engine behavior before changing patterns.
4. Tighten suppressions only where the fixture proves documentation context.
5. Keep active-command examples, executable shell, and direct agent instructions
   detectable.

## Acceptance Criteria

- Regression tests cover the 2026-06-16 corpus examples above.
- Benign docs can be suppressed or demoted without hiding executable attack strings.
- JSON reports still preserve enough context to audit suppressed/demoted findings.
- README guidance stays honest: pattern scanners flag appearances; users can triage
  reviewed false positives.
