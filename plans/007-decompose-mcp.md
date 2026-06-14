# Plan 007: Decompose mcp.py into a focused package

> **Executor instructions**: Large refactor — extract one concern at a time,
> suite green after each. Honor STOP conditions. Update `plans/README.md`.
> **Drift check first**: `git diff --stat c6e9d42..HEAD -- skillguard/mcp.py`.
> **Re-read `mcp.py` in full before starting** — the line numbers below are from
> the audit at `c6e9d42` and are *leads*; confirm each against the live file.

## Status

- **Priority**: P2
- **Effort**: L
- **Risk**: MED (819-line security-relevant module; mitigated by existing
  `test_mcp_engine.py`/`test_mcp_introspect.py` + plan 004)
- **Depends on**: 001, 002, 004
- **Category**: tech-debt
- **Planned at**: commit `c6e9d42`, 2026-06-13

## Why this matters

`mcp.py` is 819 lines spanning six concerns that are already comment-sectioned but
welded together. The dominant smells (each verified by the audit):

- **`analyze_mcp_config` is a 117-line god-function** (`mcp.py:470-586`) holding
  endpoint analysis, launch analysis, inline-secret scanning, env-exposure, and
  the unparsed-config fallback.
- **Inline-credential detection is implemented three times** (`redacted_args`
  ~`mcp.py:370-385`, the analysis arg-loop ~`mcp.py:547-567`, and ~8 copies of
  the `not _is_env_ref(x) and not _has_interpolation(x)` guard) — a security-
  relevant DRY hazard where the redactor and detector share regexes but can drift.
- **Launch parsing is re-done three ways** (`_runner_in` ~589, `_runner_package`
  ~608, `_docker_image` ~644), each re-splitting the launch string naively.
- **The one place that executes untrusted code** (`_introspect_stdio` ~709-729)
  is buried at the bottom of the file, making its lifecycle/cleanup hard to review.

Isolating these into a package has a security payoff: the module that launches
untrusted servers becomes ~120 lines with a single responsibility, so plan 008's
hardening is trivial to review and test.

## Target layout (from the structural audit — verify line ranges live)

```
skillguard/mcp/                 (convert mcp.py into a package; keep public API)
  __init__.py     ← re-export the names cli.py imports (see constraint below)
  model.py        ← McpServer dataclass (+ derived props)
  discovery.py    ← *_config_path, plugins_root, _read_json, _server_from_config,
                    _servers_from_mapping, discover_mcps, _discover_plugin_mcps,
                    _plugin_name_for   (split the 57-line discover_mcps into one
                    loader per source + a shared dedup/sort tail)
  secrets.py      ← all redaction regexes + _is_env_ref/_has_interpolation/
                    _is_safe_ref(new), looks_secretish, header helpers, ONE
                    unified arg classifier, redact_*, redacted_*, scan_url(new)
  launch.py       ← _RUNNERS + a single parse_launch()->LaunchInfo replacing the
                    three re-parsers (use shlex.split for quote-awareness)
  rules.py        ← LAUNCH_RULES/ENDPOINT_RULES tables + SUSPICIOUS_HOSTS
                    (table-driven detection instead of open-coded re.search)
  engine.py       ← analyze_mcp_config split into _endpoint_findings/
                    _launch_findings/_inline_secret_findings/_exposure_findings
                    + McpConfigEngine
  materialize.py  ← safe_name, materialize_surface, write_introspection_surface
  introspect.py   ← introspect, _jsonrpc, _INIT_PARAMS, _introspect_stdio,
                    _introspect_http, _resolve_env_refs, _parse_introspection
```

## Critical constraint — keep `install.sh` and curl-install in sync

`tests/test_install_sync.py` asserts every package module is listed in
`install.sh`'s remote-fetch loop (curl-installs fetch file-by-file). Converting
`mcp.py` into the `mcp/` **package** means the flat `for f in ...skillguard/*.py`
loop will no longer fetch `mcp/__init__.py`, `mcp/secrets.py`, etc. **Read
`tests/test_install_sync.py` first**, then update both `install.sh` (fetch the
package dir / each `mcp/*.py`) and the test's discovery to recurse into
sub-packages. Plan 002 already hit the flat version of this (adding `_util.py`
required an `install.sh` edit); a package conversion needs the loop generalized.

## Critical constraint — preserve the public API

`cli.py:46-53` imports from `skillguard.mcp`: `McpConfigEngine`, `discover_mcps`,
`introspect`, `materialize_surface`, `safe_name`, `write_introspection_surface`.
Tests import more (e.g. `test_mcp_engine.py`, `test_mcp_introspect.py` import
`analyze_mcp_config`, `McpServer`, redaction helpers, etc. — grep before moving).
**Converting `mcp.py` → `mcp/` package must keep every currently-imported name
re-exported from `skillguard/mcp/__init__.py`.** Run the grep below first and make
the re-export list cover all of it.

