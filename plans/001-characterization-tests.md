# Plan 001: Pin cli.py behavior with characterization tests before any refactor

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the next
> step. If anything in "STOP conditions" occurs, stop and report — do not
> improvise. When done, update the status row for this plan in `plans/README.md`
> unless a reviewer told you they maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat c6e9d42..HEAD -- skillguard/cli.py skillguard/mcp.py tests/`
> If `skillguard/cli.py` changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW (purely additive — new test files only; no source code is modified)
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `c6e9d42`, 2026-06-13

## Why this matters

`cli.py` is 1383 lines — 44% of the package — and its primary feature (scanning
**skills** and rendering the table/markdown/quiet reports) has **zero** test
coverage that exercises it through `main()`. The only end-to-end CLI test
(`tests/test_cli_mcp.py`) drives the *MCP* path; the skill scan path, the three
report renderers, the engine selector, and the MCP dedupe helper are all
unpinned. Plans 003, 005, and 006 will move and rewrite this code. Without a
golden-output safety net, a refactor could silently change verdicts or output
and every existing test would still pass. This plan installs that net first.

It is deliberately **additive only** — it touches no source file, so it cannot
break anything, and it can be reviewed and merged with full confidence.

## Current state

The test suite (`pytest`) currently passes 131 tests in ~2s, hermetically (no
network: subprocesses run with `HOME` redirected to a tmp dir; the SkillAudit
engine's `urlopen` is mocked). The harness conventions you must match:

- **End-to-end CLI tests** run `cli.py` as a subprocess with `HOME` pointed at a
  tmp dir. See `tests/test_cli_mcp.py:23-33`:
  ```python
  def run_cli(tmp_home: Path, *args: str, env_extra=None) -> subprocess.CompletedProcess:
      env = dict(os.environ)
      env["HOME"] = str(tmp_home)
      env.pop("SKILLGUARD_ACTIVITY_LOG", None)
      env.pop("SKILLGUARD_MCP_POLICY", None)
      if env_extra:
          env.update(env_extra)
      return subprocess.run(
          [sys.executable, str(CLI), *args],
          capture_output=True, text=True, env=env, cwd=str(tmp_home),
      )
  ```
  where `CLI = REPO_ROOT / "skillguard" / "cli.py"` (`test_cli_mcp.py:17-18`).
- **Direct (in-process) tests** construct `SkillInfo` objects and call functions
  directly. See `tests/test_local_engine.py:24-30` for `_build_skill(skill_dir)`
  and `tests/conftest.py:14-34` for the `malicious_skill_dir` / `clean_skill_dir`
  / `FIXTURES_DIR` fixtures.
- **Fixtures on disk**: `tests/fixtures/malicious-skill/` (with `SKILL.md` +
  `scripts/setup.sh`, `scripts/helper.py` — these trigger local-engine findings)
  and `tests/fixtures/clean-skill/` (`SKILL.md` + `scripts/format.py` — zero
  findings).
- **Mocking `urlopen`**: `tests/test_skillaudit_engine.py` already monkeypatches
  `urllib.request.urlopen` with a fake response object; reuse that pattern for
  HTTP error tests.

Code under test (cited so you can confirm you're pinning the right behavior):

- **Report renderers** — `cli.py:753-848` `report_table(skills, engines_used,
  scan_time, verbose=False)`, `cli.py:851-909` `report_json(...)`,
  `cli.py:912-962` `report_markdown(... verbose=False)`, `cli.py:965-976`
  `report_quiet(skills)`. All take `list[SkillInfo]` and print to stdout.
- **Medium-findings behavior to lock** — `cli.py:813-823`. The MEDIUM section
  loop iterates **all** skills (`for skill in skills:` at line 818), so a target
  whose `max_severity` is `critical`/`high` **still lists its medium findings**.
  (There is a dead, unused `med_skills` variable at line 814 that plan 003 will
  delete; your test must assert the *all-skills* behavior so that deletion is
  provably safe.)
- **Engine selector** — `cli.py:1105-1130` `_build_engines(engine_names, quiet)`.
  Returns `(engines, used)`. `local` and `skillaudit` are always added; `cisco`
  and `snyk` are gated on `.available`; an unknown name prints
  `f"Unknown engine: {name}"` to stderr and calls `sys.exit(1)`.
- **MCP dedupe** — `cli.py:718-738` `_dedupe_mcp_findings(findings)`. Collapses
  findings with the same `(engine, category, message)`, keeping the one whose
  `file` ranks lowest (`command.txt`/`endpoint.txt` = 0, `mcp-config.json` = 1,
  anything else = 2), preserving first-seen order.
- **SkillAudit HTTP errors** — `cli.py:393-414`. On `HTTPError` with code 429 the
  engine yields a single `info`/`rate_limited` Finding (it does not crash).
- **Skill discovery** — `cli.py:77-119` `discover_skills(scope, project_dir,
  single_skill=None)` reads `GLOBAL_SKILLS_DIR = Path.home()/".claude"/"skills"`
  (`cli.py:61`) for global scope. An e2e skill test seeds skills there by
  copying a fixture into `tmp_home/.claude/skills/<name>/`.

The README exit-code contract (`README.md:199-205`): the CLI exits **0 even when
findings exist** (findings are reported, not an error); it exits **1** only when
no targets are found or an engine is unknown. Do not "fix" the exit-0-on-findings
behavior — it is intentional.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Install (once) | `pip install -e ".[dev]"` | exit 0 |
| Run full suite | `python -m pytest -q` | all pass (131 existing + your new tests) |
| Run one new file | `python -m pytest tests/test_cli_skills.py -v` | all pass |
| Confirm count grew | `python -m pytest -q \| tail -1` | a higher passed count than 131 |

A virtualenv exists at `.venv/`. If `python -m pytest` is not found, use
`.venv/bin/python -m pytest`. Do not create a new venv.

## Scope

**In scope** (create these files only):
- `tests/test_cli_skills.py` (create) — e2e skill scan through `main()`
- `tests/test_reports.py` (create) — direct renderer tests
- `tests/test_build_engines.py` (create) — engine selector + unknown-engine exit
- `tests/test_mcp_dedupe.py` (create) — `_dedupe_mcp_findings` unit test
- `tests/test_skillaudit_engine.py` (modify) — add HTTP-error cases only

**Out of scope** (do NOT modify):
- Any file under `skillguard/` — this plan adds tests only. If you find yourself
  wanting to change source to make a test pass, STOP: the test is wrong, or
  you've found a real bug to report, not fix.
- `tests/test_cli_mcp.py` and other existing test files (except the one
  `test_skillaudit_engine.py` addition).

## Git workflow

- Branch: `refactor/improve-foundation` (create if absent:
  `git switch -c refactor/improve-foundation`). If a reviewer already put you on
  a branch, stay on it.
- Commit message style matches the repo's imperative, capitalized subject (see
  `git log --oneline -5`), e.g. `Add characterization tests pinning cli.py scan + reports`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: E2E skill scan through `main()` — `tests/test_cli_skills.py`

Create `tests/test_cli_skills.py`. Reuse the subprocess harness from
`test_cli_mcp.py` (copy the `run_cli` helper and `REPO_ROOT`/`CLI` constants, or
import them). Seed skills by copying fixture dirs into the tmp HOME:

```python
import json, os, shutil, subprocess, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "skillguard" / "cli.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

