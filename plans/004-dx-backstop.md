# Plan 004: DX backstop — ruff + mypy + pre-commit + CI gates

> **Executor instructions**: Step by step; verify each step; honor STOP
> conditions; update `plans/README.md`. **Drift check first**:
> `git diff --stat c6e9d42..HEAD -- pyproject.toml .github/workflows/ci.yml`.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW (additive tooling; the only source edits are whatever the initial
  lint/type pass forces, which should be small and reviewed)
- **Depends on**: 001
- **Category**: dx
- **Planned at**: commit `c6e9d42`, 2026-06-13

## Why this matters

There is **no linter, formatter, or type checker** anywhere — no `ruff`/`flake8`/
`mypy`/`black`/pre-commit config, and CI runs only `pytest -v` + a CLI smoke
test. For a security tool processing untrusted input, the missing type checker is
the sharpest gap: the code is heavily annotated (`from __future__ import
annotations`, `Optional[...]`, dataclasses) but nothing verifies those
annotations. The big refactors (005-007) split a 1383-line and an 819-line module
— doing that without a mechanical lint/type net is needlessly risky. Install the
net **before** the decompositions.

## Current state

- `pyproject.toml` has only `[build-system]`, `[project]`,
  `[tool.hatch.build.targets.wheel]`, and `[tool.pytest.ini_options]` — no
  `[tool.ruff]`/`[tool.mypy]`. `dev` extra is `["pytest>=8"]`.
- `.github/workflows/ci.yml`: matrix `os: [ubuntu, macos] × python: ["3.10","3.13"]`,
  steps = install + `pytest -v` + smoke test. No lint/typecheck/coverage.
- `pyproject.toml` classifiers advertise 3.10–3.14; CI tests only 3.10 + 3.13.
- Core is zero-dependency; `from __future__ import annotations` is used in every
  module (so mypy should run clean-ish on annotations-as-strings).

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install dev | `pip install -e ".[dev]"` | exit 0 |
| Lint | `ruff check skillguard tests` | exit 0 after fixes |
| Format check | `ruff format --check skillguard tests` | exit 0 |
| Typecheck | `mypy skillguard` | exit 0 (start lenient) |
| Tests | `python -m pytest -q` | all pass |

## Scope

**In scope**: `pyproject.toml` (add `[tool.ruff]`, `[tool.mypy]`, extend `dev`
extra), `.github/workflows/ci.yml` (add a lint+typecheck job; optionally broaden
matrix + add coverage), `.pre-commit-config.yaml` (create), and **minimal**
source edits required to pass the initial lint/type pass.
**Out of scope**: large refactors to satisfy strict mypy — start lenient and
ratchet. Do not enable `--strict` in this plan. Do not reformat the whole tree in
a way that buries the refactor diffs of 005-007 — agree the format config now,
apply `ruff format` once, in its own commit.

## Steps

### Step 1: Add ruff + mypy config to `pyproject.toml`

Add (tune line-length to the codebase; it uses long lines — `line-length = 100`
or `120` to avoid a massive reflow):
```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]  # pyflakes, pycodestyle, isort, pyupgrade, bugbear
ignore = ["E501"]  # don't fight existing long lines; reflow opportunistically

[tool.mypy]
python_version = "3.10"
ignore_missing_imports = true   # cisco/skill_scanner optional deps
warn_unused_ignores = true
# start lenient; ratchet later:
check_untyped_defs = true
```
Extend the dev extra: `dev = ["pytest>=8", "ruff", "mypy"]`.

**Verify**: `ruff check skillguard tests` runs (may report findings) and
`mypy skillguard` runs.

### Step 2: Fix the initial findings (minimal, reviewed)

Run `ruff check --fix` for safe autofixes (imports sorting, pyupgrade). Manually
resolve real issues ruff/mypy surface — expect: unused imports, possibly real
`Optional` handling gaps (those are the point — fix them, don't `# type: ignore`
them). Keep edits minimal and behavior-preserving; the test suite must stay green
after each fix.

**Verify**: `ruff check skillguard tests` exit 0; `mypy skillguard` exit 0;
`python -m pytest -q` all pass.

### Step 3: Apply `ruff format` once

Run `ruff format skillguard tests` in its own commit so the formatting churn is
isolated from logic changes.

**Verify**: `ruff format --check skillguard tests` exit 0; tests still pass.

### Step 4: Pre-commit + CI

Create `.pre-commit-config.yaml` wiring ruff (lint + format) and mypy. Add a
`lint` job to `.github/workflows/ci.yml` running `ruff check`, `ruff format
--check`, and `mypy skillguard`. Optionally add `3.12` and `3.14` to the matrix
(or trim the advertised classifiers to match CI — keep the support claim honest),
and add `pytest-cov` with `--cov=skillguard --cov-fail-under=<current measured>`
(measure first; set the floor at the current level, ratchet later).

**Verify**: re-run all commands in the table; all exit 0.

## Done criteria

- [ ] `ruff check skillguard tests` exit 0.
- [ ] `ruff format --check skillguard tests` exit 0.
- [ ] `mypy skillguard` exit 0.
- [ ] `python -m pytest -q` all pass.
- [ ] CI has a lint/typecheck job; `.pre-commit-config.yaml` exists.
- [ ] `plans/README.md` row for 004 updated.

## STOP conditions

- mypy surfaces a genuine bug (e.g. an attribute that can be `None` is
  dereferenced) that needs a behavioral decision — report it as a finding (with a
  failing test if possible) rather than silencing with `# type: ignore`.
- The initial `ruff format` would reflow >50% of lines — re-tune `line-length`
  first so the diff stays reviewable.

## Maintenance notes

- Ratchet mypy toward `--strict` in a later plan once the decompositions land
  (smaller modules type-check more easily).
- Keep `ignore_missing_imports` scoped to the optional `cisco`/`skill_scanner`
  deps if you later tighten mypy.