```
grep -rn "from skillguard.mcp import\|from skillguard import mcp\|mcp\.[A-Za-z_]" tests/ skillguard/
```

## Embedded sub-improvements

- **MCP-02 (secrets DRY)**: one `classify_args(args) -> list[ArgClass]` authority;
  redaction maps it to strings, analysis maps it to Findings. Add `_is_safe_ref`
  to collapse the doubled guard. Add a property-style test: anything
  `redacted_args` redacts, the analyzer flags, and vice-versa.
- **MCP-08 (URL DRY)**: one `scan_url(url) -> (redacted, secret_param_names, host,
  scheme, is_raw_ip)` computed once; redaction, materialization, and analysis read
  its result instead of re-parsing.
- **MCP-04 (table-driven rules)**: `LAUNCH_RULES`/`ENDPOINT_RULES` as data;
  complex rules (runner package, docker image) registered as callables.
- **MCP-06 (launch parser)**: single `parse_launch()` via `shlex.split`. NOTE:
  snapshot current findings on the test corpus FIRST — `shlex` changes
  tokenization edge cases vs `str.split`; the snapshot proves behavior preserved.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install | `pip install -e ".[dev]"` | exit 0 |
| MCP tests (after each step) | `python -m pytest tests/test_mcp_engine.py tests/test_mcp_introspect.py tests/test_cli_mcp.py -q` | all pass |
| Full suite | `python -m pytest -q` | all pass |
| Secret-leak guard | `python -m pytest tests/test_cli_mcp.py::test_secret_never_persisted_anywhere -q` | pass |
| API surface | (the grep above, then) `python -c "from skillguard.mcp import McpConfigEngine, discover_mcps, introspect, materialize_surface, safe_name, write_introspection_surface; print('ok')"` | `ok` |
| Lint/type | `ruff check skillguard && mypy skillguard` | exit 0 |

## Scope

**In scope**: converting `mcp.py` into the `mcp/` package above; the embedded DRY
unifications. **Out of scope**: changing detection severities/categories
(behavior must be identical — the corpus snapshot proves it); the introspection
*security* hardening (env minimization, SSRF guard, process lifecycle) — that is
plan 008, layered on top of the now-isolated `introspect.py`.

## Steps (one extraction at a time; MCP suite green after each)

1. Run the API-surface grep; write down the full re-export list.
2. Create the `mcp/` package; move `McpServer` → `mcp/model.py`; `__init__`
   re-exports everything. Verify suite green (this step alone should be a no-op to
   importers).
3. Extract `secrets.py` (unify the arg classifier + `scan_url`). Verify — esp. the
   secret-leak guard test.
4. Extract `launch.py` (`parse_launch`). Snapshot corpus findings before; compare
   after. Verify.
5. Extract `rules.py` (table-driven). Verify findings unchanged.
6. Extract `discovery.py` (one loader per source). Verify discovery tests.
7. Extract `engine.py` (split `analyze_mcp_config` into the four predicates +
   `McpConfigEngine`). Verify.
8. Extract `materialize.py` and `introspect.py`. Verify introspection tests.
9. Final: confirm `mcp.py` no longer exists as a single file (it's now `mcp/`),
   the API-surface check prints `ok`, full suite green.

## Done criteria

- [ ] `python -m pytest -q` all pass; `ruff check` + `mypy skillguard` exit 0.
- [ ] API-surface check prints `ok`; the leak-guard test passes.
- [ ] No file under `skillguard/mcp/` exceeds ~200 LOC.
- [ ] Detection output is identical to pre-refactor on the test corpus (snapshot
      compared in steps 4-5).
- [ ] `grep -rn "_is_env_ref(.*) and .*_has_interpolation" skillguard/mcp/`
      shows the guard collapsed into `_is_safe_ref` (≤1-2 sites).
- [ ] `plans/README.md` row for 007 updated.

## STOP conditions

- The secret-leak guard test (`test_secret_never_persisted_anywhere`) fails at
  ANY step — STOP immediately; a redaction regression is a security defect.
- The launch-parser corpus snapshot differs after switching to `shlex` — STOP;
  decide each delta explicitly with the maintainer before accepting it.
- An imported name can't be re-exported without a cycle — report it.

## Maintenance notes

- `introspect.py` is the only module that executes untrusted code — keep it small
  and dependency-isolated; plan 008 hardens it.
- `secrets.py` is the single authority for "what is a secret / how is it
  redacted" — any new redaction or detection rule goes there, not into `engine.py`.
