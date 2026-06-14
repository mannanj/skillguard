# Plan 006: Decompose cli.py into modules behind a thin facade

> **Executor instructions**: This is a large, multi-step refactor. Do it as a
> sequence of *moves* (add new module, switch references, re-export), verifying
> the full test suite green after EACH module extraction — never let the suite go
> red between steps. Honor STOP conditions. Update `plans/README.md`.
> **Drift check first**: `git diff --stat c6e9d42..HEAD -- skillguard/cli.py`.

## Status

- **Priority**: P2
- **Effort**: L
- **Risk**: MED (moves ~1100 lines across modules; mitigated by re-exports +
  plan 001 tests + plan 004 typecheck)
- **Depends on**: 001 (tests), 002 (shared helpers), 004 (mypy/ruff net), 005 (engine registry)
- **Category**: tech-debt
- **Planned at**: commit `c6e9d42`, 2026-06-13

## Why this matters

`cli.py` is 1383 lines and holds, in one file: 4 engines (~256 LOC), 4 report
renderers (~219 LOC), 3 history/show commands (~109 LOC), a triage subsystem
(~120 LOC), a cache subsystem (~110 LOC), the 50+ pattern ruleset (~90 LOC), and
a **247-line `main()`** (`cli.py:1133-1379`). Six functions exceed ~50 LOC. The
single most important control path (`main()`) is reachable only via subprocess,
and aggregation logic is duplicated across the renderers (`engine_counts`
rebuilt at `cli.py:757`, `858`, and recomputed at `940`). This plan breaks the
god-module into focused, independently-testable modules, **behind a thin `cli.py`
facade that re-exports every moved public name** so no test or external import
breaks.

## Critical constraint — keep `install.sh` and curl-install in sync

`tests/test_install_sync.py` asserts every package module the scanner imports is
listed in `install.sh`'s remote-fetch loop (a curl-installed copy must contain
every module or it won't import). **Every new module/file you create under
`skillguard/` must be added to that loop**, and if you introduce *sub-packages*
(`engines/`, `render/`), confirm whether the test's assertion covers nested files
— read `tests/test_install_sync.py` first and update both the loop and (if
needed) the test's discovery to be recursive. This bit plan 002 (adding
`_util.py` required an `install.sh` edit); it will bite this plan harder.

## Critical constraint — preserve the public import surface

Tests and the hook import names directly from `skillguard.cli`. Verified
importers include: `LocalEngine`, `SkillAuditEngine`, `SkillInfo`, `Finding`,
`_atomic_write_json`, `write_cache`, `write_skip_cache`, `apply_triage`,
`finding_fingerprint`, `load_triage`, `save_triage`, `mark_fp_command`,
`unmark_fp_command`, `__version__`, and the module global `CACHE_DIR` (which is
monkeypatched). `cli.py` ALREADY uses this re-export pattern for `Finding`/
`SkillInfo` (see `cli.py:46-54`, `68-72`). **Every name moved out must be
re-imported back into `cli.py`** so `from skillguard.cli import X` keeps working,
and `cli.CACHE_DIR` must remain a writable module global that the path helpers
read at call time.

## Target layout (from the structural audit)

```
skillguard/
  patterns.py        ← LOCAL_PATTERNS + _p (the 50+ rule registrations)   ~95 LOC
  paths.py           ← CACHE_DIR source, triage_path, db_path,
                        cache_path_for, resolve_existing_cache             ~45 LOC
  discovery.py       ← discover_skills + rel_to() helper                   ~60 LOC
  engines/
    __init__.py      ← ENGINE_REGISTRY (from plan 005), _build_engines,
                        shared normalize helpers
    local.py cisco.py skillaudit.py snyk.py   (one adapter each)
  triage.py          ← fingerprint, load/save/apply, _rewrite_cache_verdict,
                        mark_fp_command, unmark_fp_command
  cache.py           ← build_verdict, write_cache, write_skip_cache,
                        summarize_findings   (unify the duplicated schema)
  render/
    colors.py        ← severity_color, RESET/BOLD/DIM + NO_COLOR/TTY gate
    summary.py       ← summarize(targets, engines) -> ScanSummary
    reports.py       ← report_table/json/markdown/quiet, _fmt_ts, emit()
  commands.py        ← history/activity/show (gather_* + render_*)
  scan.py            ← run_scan_pipeline(...): the scan loop + DB lifecycle
                        (single context manager — fold in plan 003's fix)
  cli.py             ← build_parser(), dispatch table, main() ≤ ~60 LOC,
                        + back-compat re-exports of every moved public name
```

## Embedded sub-improvements (do these as part of the relevant extraction)

- **CLI-03 / aggregation**: while extracting `render/`, add a pure
  `summarize(targets, engines_used) -> ScanSummary` (engine_counts, severity
  totals, skill/mcp split, triaged_total, clean_count) and have all four
  renderers consume it — kills the triplicated counting at `cli.py:757/858/940`.
