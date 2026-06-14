# Plan 005: Engine protocol + registry (the reusability centerpiece)

> **Executor instructions**: Step by step; verify each step; honor STOP
> conditions; update `plans/README.md`. **Drift check first**:
> `git diff --stat c6e9d42..HEAD -- skillguard/cli.py skillguard/mcp.py skillguard/model.py`.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (changes how engines are registered and dispatched; covered by
  plan 001 + existing engine tests)
- **Depends on**: 001 (tests), 002 (shared severity helpers + `_util`)
- **Category**: tech-debt
- **Planned at**: commit `c6e9d42`, 2026-06-13

## Why this matters

There are **five engines** —
`LocalEngine` (`cli.py:218`), `CiscoEngine` (`cli.py:264`), `SkillAuditEngine`
(`cli.py:312`), `SnykEngine` (`cli.py:421`), `McpConfigEngine` (`mcp.py:657`) —
coupled only by an informal duck-typed convention (`name: str`, `scan(target) ->
list[Finding]`). There is **no base class, ABC, or Protocol**. Consequences,
all verified:

- Engine registration lives in **three disjoint places**: the `if/elif` ladder in
  `_build_engines` (`cli.py:1105-1130`), the hard-coded `["local","cisco",
  "skillaudit","snyk"]` list for `--engines all` (`cli.py:1244`), and the
  separate `McpConfigEngine` append (`cli.py:1263-1266`). Adding an engine means
  editing all three with no compiler check.
- A per-engine policy leaks into the dispatcher: `if engine.name == "skillaudit":
  time.sleep(SKILLAUDIT_DELAY)` (`cli.py:1321-1322`).
- Each engine re-implements a normalize-and-swallow pattern (lowercase severity →
  clamp unknown to `medium` → build `Finding` → `except Exception: append info
  engine_error`). See `CiscoEngine:288-306`, `SkillAuditEngine:362-376`+`408-414`,
  `SnykEngine:451-461`+`477-483`.

This plan introduces a real `Engine` protocol, a single registry, and shared
normalization helpers — the heart of the "more reusable, modular" goal. It makes
engines genuinely pluggable: one place to register, one contract to satisfy.

## Current state

- `cli.py:1105-1130` `_build_engines` — `if/elif` over engine names; `local` and
  `skillaudit` always added; `cisco`/`snyk` gated on `.available`; unknown →
  `print(...); sys.exit(1)`.
- `cli.py:1244` — `engine_names = ["local","cisco","skillaudit","snyk"] if
  args.engines == "all" else [...]`.
- `cli.py:1263-1266` — `if mcp_targets: engines.append(McpConfigEngine());
  engine_names_used.append("mcp")`.
- `cli.py:1319-1322` — dispatch loop with the `skillaudit` sleep hack.
- `model.py` — the natural home for the `Engine` protocol and `normalize_severity`
  (it already owns `Finding`/`SEVERITY_ORDER`; after plan 002 it also owns
  `max_severity_of`/`worst_severity`).
- Engine classes currently live in `cli.py` (4) and `mcp.py` (1). This plan
  introduces the protocol/registry/helpers but **keeps the engine classes where
  they are** — physically moving them into an `engines/` package is plan 006's
  job, to keep this diff focused.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install | `pip install -e ".[dev]"` | exit 0 |
| Tests | `python -m pytest -q` | all pass |
| Engine tests | `python -m pytest tests/test_local_engine.py tests/test_skillaudit_engine.py tests/test_mcp_engine.py tests/test_build_engines.py -v` | all pass |
| Typecheck (if 004 landed) | `mypy skillguard` | exit 0 |

## Scope

**In scope**: `skillguard/model.py` (add `Engine` Protocol +
`normalize_severity` + optional `finding_from_mapping`), `skillguard/cli.py`
(registry + rewrite `_build_engines` + dispatch; each engine gains
`available`/`inter_target_delay` attributes; engines use the shared normalizer),
`skillguard/mcp.py` (`McpConfigEngine` declares conformance), and tests.
**Out of scope**: moving engine classes into separate files (plan 006); changing
the cache schema (plan 006); changing detection rules.

## Steps

### Step 1: Define the `Engine` protocol + `normalize_severity` in `model.py`

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Engine(Protocol):
    name: str
    available: bool
    inter_target_delay: float
    def scan(self, target: "SkillInfo") -> list["Finding"]: ...

def normalize_severity(sev: str) -> str:
    s = (sev or "").lower()
    return s if s in SEVERITY_ORDER else "medium"