def run_cli(tmp_home, *args):
    env = dict(os.environ); env["HOME"] = str(tmp_home)
    env.pop("SKILLGUARD_ACTIVITY_LOG", None); env.pop("SKILLGUARD_MCP_POLICY", None)
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, env=env, cwd=str(tmp_home))

def seed_skill(tmp_home, fixture_name, as_name):
    dst = tmp_home / ".claude" / "skills" / as_name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURES / fixture_name, dst)
```

Write these tests (assert behavior, not incidental formatting):
- `test_scan_skills_json_summary`: seed `malicious-skill` as `evil` and
  `clean-skill` as `good`; run `--target skills --scope global --engines local
  --format json`; assert `returncode == 0`, `summary.total_skills == 2`, the
  `evil` target's `max_severity` is in `("critical","high")`, and `good` is
  `"clean"`.
- `test_scan_skills_quiet_lines`: same seed; run `--target skills --scope global
  --engines local --quiet`; assert the output contains
  `target(s) have HIGH+ findings` and names `evil`.
- `test_scan_skills_table_contains_finding`: same seed; run `--target skills
  --scope global --engines local`; assert `returncode == 0` and the stdout
  mentions `evil` and `HIGH` (or `CRITICAL`).
- `test_scan_no_skills_exits_1`: empty HOME (no skills dir); run `--target skills
  --scope global --engines local`; assert `returncode == 1` and stderr contains
  `No skills`.
- `test_scan_findings_still_exit_0`: seed only `malicious-skill`; run `--target
  skills --scope global --engines local`; assert `returncode == 0` (locks the
  README exit-code contract).

**Verify**: `python -m pytest tests/test_cli_skills.py -v` → all pass.

### Step 2: Direct renderer tests — `tests/test_reports.py`

Create `tests/test_reports.py`. Import the renderers and model:
```python
from skillguard.cli import report_table, report_json, report_markdown, report_quiet
from skillguard.model import Finding, SkillInfo
from pathlib import Path
```
Build `SkillInfo` objects by hand (no disk needed). Construct at least:
- a skill with BOTH a `high` and a `medium` finding (this is the key case),
- a skill with only a `medium` finding,
- an MCP target (`kind="mcp"`) with a `low`/`info` advisory and one triaged FP
  (`Finding(..., triaged_fp=True)`),
- a clean skill (no findings).

Tests (use `capsys` to capture stdout):
- `test_table_lists_medium_on_high_target`: render the high+medium skill via
  `report_table([...], ["local"], "t")`; assert the captured output contains the
  MEDIUM section AND the medium finding's message — proving medium findings are
  shown even on a high-severity target. **This is the assertion that makes plan
  003's dead-code removal provably safe; do not omit it.**
- `test_table_advisories_only_when_verbose`: render a skill with a `low`/`info`
  finding; assert the `ADVISORIES` header is absent with `verbose=False` and
  present with `verbose=True`.
- `test_table_triaged_suppressed_note`: include a triaged FP; assert the output
  contains `suppressed as triaged`.
- `test_json_splits_skills_and_mcps`: render a mixed list via `report_json`;
  parse the captured stdout as JSON; assert `skills`, `mcps`, `targets` arrays
  exist and `summary.total_mcps`/`total_skills` are correct.
- `test_markdown_has_summary_table_and_findings`: render via `report_markdown`;
  assert `## Summary by Engine` and `## Findings by Target` (or `## All targets
  clean` for the clean case) appear.
- `test_quiet_clean_vs_flagged`: `report_quiet` on a clean list says `all clean`;
  on a high list says `HIGH+ findings`.

**Verify**: `python -m pytest tests/test_reports.py -v` → all pass.

### Step 3: Engine selector — `tests/test_build_engines.py`

Create `tests/test_build_engines.py`:
```python
import pytest
from skillguard.cli import _build_engines
```
- `test_local_always_selected`: `_build_engines(["local"], quiet=True)` returns
  engines whose `used` list is `["local"]`.
- `test_unknown_engine_exits_1`: `with pytest.raises(SystemExit) as e:
  _build_engines(["bogus"], quiet=True)` and assert `e.value.code == 1`.
- `test_unavailable_engines_skipped`: `_build_engines(["local","cisco","snyk"],
  quiet=True)` with cisco not installed and `SNYK_TOKEN` unset → `used == ["local"]`
  (use `monkeypatch.delenv("SNYK_TOKEN", raising=False)`).

**Verify**: `python -m pytest tests/test_build_engines.py -v` → all pass.

### Step 4: SkillAudit HTTP-error path — extend `tests/test_skillaudit_engine.py`

Add a test that monkeypatches `urllib.request.urlopen` to raise
`urllib.error.HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=None)` and
asserts `SkillAuditEngine().scan(target)` returns exactly one Finding with
`severity == "info"` and `category == "rate_limited"` (confirm the exact category
string against `cli.py:393-407` first; match what the code emits). Follow the
existing mocking pattern already in that file.

**Verify**: `python -m pytest tests/test_skillaudit_engine.py -v` → all pass.

### Step 5: MCP dedupe — `tests/test_mcp_dedupe.py`

Create `tests/test_mcp_dedupe.py`:
```python
from skillguard.cli import _dedupe_mcp_findings
from skillguard.model import Finding
```
- `test_dedupe_keeps_most_specific_location`: build two findings with the same
  `(engine, category, message)` — one with `file="mcp-config.json"`, one with
  `file="command.txt"`; assert the result has length 1 and the survivor's
  `file == "command.txt"`.
- `test_dedupe_keeps_distinct_messages`: two findings with different messages →
  both kept, original order preserved.

**Verify**: `python -m pytest tests/test_mcp_dedupe.py -v` → all pass.

## Test plan

- New files: `test_cli_skills.py`, `test_reports.py`, `test_build_engines.py`,
  `test_mcp_dedupe.py`; plus HTTP-error case(s) in `test_skillaudit_engine.py`.
- Structural patterns to copy: subprocess harness from `tests/test_cli_mcp.py`;
  direct-construction from `tests/test_local_engine.py`; `urlopen` mocking from
  `tests/test_skillaudit_engine.py`.
- Verification: `python -m pytest -q` → all pass, with a strictly higher passed
  count than the 131 baseline.

## Done criteria

ALL must hold:

- [ ] `python -m pytest -q` exits 0; passed count > 131.
- [ ] The four new test files exist and each passes in isolation.
- [ ] `test_reports.py` includes `test_table_lists_medium_on_high_target` (or
      equivalently named) asserting medium findings show on a high-severity target.
- [ ] `git status` shows changes ONLY under `tests/` (no `skillguard/` edits).
- [ ] `plans/README.md` status row for 001 updated.

## STOP conditions

Stop and report (do not improvise) if:

- The "Current state" excerpts don't match the live code (cli.py drifted) — run
  the drift check.
- A renderer's actual output structurally contradicts this plan (e.g. the JSON
  has no `mcps` key) — report the real shape; do not change source to match.
- Any new test reveals what looks like a real bug. Document it (with a failing
  test if you can) and report it — do NOT fix source here; that's plan 003.
- A test can only pass by editing a file under `skillguard/`.

## Maintenance notes

- These tests are characterization tests: they pin **current** behavior, not
  necessarily ideal behavior. Plans 003/005/006 may intentionally change some
  output; when they do, the test is updated *in that plan* with a note, not here.
- The medium-on-high-target assertion (Step 2) is load-bearing for plan 003's
  removal of the dead `med_skills` variable — a reviewer should confirm it stays.
- If `report_table` is later split into `render/` modules (plan 006), these
  tests should keep passing by importing from the new location via the cli
  re-export; if they break, the re-export shim is missing.