- **CLI-07 / colors**: move `severity_color` + `RESET/BOLD/DIM` into
  `render/colors.py` with `enabled = sys.stdout.isatty() and not
  os.environ.get("NO_COLOR")`; helpers return "" when disabled. Fixes the missing
  `NO_COLOR`/TTY gate (ANSI currently leaks into piped/redirected output).
- **CLI-10 / cache schema**: one `build_verdict(skill_or_name, *, skipped,
  engines_used) -> dict` producing the canonical schema; `write_cache`,
  `write_skip_cache`, and `_rewrite_cache_verdict` all use it +
  `summarize_findings(findings, limit=10)`. Keep the on-disk shape byte-compatible
  (the hook reads it — see `hook.py:132-199`).
- **CLI-06 / commands**: split each of history/activity/show into a pure
  `gather_*(conn) -> data` and `render_*(data, fmt)`, returning exit codes
  instead of calling `sys.exit` inline; factor the `if fmt == "json":
  print(json.dumps(...))` prologue into one `emit(data, fmt)`.
- **CLI-01 / main**: `main()` becomes parse → dispatch-or-`run_scan` →
  `sys.exit(code)`. Early-exit subcommands become a dispatch table. The scan loop
  + DB lifecycle move to `scan.py` as `run_scan_pipeline(...) -> int`.
- **CLI-11 / patterns**: move `LOCAL_PATTERNS`/`_p` to `patterns.py`;
  `LocalEngine` imports it; `cli` re-exports `LOCAL_PATTERNS`.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install | `pip install -e ".[dev]"` | exit 0 |
| Full suite (after EACH extraction) | `python -m pytest -q` | all pass, every step |
| Import surface check | `python -c "from skillguard.cli import LocalEngine, SkillAuditEngine, write_cache, apply_triage, mark_fp_command, _atomic_write_json, CACHE_DIR; print('ok')"` | `ok` |
| Lint/type | `ruff check skillguard && mypy skillguard` | exit 0 |
| Color gate | `python skillguard/cli.py --help | cat` then a real scan piped to `cat` | no raw `\033[` escape codes in piped output |

## Scope

**In scope**: creating the new modules above; moving code into them; turning
`cli.py` into a facade + `main()`. **Out of scope**: changing detection behavior,
the cache on-disk schema's *field set* (keep byte-compatible), or `mcp.py` (plan
007). Do not "improve" engine internals here beyond the plan-005 protocol already
in place.

## Steps (extract one module at a time; suite green after each)

1. **patterns.py** — move `LOCAL_PATTERNS`/`_p`; import into cli; re-export. Verify.
2. **paths.py** — move path helpers; keep `cli.CACHE_DIR` as a re-exported,
   monkeypatchable global that `paths` reads. Verify (esp. `test_cache.py`/
   `test_triage.py` monkeypatch).
3. **render/colors.py** — move colors + add NO_COLOR/TTY gate. Verify; check
   piped output has no escapes.
4. **render/summary.py + render/reports.py** — add `summarize()`; move renderers
   to consume it. Verify `test_reports.py`.
5. **cache.py** — unify `build_verdict`/`summarize_findings`. Verify
   `test_cache.py` + that the on-disk JSON is unchanged (compare a sample).
6. **triage.py** — move triage subsystem (incl. plan-003 guard if already landed).
   Verify `test_triage.py`.
7. **commands.py** — split gather/render; return exit codes. Verify
   `test_cli_mcp.py` history/activity/show.
8. **engines/** — move the 4 engine classes into `engines/`; registry imports
   them; cli re-exports. Verify engine tests.
9. **scan.py** — extract `run_scan_pipeline` (scan loop + single DB lifecycle
   owner). Verify full e2e.
10. **cli.py facade** — reduce `main()` to parse→dispatch→exit; add a dispatch
    table for early-exit subcommands; ensure ALL moved names are re-imported.
    Final full-suite + import-surface verify.

## Done criteria

- [ ] `python -m pytest -q` all pass; `mypy skillguard` + `ruff check` exit 0.
- [ ] The import-surface check command prints `ok`.
- [ ] No single `skillguard/*.py` file exceeds ~300 LOC (`wc -l skillguard/**/*.py`).
- [ ] `main()` is ≤ ~60 LOC.
- [ ] Piped table output contains no raw ANSI escapes (NO_COLOR/TTY gate works).
- [ ] On-disk verdict JSON is byte-compatible with pre-refactor (hook still reads it).
- [ ] `plans/README.md` row for 006 updated.

## STOP conditions

- The suite goes red after an extraction and isn't green within one fix attempt —
  STOP, revert that extraction, report. Do not proceed with a red suite.
- A moved name can't be re-exported without a circular import — report the cycle;
  it usually means two modules should share a third (e.g. `paths`/`_util`).
- The cache on-disk schema would change shape — STOP; the hook contract is
  load-bearing (plan 009 covers a typed schema separately).

## Maintenance notes

- Keep `cli.py` a facade: new public helpers live in the focused module and are
  re-exported, not added back to cli.
- A reviewer should scrutinize: the re-export list completeness, the
  byte-compatibility of the verdict JSON, and that `CACHE_DIR` monkeypatching
  still redirects every path helper.
