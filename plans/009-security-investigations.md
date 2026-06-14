# Plan 009: Security posture investigations (hook fail-open, cache DoS, redaction blind spot, token match)

> **Executor instructions**: This is an **investigate-then-fix** plan, not a
> blind-fix plan. Each item: first write a characterization test that
> demonstrates the current behavior, then make the maintainer-approved change,
> then prove it with the test. Several items are security trade-offs the
> maintainer must decide — surface them, don't unilaterally flip them. Honor STOP
> conditions; update `plans/README.md`. **Drift check first**:
> `git diff --stat c6e9d42..HEAD -- skillguard/hook.py skillguard/mcp.py`.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (changes touch the security-critical hook and redaction paths)
- **Depends on**: 001
- **Category**: security
- **Planned at**: commit `c6e9d42`, 2026-06-13

## Why this matters

Four findings on the security-critical paths. Two are clear robustness fixes; two
are posture trade-offs the maintainer should decide consciously. All verified by
reading.

## Items

### 009-A — Hook fails OPEN for MCP when the package can't import (`hook.py:69-75`)
- **Current**: if `from skillguard import config, store` fails
  (`hook.py:41-46`, `_HAVE_PKG=False`), `_mcp_policy()` returns `"warn"`
  (non-blocking) regardless of the operator's configured `enforce`. Skills
  correctly stay fail-**closed** (`hook.py:112-130`). So a partial install or a
  syntax error in `config.py`/`store.py` silently downgrades MCP `enforce` to
  `warn` — MCP calls that should block are allowed.
- **Decision needed**: should `enforce` mean enforce even when the package is
  unimportable? At minimum, emit a loud stderr notice on import failure so the
  degradation is visible. Consider fail-closed for `enforce` specifically.
- **Test**: simulate import failure (monkeypatch the import / break sys.path) and
  assert the chosen behavior.

### 009-B — Per-call cache glob has no file-count cap (`hook.py:178-207`)
- **Current**: `find_mcp_verdict` runs on **every** `mcp__*` tool call and
  iterates `sorted(MCP_CACHE_DIR.glob("*.json"))`, reading+parsing each (512KB
  per-file guard exists at `hook.py:194`; no cap on file *count*). Thousands of
  small JSON files in the cache dir slow every tool call (latency-tail DoS).
- **Fix**: try the expected filename(s) first (the hook knows candidate
  `match_tokens` shapes via `safe_name`); fall back to the glob only on miss, and
  bound it with a file-count cap (mirror the `cap=4000` pattern in
  `mcp.py` `_discover_plugin_mcps`). `log()` when the cap is hit.
- **Test**: drop N>cap files; assert lookup stays bounded and still resolves a
  known verdict by expected filename.

### 009-C — Redaction can hide malware from the content engines (`mcp.py:318-328`, `redact_arg` ~346-357)
- **Current**: `looks_secretish` redacts any `[A-Za-z0-9_\-.=+]{20,}` arg (after
  excluding paths/URLs/prose/flags) to `<redacted-literal>` in `command.txt`
  **before** `LocalEngine` scans it. A long base64-ish *malicious* token (e.g.
  `node -e "<20+ char base64 payload>"`) could be redacted away, so the
  obfuscation/exec detector never sees it. Redaction (for secrets) can suppress an
  attack signal.
- **Investigate + fix**: pin current behavior first. Then ensure the content/
  detection engines evaluate the **raw, in-memory** arg for attack patterns before
  redaction is applied for disk — without ever writing the raw secret to disk
  (the secret-never-leaks invariant is heavily tested and must hold). Tighten the
  heuristic; do not loosen redaction.
- **Test**: a `node -e "<20+char base64>"` arg must still produce the
  `mcp_inline_exec`/obfuscation finding AND must not leak the literal to disk.

### 009-D — Loose MCP token match can mis-attribute a verdict (`hook.py:178-207`, esp. 203-205)
- **Current**: `loose = ("_"+t+"_") in ("_"+server_part+"_") or server_part == t`
  + longest-match. A short token or names like `api` vs `api-prod` can match the
  wrong verdict — under `enforce`, a risky/unscanned server could resolve to a
  *different* server's clean verdict (fail-open).
- **Investigate + fix**: prefer exact/prefix match; only fall back to loose when
  no exact candidate exists; require a minimum token length for loose; on
  ambiguity under `enforce`, resolve toward "unscanned" (safe direction).
- **Test**: two verdicts (`api` clean, `api-prod` unscanned); a
  `mcp__api-prod__x` call under enforce must NOT resolve to `api`'s clean verdict;
  and a legitimate prefix case must still resolve.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install | `pip install -e ".[dev]"` | exit 0 |
| Hook tests | `python -m pytest tests/test_hook.py -v` | all pass |
| MCP tests | `python -m pytest tests/test_mcp_engine.py tests/test_cli_mcp.py -v` | all pass |

## Scope

**In scope**: `skillguard/hook.py` (A, B, D), `skillguard/mcp.py` or `mcp/`
(C), and tests in `tests/test_hook.py` / `tests/test_mcp_engine.py`.
**Out of scope**: the introspection hardening (plan 008); broad redaction-engine
redesign — make the minimal, test-proven change.

## Done criteria

- [ ] Each item has a test demonstrating the BEFORE behavior and the AFTER fix.
- [ ] `python -m pytest -q` all pass; the secret-leak guard
      (`test_cli_mcp.py::test_secret_never_persisted_anywhere`) still passes (esp. for C).
- [ ] 009-A's posture decision is recorded in the PR description (and CLAUDE.md
      via plan 010).
- [ ] `plans/README.md` row for 009 updated.

## STOP conditions

- Any change to redaction (C) that causes the secret-leak guard to fail — STOP
  immediately; that's a security regression.
- Tightening token match (D) turns currently-resolving legitimate servers into
  "unscanned" in a way that floods users with nudges — confirm the prefix case
  still resolves before shipping; if there's tension, surface it to the maintainer.

## Maintenance notes

- A/D are about what `enforce` *means* on the degraded/ambiguous paths — keep the
  documented hook contract (`hook.py:5-27`) in sync with whatever is decided.
- C is the subtle one: redaction protects secrets but must never blind the
  scanner; the invariant is "raw args are scanned in memory, only redacted forms
  reach disk."
