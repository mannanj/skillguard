# CLAUDE.md — contributor guide for agents

SkillGuard is a **stdlib-only, multi-engine security scanner for Claude Code
skills and MCP servers**. It runs as a CLI and as a PreToolUse hook that gates
skill/MCP invocations. This file is the fast on-ramp; deeper rationale lives in
module docstrings and `CONTRIBUTING.md` / `SECURITY.md`. Read it before changing
code, and keep it in sync when the engine set or module layout changes.

## Landing page copy rule

No fluff. The Gandalf landing page should stay terse and factual: no filler
sections, no vague proof chips, no clever explanatory blocks, and no decorative
claims. Use concrete product truth, install actions, command docs, and factual
metadata only. Do not invent compatibility counts; only use numbers backed by
repo data or live metadata.

## Build / test / lint

A `.venv/` is checked in locally; prefix commands with `.venv/bin/` to use it.

```bash
pip install -e ".[dev]"                          # dev deps: pytest>=8, ruff, mypy
.venv/bin/python -m pytest -q                    # 205 tests, all must pass
.venv/bin/ruff check skillguard tests            # lint
.venv/bin/ruff format --check skillguard tests   # format
.venv/bin/mypy skillguard                        # typecheck (34 source files)
git config core.hooksPath .githooks               # one-time: enable pre-push gate
```

Those four commands (pytest + ruff check + ruff format + mypy) are the **DX
gates**; all four must stay green on every change. Python ≥ 3.10. Core has
**zero runtime dependencies** (`pyproject.toml` `dependencies = []`); the `cisco`
engine is an optional extra and is import-guarded.

## Architecture

`skillguard/cli.py` is a **thin facade**: it re-exports public names from the
sub-modules and owns `run_scan()` + `__version__`. `from skillguard.cli import …`
keeps working, but new code belongs in the focused module, not in `cli.py`.

Top-level package modules:

- `model.py` — shared types (`Finding`, `SkillInfo`), the `Engine` Protocol, and
  the **only** home for severity ordering (see Inviolable rules).
- `patterns.py` — `LOCAL_PATTERNS`, the regex detection rules + the `_p` builder.
- `branding.py` — naming authority (`APP_NAME`, `CACHE_DIR_NAME`, `DB_NAME`,
  `ENV_PREFIX`), all derived from `APP_NAME`.
- `config.py` / `paths.py` — settings precedence, cache-dir resolution.
- `discovery.py` / `scan.py` — find skills, run the engine pipeline, dedupe.
- `store.py` — SQLite history + activity store. **Stores only what it's given;
  callers must hand it redacted data.**
- `cache.py` / `triage.py` / `commands.py` / `args.py` / `_util.py` — verdict
  writers, false-positive triage, read subcommands, argparse, atomic-write util.
- `hook.py` — the standalone PreToolUse gate (see Hook posture).

Sub-packages:

- `engines/` — `LocalEngine`, `CiscoEngine`, `SkillAuditEngine`, `SnykEngine`,
  plus the registry (see below).
- `mcp/` — the MCP scanner, a package with a re-export facade in `__init__.py`
  (`__all__`). Modules: `model`, `discovery`, `secrets`, `launch`, `rules`,
  `materialize`, `engine`, `introspect`. **`secrets.py` is the single
  redaction/secret-detection authority** — new redaction/detection rules go
  there. **`introspect.py` is the ONLY module that executes untrusted code.**
- `render/` — `colors.py`, `reports.py`, `summary.py` (table/json/markdown/quiet
  output).

### Adding an engine

Engines satisfy the `@runtime_checkable` `Engine` Protocol in `model.py`
(`name`, `inter_target_delay`, `available`, `scan(target)`). To add one:
implement the class in `engines/`, then register it in **one place** —
`ENGINE_REGISTRY` in `skillguard/engines/__init__.py`. `_build_engines` and
`resolve_engine_names` are data-driven over that dict; `inter_target_delay` lets
a rate-limited remote engine throttle between targets (0.0 for local engines).

