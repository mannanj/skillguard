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
- **Any path by which a secret value (an MCP `env`/`headers` value) reaches a materialized surface, finding, cache file, or the history DB** — only variable/header names should ever be persisted
- An MCP config crafted to make discovery execute a server during a *static* scan (static scanning must never launch a server; only `--mcp-introspect` may)

Out of scope:

- False negatives in a single pattern (open a regular issue with the sample — pattern gaps are normal contributions, not vulnerabilities, unless they reflect a class-level evasion)
- Vulnerabilities in the optional third-party engines (report to Cisco/Snyk/SkillAudit directly)

## Design notes for reviewers

- The hook **fails closed**: a missing, corrupted, or unreadable cache entry blocks the skill rather than silently allowing it.
- Cache entries record the skill's `SKILL.md` mtime at scan time; if the skill is modified after its scan, the hook blocks until it is re-scanned. This check only covers skills in `~/.claude/skills/` — plugin-namespaced skills resolve to plugin cache directories the hook does not currently locate.
- The cache lives at `~/.claude/skillguard-cache/` with the user's permissions. An attacker with arbitrary write access to the user's home directory is outside the threat model (they could edit `settings.json` and remove the hook entirely).
- The scanner reads skill files with `errors="replace"` and never executes skill code.

### MCP scanning

- **Static MCP scanning never launches a server.** It reads config files and materializes a *redacted* surface. Live introspection (`--mcp-introspect`), which does connect to / launch a server, is strictly opt-in and clearly labeled — it carries the same "you are executing third-party code" risk as running the server normally.
- **Secret discipline.** Any value that could be a credential — an `env` value, a `headers` value, a credential-bearing launch argument (a bare credential-shaped token, a `--flag=VALUE`, or the value after a long credential flag like `--token VALUE`), or a credential-bearing URL query parameter — is read in memory only, to decide whether an inline literal secret is present. It is never written to the materialized surface, a finding message, the cache, or the history DB — only names are. Inline-secret findings name the variable/flag/param, never the value. Regression-tested (`tests/test_mcp_engine.py`, `tests/test_cli_mcp.py`) against real-config-shaped data with sentinels in every position. *Boundary:* a short value that is not credential-shaped and is passed as a bare positional argument with no credential flag is indistinguishable from an ordinary argument and is treated as scan surface — pass secrets via `env`/`${REF}`, which is always redacted.
- **The hook never crashes a tool call.** Its integration with the SkillGuard package (settings + activity log) is import-guarded; if the package can't be imported the hook still blocks/allows with a default `warn` MCP policy and no logging. Activity logging from the hook is best-effort and can never fail or delay a tool call.
- The configured MCP policy defaults to **`enforce`**: unscanned servers and critical/high verdicts block unless the user changes the policy, skips the server, or acknowledges the current risk. The dependency-light emergency fallback remains `warn` only when the hook cannot import the SkillGuard package. Plugin-namespaced tool-name matching in `enforce` mode is best-effort; `--skip-mcp` and `off` cover known host-mapping gaps.
- **Runtime coverage varies by host.** Claude Code can gate both skill invocations and MCP tools. The local installer registers an MCP PreToolUse hook for Codex, but Codex does not currently expose skill loading as a hook event. Repository adapters provide scan and review instructions and must not be described as automatic enforcement unless their host exposes an equivalent hook.
- MCP verdict caches record the source config file's mtime; editing a server's config triggers a re-scan requirement (TOCTOU guard), same as skills.
