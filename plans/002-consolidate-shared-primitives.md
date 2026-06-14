# Plan 002: Consolidate duplicated primitives into single authorities

> **Executor instructions**: Follow step by step. Run every verification command
> and confirm the expected result before the next step. Honor STOP conditions.
> Update this plan's row in `plans/README.md` when done unless a reviewer owns
> the index.
>
> **Drift check (run first)**:
> `git diff --stat c6e9d42..HEAD -- skillguard/cli.py skillguard/config.py skillguard/model.py`
> If any of those changed since `c6e9d42`, compare the "Current state" excerpts
> to the live code before editing; on a mismatch, STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW (behavior-preserving; covered by the 131-test suite + plan 001)
- **Depends on**: 001 (the characterization tests are the safety net)
- **Category**: tech-debt
- **Planned at**: commit `c6e9d42`, 2026-06-13

## Why this matters

Four primitives are each implemented two-to-four times, and several are the very
invariants the security hook trusts:

1. **Atomic JSON write** — byte-identical in `cli.py:663-667` and
   `config.py:70-72`. A durability fix to one (e.g. adding `fsync`) silently
   skips the other.
2. **Severity ranking** — `model.py` owns it (`SkillInfo.max_severity`,
   lines 62-66), but `cli.py:539` re-derives it inline and `cli.py:1346-1349`
   re-derives the cross-target reduction by hand. Three encodings of one order;
   the cache they write is what the hook gates on.
3. **Cache-dir literal** — `Path.home()/".claude"/"skillguard-cache"` is written
   out four times (`config.py:49`, `cli.py:60`, `hook.py:35`, `store.py:48`).
4. **UTC-now ISO timestamp** — `store._utcnow_iso()` (private) plus three inline
   `datetime.now(timezone.utc).isoformat()` copies in `cli.py` (565, 641, 678).

This plan makes each a single authority. It is intentionally low-risk and
mechanical — the high-leverage warm-up before the architectural changes (005-007).

## Current state

Verified excerpts (confirm these match before editing):

- `cli.py:663-667`:
  ```python
  def _atomic_write_json(path: Path, data: dict) -> None:
      """Write JSON via temp-file-then-rename so concurrent scans never leave a torn cache."""
      tmp = path.with_suffix(f".tmp.{os.getpid()}")
      tmp.write_text(json.dumps(data, indent=2))
      tmp.replace(path)
  ```
  Called at `cli.py:525, 547, 659, 688`.
- `config.py:67-72`:
  ```python
  def save_settings(settings: dict[str, Any], cache_dir: Path | None = None) -> None:
      path = settings_path(cache_dir)
      path.parent.mkdir(parents=True, exist_ok=True)
      tmp = path.with_suffix(f".tmp.{os.getpid()}")
      tmp.write_text(json.dumps(settings, indent=2))
      tmp.replace(path)
  ```
- `config.py:48-49`: `def default_cache_dir() -> Path: return Path.home() / ".claude" / "skillguard-cache"`.
- `cli.py:60`: `CACHE_DIR = Path.home() / ".claude" / "skillguard-cache"`.
- `model.py:61-66`:
  ```python
  @property
  def max_severity(self) -> str:
      active = self.active_findings
      if not active:
          return "clean"
      return min(active, key=lambda f: f.sort_key()).severity
  ```
- `cli.py:539`: `cache["max_severity"] = min(active, key=lambda f: f.sort_key()).severity if active else "clean"`
- `cli.py:1346-1349`:
  ```python
  worst = "clean"
  for t in targets:
      if SEVERITY_ORDER.get(t.max_severity, 99) < SEVERITY_ORDER.get(worst, 99):
          worst = t.max_severity
  ```
- `store.py:51-52`: `def _utcnow_iso() -> str: return datetime.now(timezone.utc).isoformat()`

**Hard constraints the tests impose** (both verified — do not break them):

- `tests/test_cache.py:20` does `from skillguard.cli import ... _atomic_write_json`,
  and calls it directly (lines 120, 133-134). **The name `cli._atomic_write_json`
  must remain importable and callable** with the same signature.
- `tests/test_triage.py:39` and `tests/test_cache.py:27` do
  `monkeypatch.setattr(cli, "CACHE_DIR", d)`. **`cli.CACHE_DIR` must remain a
  mutable module-level attribute**, and all path helpers (`cache_path_for`,
  `db_path`, `triage_path`) must keep reading that module global so the
  monkeypatch still redirects them.