`McpConfigEngine` is **deliberately NOT in the registry** — it's the structural
MCP analyzer that `cli.py` appends only when MCP targets exist, never a
user-selectable engine.

## Inviolable rules

- **Secret redaction.** Raw env / headers / args / url values are scanned **in
  memory only**; only redacted, model-shape data is ever persisted (cache,
  history DB, materialized surfaces, finding messages). `mcp/secrets.py` is the
  authority; `store.py` stores "no secrets, ever" (its docstring). The MCP engine
  even re-scans raw literals in memory for blind-spots
  (`mcp/engine.py::_redaction_blindspot_findings`, via `secrets.redacted_literals`)
  without echoing them. Pinned by
  `tests/test_cli_mcp.py::test_secret_never_persisted_anywhere`.
- **Zero runtime dependencies.** Core imports stdlib only. Optional engines are
  import-guarded and gated on `.available`.
- **Severity ordering lives only in `model.py`** (`SEVERITY_ORDER`,
  `max_severity_of`, `worst_severity`, `normalize_severity`). Never re-derive
  "which severity is worse" or "unknown → medium" inline.
- **Hook posture (`hook.py:4-30` docstring).** Skills **fail CLOSED** (no scan,
  corrupted cache, or modified-since-scan → block; skipped → allow with a
  reminder). MCP policy is `off | warn | enforce`. The hook must never crash a
  tool call.
- **`hook.py` is standalone** and import-guards the package, so it
  **deliberately mirrors** branding/policy constants as inline literals
  (`CACHE_DIR`, `DB_NAME`, `MCP_POLICY_ENV`, `SETTINGS_NAME`, `_safe_name`, …).
  Do NOT "DRY" these into a `branding` import — the mirror is pinned by
  `tests/test_branding.py::test_hook_mirrors_branding` and
  `tests/test_hook.py::test_safe_name_mirrors_package`. When the package can't be
  imported, `_mcp_policy()` returns `(policy, degraded)` and reads policy
  standalone from `SKILLGUARD_MCP_POLICY` + `<CACHE_DIR>/_settings.json`, failing
  closed for `enforce`. Verdict resolution prefers exact/prefix and refuses loose
  matches under enforce (`find_mcp_verdict(token, *, strict=…)`,
  `MIN_LOOSE_TOKEN`, `MCP_GLOB_CAP`).
- **Version sync.** The version string is owned by `cli.py` (`__version__`) and
  must agree across `pyproject.toml`, `.claude-plugin/plugin.json`, and
  `.claude-plugin/marketplace.json` — bump all four together.
  `tests/test_version_sync.py` enforces it.
- **Install sync.** Every package module must appear in the `MODULES` list in
  `install.sh`, and every hook matcher in `hooks/hooks.json` must appear there
  too. Adding a new `skillguard/**.py` file without updating `install.sh` fails
  `tests/test_install_sync.py`.

## Contribution contract

Adding a detection pattern (see `CONTRIBUTING.md`) requires **both**: a malicious
fixture under `tests/fixtures/` that must be flagged with the right
category + severity, **and** a false-positive guard — an innocent look-alike that
must yield zero findings. `tests/test_local_engine.py` is the canonical example
of that pairing. (Patterns live in `skillguard/patterns.py`; `CONTRIBUTING.md`
still says `cli.py`, which only re-exports them.)

**Prove every test catches its bug:** before trusting a new test, mutate the
production code its assertion depends on, confirm RED, then revert and confirm
GREEN.

## Plans workflow

`plans/` holds the improve-skill roadmap (see `plans/README.md` for the table +
session log). Plans are agent-executed and may predate later refactors —
**re-verify every cited symbol/line against live code before following a plan
literally** (drift check). Update the plan's row and add a session-log entry when
you land one.
