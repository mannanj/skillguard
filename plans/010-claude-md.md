# Plan 010: Add CLAUDE.md for agent contributors

> **Executor instructions**: Write the guide, verify the facts it states against
> the live code, keep it short. Update `plans/README.md`. **Drift check first**:
> the architecture this documents settles in plans 005-007; do this LAST.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW (documentation only)
- **Depends on**: 005, 006, 007 (document the architecture after it settles)
- **Category**: docs
- **Planned at**: commit `c6e9d42`, 2026-06-13

## Why this matters

There is no `CLAUDE.md`/`AGENTS.md`, yet this project's whole domain is Claude
Code and it is explicitly oriented toward agent-executed plans. Without a guide,
every agent session must rediscover: the engine protocol/registry, the
secret-redaction discipline, the version-sync-across-files rule (there's a
`test_version_sync.py`), the hook's fail-closed-skills / configurable-MCP posture,
and the "add a detection pattern + fixture + false-positive guard" contribution
contract. The knowledge is scattered across `CONTRIBUTING.md`, `SECURITY.md`, and
module docstrings.

## Current state

- Rich human docs exist: `README.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  `docs/RELEASE-STRATEGY.md`, `docs/DEPLOYMENT.md`, plus `task-*.md` scratch files.
- Module docstrings are excellent sources of truth: `model.py:4-10` (shared
  types), `config.py:4-28` (settings precedence), `store.py:4-32` (design
  constraints incl. "no secrets, ever"), `hook.py:4-27` (the gate contract),
  `mcp.py` header (redaction discipline).
- `tests/test_version_sync.py` enforces version consistency; note where the
  version string lives (e.g. `cli.py:58 __version__`, `pyproject.toml:7`,
  `.claude-plugin/plugin.json`).

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Verify version sources | `python -m pytest tests/test_version_sync.py -v` | pass (tells you the synced files) |
| Verify build/test commands | `pip install -e ".[dev]" && python -m pytest -q` | exit 0 |

## Scope

**In scope**: create `CLAUDE.md` at the repo root. **Out of scope**: changing
`CONTRIBUTING.md` (link to it, don't duplicate it); restating the full README.

## Steps

### Step 1: Write `CLAUDE.md` covering

1. **One-line what/why** + the build/test/lint commands (`pip install -e
   ".[dev]"`, `python -m pytest -q`, and post-004: `ruff check`, `mypy skillguard`).
2. **Architecture** (post 005-007): the `Engine` protocol + `ENGINE_REGISTRY`
   (one place to add an engine), the module layout (`engines/`, `render/`,
   `mcp/`, `scan.py`, `cache.py`, `triage.py`, `model.py`, `config.py`,
   `store.py`, `hook.py`), and the `cli.py`-as-facade + re-export rule.
3. **Inviolable rules**:
   - *Secret redaction*: only redacted, model-shape data is ever persisted; raw
     args are scanned in memory only (cite `store.py:22-25`, `mcp/secrets.py`).
   - *Zero runtime dependencies*: core imports stdlib only; third-party engines
     are optional + import-guarded.
   - *Hook posture*: skills fail-closed; MCP policy is `off|warn|enforce` (cite
     `hook.py:5-27`); the hook must never crash a tool call.
   - *Severity ordering* lives only in `model.py` (`max_severity_of`/
     `worst_severity`); never re-derive it inline.
   - *Version sync*: bump every file `test_version_sync.py` checks together.
4. **Contribution contract**: adding a detection pattern requires a malicious
   fixture AND a false-positive guard (cite `CONTRIBUTING.md` + the
   `test_local_engine.py` pattern).
5. **Pointer to `plans/`**: how the improve-skill plans work and the drift-check
   discipline.

### Step 2: Verify every factual claim

Check each cited file:line and command is still accurate (the architecture
sections must match the post-006/007 layout). Run the version-sync test to list
the synced files correctly.

## Done criteria

- [ ] `CLAUDE.md` exists at the repo root and is < ~150 lines (a guide, not a book).
- [ ] Every command in it runs successfully; every cited file path exists.
- [ ] It accurately reflects the post-005/006/007 module layout (no references to
      the old monolithic `cli.py`/`mcp.py` structure).
- [ ] `plans/README.md` row for 010 updated.

## STOP conditions

- If 005/006/007 have NOT landed yet, STOP — documenting a moving architecture
  produces a wrong guide. Either wait or write only the stable sections (rules,
  commands, contribution contract) and mark the architecture section TODO.

## Maintenance notes

- Keep `CLAUDE.md` in sync when the engine set or module layout changes; it's the
  first thing an agent reads.