- `skillguard/hook.py` is **import-guarded** (`hook.py:41-46`, `_HAVE_PKG`): it
  must work even when the package can't be imported. Its `CACHE_DIR` literal
  (`hook.py:35`) is a deliberate standalone fallback. **Do NOT change hook.py in
  this plan.** Its duplication is intentional resilience, not an accident.
- `store.py` documents (lines 30-31) that it "imports nothing from `cli`" and
  takes plain values — keep store dependency-light. **Do NOT change store.py in
  this plan** (its `default_db_path`/`_utcnow_iso` are addressed later if at all;
  they are not on a hot path).

Only `line 1300` in cli.py uses `datetime.now(timezone.utc)` with `.strftime()`
(a display string, not ISO) — **leave line 1300 unchanged.** Only the three
`.isoformat()` sites (565, 641, 678) are in scope for the time helper.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install | `pip install -e ".[dev]"` | exit 0 |
| Full suite | `python -m pytest -q` | all pass |
| Targeted | `python -m pytest tests/test_cache.py tests/test_triage.py tests/test_config.py -v` | all pass |
| Dup check | `grep -rn "with_suffix(f\".tmp" skillguard/` | exactly ONE match (in `_util.py`) |

(Use `.venv/bin/python -m pytest` if `python` isn't the venv.)

## Scope

**In scope**:
- `skillguard/_util.py` (create)
- `skillguard/model.py` (modify — add two functions, delegate the property)
- `skillguard/cli.py` (modify — import + replace duplicated bodies/call sites)
- `skillguard/config.py` (modify — `save_settings` uses the shared writer)

**Out of scope** (do NOT touch):
- `skillguard/hook.py` — intentional standalone fallback (see constraints above).
- `skillguard/store.py` — keep dependency-light; not on a hot path.
- The `CACHE_DIR` literal in hook.py and the `default_db_path` in store.py — they
  stay as-is; this plan only de-dups the *package-internal, non-guarded* copies.

## Git workflow

- Branch `refactor/improve-foundation` (continue from plan 001's branch if you're
  already on it).
- Commit message e.g. `Consolidate atomic-write, severity, and time helpers into single authorities`.
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Create `skillguard/_util.py`

Stdlib-only shared helpers, importing nothing from the rest of the package (so it
never creates a cycle and any module may use it). Match the repo's file header
(SPDX line + copyright — copy from the top of `config.py:1-3`).

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Small dependency-free helpers shared across the package (atomic IO, time).

Imports nothing from the rest of ``skillguard`` so it stays safe to import from
any module without risking a circular import.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON via temp-file-then-rename so concurrent writers never leave a torn file."""
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
```

**Verify**: `python -c "from skillguard._util import atomic_write_json, utcnow_iso; print('ok')"` → `ok`.

### Step 2: Add severity authorities to `model.py`

Add two module-level functions and make the property delegate. Place them after
the `SEVERITY_ORDER` constant (after line 18) or after the dataclasses — keep
`SEVERITY_ORDER`/`Finding` defined before they're referenced.

```python
def max_severity_of(findings: "Iterable[Finding]") -> str:
    """Worst (lowest sort_key) severity among findings, or 'clean' if none."""
    active = [f for f in findings if not f.triaged_fp]
    if not active:
        return "clean"
    return min(active, key=lambda f: f.sort_key()).severity


def worst_severity(severities: "Iterable[str]") -> str:
    """Worst severity among a sequence of severity strings, 'clean' if all clean/empty."""
    worst = "clean"
    for s in severities:
        if SEVERITY_ORDER.get(s, 99) < SEVERITY_ORDER.get(worst, 99):
            worst = s
    return worst
```
Add `Iterable` to the typing import (`from typing import Any, Iterable, Optional`).
Then change `SkillInfo.max_severity` (lines 61-66) to delegate:
```python
    @property
    def max_severity(self) -> str:
        return max_severity_of(self.findings)
```
Note `max_severity_of` filters `triaged_fp` itself, so passing `self.findings`
(not `self.active_findings`) preserves identical behavior.

**Verify**: `python -m pytest tests/test_triage.py tests/test_cache.py -q` → all pass.

### Step 3: Rewire `cli.py` to the shared authorities

Make these edits in `cli.py`:

1. **Replace the local atomic-write definition** (lines 663-667) with an alias
   import that preserves the name for callers and tests. Near the other imports
   (after line 54), add:
   ```python
   from skillguard._util import atomic_write_json as _atomic_write_json, utcnow_iso
   from skillguard.model import SEVERITY_ORDER, Finding, SkillInfo, max_severity_of, worst_severity
   ```
   (merge the `model` import with the existing one on line 54). Then **delete**
   the `def _atomic_write_json(...)` block at lines 663-667. The four existing
   call sites (`525, 547, 659, 688`) keep working via the alias, and
   `from skillguard.cli import _atomic_write_json` still resolves.
2. **CACHE_DIR from config** — change line 60 to:
   ```python
   CACHE_DIR = config.default_cache_dir()
   ```
   (It stays a module global, so `monkeypatch.setattr(cli, "CACHE_DIR", ...)`
   still works; the value is identical.)
3. **Severity reuse** — change line 539 to:
   ```python
   cache["max_severity"] = max_severity_of(active)
   ```
   and replace the loop at 1346-1349 with:
   ```python
   worst = worst_severity(t.max_severity for t in targets)
   ```
4. **Time helper** — replace the three `datetime.now(timezone.utc).isoformat()`
   at lines 565, 641, 678 with `utcnow_iso()`. **Leave line 1300 unchanged** (it
   uses `.strftime(...)`, a display string).

**Verify**: `python -m pytest -q` → all pass. Then
`python -c "from skillguard.cli import _atomic_write_json; print('alias ok')"` → `alias ok`.

### Step 4: `config.save_settings` uses the shared writer

In `config.py`, replace the manual tmp-rename in `save_settings` (lines 70-72)
with the shared helper:
```python
from skillguard._util import atomic_write_json   # add near the top imports
...
def save_settings(settings: dict[str, Any], cache_dir: Path | None = None) -> None:
    path = settings_path(cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, settings)
```
Update the module docstring note (config.py:26-27) from "imports nothing from the
rest of the package" to "imports only the dependency-free `_util` helper from the
package" — keep it accurate.

**Verify**: `python -m pytest tests/test_config.py -q` → all pass.

## Test plan

- No new test files are required (the existing suite + plan 001 cover these
  paths: `test_cache.py` for atomic write, `test_triage.py`/`test_cache.py` for
  severity in the rewritten cache, `test_config.py` for settings, plan 001's
  renderer/scan tests for `max_severity`).
- Optionally add to `tests/test_cache.py` a one-line assertion that
  `cli._atomic_write_json is skillguard._util.atomic_write_json` to lock the
  aliasing — nice-to-have, not required.
- Verification: `python -m pytest -q` → all pass, same count as after plan 001.

## Done criteria

ALL must hold:

- [ ] `python -m pytest -q` exits 0 (same passed count as end of plan 001).
- [ ] `grep -rn "with_suffix(f\".tmp" skillguard/` returns exactly ONE line
      (inside `skillguard/_util.py`).
- [ ] `grep -rn "min(active, key=lambda f: f.sort_key()).severity" skillguard/`
      returns ONE line (inside `skillguard/model.py`) — cli.py no longer re-derives it.
- [ ] `python -c "from skillguard.cli import _atomic_write_json"` succeeds.
- [ ] `git status` shows changes only in `_util.py` (new), `model.py`, `cli.py`,
      `config.py` — NOT `hook.py` or `store.py`.
- [ ] `plans/README.md` status row for 002 updated.

## STOP conditions

Stop and report if:

- The "Current state" excerpts don't match live code (drift).
- After Step 3, `test_cache.py` or `test_triage.py` fails on the `CACHE_DIR`
  monkeypatch — it means a path helper stopped reading the module global; report
  rather than working around it.
- Removing `_atomic_write_json` breaks an import you didn't anticipate (grep
  `_atomic_write_json` across `tests/` and `skillguard/` first — you should find
  only `cli.py` and `tests/test_cache.py`).
- A change to `config.py` introduces a circular import (`config` → `_util` →
  must NOT import `config`/`cli`/`store`).

## Maintenance notes

- `_util.py` is the home for future dependency-free helpers; resist putting
  domain logic there.
- `store._utcnow_iso` and `store.default_db_path` are intentionally left as
  separate copies in this plan to keep `store` import-light; a later plan may
  have store delegate to `_util`/`config` *if* the dependency direction is
  reviewed and accepted. Note this so it isn't mistaken for an oversight.
- After plan 005 (engine protocol) and 006 (cli split), `max_severity_of` /
  `worst_severity` should be the only place severity ordering is computed — a
  reviewer should reject any new inline `min(..., key=sort_key)` or
  `SEVERITY_ORDER.get(...)` outside `model.py`.
