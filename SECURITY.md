# Security Policy

SkillGuard is a security tool, which makes its own security posture part of the product. If you find a way to bypass the hook, evade a detection engine, poison the scan cache, or otherwise defeat SkillGuard's protections, we want to hear about it — privately first.

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities or detection bypasses.**

- Preferred: open a [private security advisory](https://github.com/mannanj/skillguard/security/advisories/new) on GitHub.
- We aim to acknowledge reports within 72 hours and to ship a fix or public advisory within 30 days.

In-scope examples:

- Bypassing the PreToolUse block (running an unscanned skill without tripping exit 2)
- Cache poisoning (forging a "clean" cache entry a skill author could plant)
- TOCTOU windows beyond the documented plugin-skill limitation
- Code execution or path traversal in the scanner itself
- A malicious skill crafted to crash or hang the scanner (denial of scanning)

Out of scope:

- False negatives in a single pattern (open a regular issue with the sample — pattern gaps are normal contributions, not vulnerabilities, unless they reflect a class-level evasion)
- Vulnerabilities in the optional third-party engines (report to Cisco/Snyk/SkillAudit directly)

## Design notes for reviewers

- The hook **fails closed**: a missing, corrupted, or unreadable cache entry blocks the skill rather than silently allowing it.
- Cache entries record the skill's `SKILL.md` mtime at scan time; if the skill is modified after its scan, the hook blocks until it is re-scanned. This check only covers skills in `~/.claude/skills/` — plugin-namespaced skills resolve to plugin cache directories the hook does not currently locate.
- The cache lives at `~/.claude/skillguard-cache/` with the user's permissions. An attacker with arbitrary write access to the user's home directory is outside the threat model (they could edit `settings.json` and remove the hook entirely).
- The scanner reads skill files with `errors="replace"` and never executes skill code.
