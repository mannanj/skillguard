# Plan 003: Correctness & robustness fixes (DB lifecycle, silent failures, dead code)

> **Executor instructions**: Step by step; verify each step; honor STOP
> conditions; update `plans/README.md`. **Drift check first**:
> `git diff --stat c6e9d42..HEAD -- skillguard/cli.py` — if cli.py changed,
> re-read the cited ranges before editing.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW–MED (touches the scan loop's DB lifecycle; covered by plan 001 + `test_cli_mcp.py`)
- **Depends on**: 001 (characterization tests)
- **Category**: bug
- **Planned at**: commit `c6e9d42`, 2026-06-13

## Why this matters

Four reliability defects in `cli.py`, all confirmed by reading:

1. **DB connection leak + triple silent swallow** (`cli.py:1306-1358`). The
   history-DB connection is opened, written, finished, and closed across **three
   separate `try/except Exception: pass` blocks with no `finally`**. If the scan
   loop raises between open and close, `conn.close()` never runs (leak). And a
   persistently failing DB (corrupt/disk-full) produces **no diagnostic at all**,
   even under `-v` — the user believes scans are recorded when they aren't.
2. **`--mcp-introspect` failures are invisible** (`cli.py:1290-1297`). When a
   user explicitly asks to introspect and a server fails to launch/times out, the
   only trace is `log_activity(...)`, which is itself gated off when activity
   logging is disabled. Silent failure on a deliberately-requested operation.
3. **Triage commands crash on a corrupted cache** (`cli.py:557`,
   `mark_fp_command`). The read+parse is unguarded, so `--mark-fp NAME` on a torn
   cache raises an uncaught `json.JSONDecodeError`/`TypeError` and exits with a
   traceback — less robust than the hook, which guards the same read
   (`hook.py:122-130`).
4. **Dead/misleading code in the table reporter** (`cli.py:789-791` no-op;
   `cli.py:814` an unused `med_skills` with a tautological predicate). Plan 001's
   `test_table_lists_medium_on_high_target` proves removing line 814 is safe.

## Current state

- `cli.py:1304-1358` — DB lifecycle in three swallow blocks (open at 1306-1313,
  `record_scan` at 1331-1340, `finish`+`close` at 1350-1358), no `finally`.
- `cli.py:1290-1297` — introspection loop; on `not intro.get("ok")` only
  `log_activity` runs (no stderr).
- `cli.py:557-561` — `cache = json.loads(cache_file.read_text())` unguarded;
  contrast the guarded version already present in `unmark_fp_command` at
  `cli.py:608-615` (`try/except (OSError, json.JSONDecodeError)`).
- `hook.py:122-130` — the pattern to mirror for guarded cache reads.
- `cli.py:789-791`:
  ```python
  if row_total == 0 and sev in ("low",):
      # Always show low even if 0
      pass
  ```
  (a no-op; the row prints regardless below).
- `cli.py:814`:
  ```python
  med_skills = [s for s in skills if s.max_severity == "medium" and s.max_severity not in ("critical", "high")]
  ```
  `med_skills` is never used (the loop at 818 iterates all `skills`); the second
  clause is always true when the first holds.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install | `pip install -e ".[dev]"` | exit 0 |
| Full suite | `python -m pytest -q` | all pass |
| Targeted | `python -m pytest tests/test_cli_mcp.py tests/test_triage.py tests/test_reports.py -v` | all pass |

## Scope

**In scope**: `skillguard/cli.py`; new tests in `tests/test_triage.py` (corrupted
cache) and optionally `tests/test_cli_mcp.py` (introspect-failure stderr).
**Out of scope**: the broader `main()` decomposition (that's plan 006) — here,
fix the lifecycle in place with a context manager/`try-finally`, do not move the
scan loop into a new module yet. Do not touch `mcp.py` introspection internals
(that's plan 008).

## Steps

### Step 1: Single-owner DB lifecycle

Replace the three scattered blocks (1304-1358) with one structure that guarantees
close. Simplest correct form: a `try/finally` (or `contextlib.closing`) owning
open→finish→close, with `record_scan` failures collected and surfaced once. On
DB-open or write failure, print a single `[history] could not record scan: <e>`
to **stderr** unless `args.quiet`. Keep history best-effort (a DB failure must
still never crash a scan), but make it *observable*. Preserve the existing
behavior that history is recorded independent of the activity-log toggle.

**Verify**: `python -m pytest tests/test_cli_mcp.py -q` → all pass (history still
recorded; toggle test still green).

### Step 2: Surface introspection failures

In the `--mcp-introspect` loop (1290-1297), when `not intro.get("ok")`, print
`⚠ introspection of {srv.name} failed: {intro.get('error')}` to stderr unless
`args.quiet`, independent of the activity-log toggle. Keep the existing
`log_activity` call.

**Verify**: add a test (or extend `test_cli_mcp.py`) where introspection of a
bogus stdio server fails and assert the stderr warning appears.

### Step 3: Guard the triage cache read

In `mark_fp_command` (around 557), wrap the read+parse in
`try/except (OSError, json.JSONDecodeError)` and, on failure, print the same
"predates/corrupted, re-scan" message used at line 560 and `sys.exit(1)`. Mirror
`unmark_fp_command`'s existing guard.

**Verify**: add `tests/test_triage.py` case — write `{ not json` into an existing
verdict cache, run `--mark-fp NAME`, assert `SystemExit`/returncode 1 with the
message (not a traceback).

### Step 4: Remove dead code in the table reporter

Delete the no-op at 789-791 and the unused `med_skills` line at 814. Do not
change the MEDIUM loop at 818 (it correctly iterates all skills). Plan 001's
`test_table_lists_medium_on_high_target` must still pass — it proves this is safe.

**Verify**: `python -m pytest tests/test_reports.py -q` → all pass.

## Done criteria

- [ ] `python -m pytest -q` exits 0; new corrupted-cache and introspect-failure
      tests pass.
- [ ] `grep -n "except Exception:" cli.py` around the scan loop shows the three
      swallow blocks replaced by one lifecycle owner with a `finally`/`closing`.
- [ ] `grep -n "med_skills" skillguard/cli.py` returns nothing.
- [ ] `plans/README.md` row for 003 updated.

## STOP conditions

- The history toggle test (`test_activity_toggle_off_keeps_history`) fails — you
  changed *what* is recorded, not just *how* the connection is managed. Revert
  and report.
- Surfacing introspection errors changes an existing test's expected stdout
  (warnings must go to **stderr**, not stdout) — fix the stream, don't relax the test.

## Maintenance notes

- When plan 006 extracts the scan loop into `scan.py`, the lifecycle owner moves
  with it — keep it a single context manager so the extraction is a move, not a
  rewrite.
- The introspection-failure surfacing here is independent of plan 008's
  process-lifecycle hardening inside `mcp.py`; both should land.