```
Optionally add `finding_from_mapping(engine, mapping, *, key_aliases)` capturing
the shared "lowercase severity, clamp, pull category via fallbacks, build
Finding" pattern — only if you can make it cover all four engines without
changing which key wins (each has subtly different fallbacks: `code`/`type` vs
`rule`/`ruleId`). If unifying risks changing outputs, keep per-engine field
extraction and only share `normalize_severity`.

**Verify**: `python -c "from skillguard.model import Engine, normalize_severity; print('ok')"`.

### Step 2: Give every engine the protocol attributes

Add `available = True` (class attr) and `inter_target_delay = 0.0` to
`LocalEngine`, `SkillAuditEngine` (set `inter_target_delay = SKILLAUDIT_DELAY`),
and `McpConfigEngine`. `CiscoEngine`/`SnykEngine` already compute `.available`;
ensure it's an attribute/property usable uniformly. Replace each engine's inline
severity-clamp with `normalize_severity(...)`.

**Verify**: `python -m pytest tests/test_local_engine.py tests/test_skillaudit_engine.py tests/test_mcp_engine.py -q`.

### Step 3: Introduce `ENGINE_REGISTRY` and rewrite `_build_engines`

In `cli.py`:
```python
ENGINE_REGISTRY: dict[str, Callable[[], Engine]] = {
    "local": LocalEngine,
    "cisco": CiscoEngine,
    "skillaudit": SkillAuditEngine,
    "snyk": SnykEngine,
}
```
Rewrite `_build_engines` to iterate the requested names: unknown name →
`raise ValueError` (the caller maps it to the stderr+exit, OR keep `sys.exit(1)`
here but make `--engines all` use `list(ENGINE_REGISTRY)`). Instantiate, check
`.available`, collect skip-reasons into the returned tuple (caller prints).
`--engines all` (`cli.py:1244`) becomes `list(ENGINE_REGISTRY)`.

Keep the `McpConfigEngine` append target-gated (it must only run when MCP targets
exist — it is a no-op for skills, `mcp.py:667-668`, so appending it is harmless,
but preserve current behavior of appending only when `mcp_targets`).

**Verify**: `python -m pytest tests/test_build_engines.py -q` (plan 001's
selector tests, including unknown→exit 1, must still pass).

### Step 4: Move the per-engine delay out of the dispatcher

Replace `if engine.name == "skillaudit": time.sleep(SKILLAUDIT_DELAY)`
(`cli.py:1321-1322`) with a generic
`if engine.inter_target_delay and i < total - 1: time.sleep(engine.inter_target_delay)`.

**Verify**: `python -m pytest -q` all pass.

## Test plan

- Extend `tests/test_build_engines.py`: assert `list(ENGINE_REGISTRY)` ==
  expected names; assert a registered engine instance satisfies
  `isinstance(x, Engine)` (runtime_checkable); assert `--engines all` resolves to
  the registry keys.
- Add a test that an engine with `inter_target_delay > 0` is honored generically
  (you can monkeypatch a tiny fake engine into the registry and assert dispatch
  doesn't special-case by name).
- Existing engine tests must remain green (behavior preserved).

## Done criteria

- [ ] `python -m pytest -q` all pass; `mypy skillguard` exit 0 (if 004 landed).
- [ ] `grep -n "engine.name == \"skillaudit\"" skillguard/cli.py` returns nothing.
- [ ] `grep -n "\\[\"local\", \"cisco\", \"skillaudit\", \"snyk\"\\]" skillguard/cli.py`
      returns nothing (the `all` list is now `list(ENGINE_REGISTRY)`).
- [ ] Adding a new engine requires editing exactly ONE place (the registry) plus
      the engine class — demonstrate in the PR description.
- [ ] `plans/README.md` row for 005 updated.

## STOP conditions

- A shared `finding_from_mapping` changes which finding fields appear for any
  engine (compare `test_skillaudit_engine.py`/`test_mcp_engine.py` outputs before
  and after) — back out the unification and keep only `normalize_severity` shared.
- Making `McpConfigEngine` part of the registry causes it to run on skill targets
  and emit findings — keep it target-gated.

## Maintenance notes

- After this lands, plan 006 physically moves the four cli engines into
  `skillguard/engines/{local,cisco,skillaudit,snyk}.py` and `McpConfigEngine`
  stays in the mcp package (plan 007); the registry then imports them. Keep the
  registry as the single source of truth for "what engines exist."
- The `Engine` protocol is the contract for any future engine (e.g. a Semgrep or
  custom-rules engine) — document it in CLAUDE.md (plan 010).
