# Check-In: Refactor Conformance & Forward-Architecture Fit

**Date:** 2026-06-14
**Reviewer:** Claude (Opus 4.8), 6 parallel sub-agents + direct re-verification of load-bearing claims
**Trigger:** "Are we sticking to the refactor as proposed? And have we not forgotten what's next — are we accounting for it by refactoring to *proper* architecture?"
**Scope reviewed:** all 11 `plans/`, all 7 `.claude/handoff/`, all `.claude/session-memory/`, full git history (a1abc28→359a21e), product backlog (`task*.md`), and the live `skillguard/` package.

---

## TL;DR

| Question | Verdict |
|---|---|
| **1. Sticking to the refactor as proposed?** | ✅ **YES — textbook.** 8/8 done plans executed faithfully, in order, no scope-creep, nothing the roadmap explicitly rejected was built. Detection output is byte-identical across the entire refactor = behavior-preserving exactly as promised. One soft-LOC overage, *documented and accepted*. |
| **2. Accounting for "what's next" in the architecture?** | 🟡 **MOSTLY — two specific, cheap gaps.** Most seams are right (new engines ≈ drop-in, MCP deepening localized, sandboxing boundary clean, PyPI is token-blocked not architecture-blocked). But the **two highest-priority upcoming product moves have no seam yet**: the Portcullis **rename** (no naming authority) and the **Cisco false-positive fix** (suppression heuristic trapped inline). And the roadmap is structurally disconnected from the product backlog, which is *how* "what's next" gets forgotten. |
| **Go/No-Go on the handoff (resume plan 009)?** | ✅ **GO**, with a small recommended augmentation (below) and two posture decisions that are yours to make. |

The refactor is healthy. The risk is not drift *within* the refactor — it's that the refactor could **finish clean and still hand off to product work through seams that don't exist yet**, forcing us to re-open freshly-refactored files to do the rename and the FP fix. Closing two ~30-line gaps now prevents that.

---

## Q1 — Are we sticking to the refactor as proposed?

**Yes.** Plans executed in strict order 001→008, each behind a test net, each scoped exactly to its plan. Verified commit-by-commit:

| Plan | Commit | Verdict | Note |
|---|---|---|---|
| 001 characterization tests | 0f451ff | FAITHFUL | tests only, 0 source changes (131→151) |
| 002 consolidate primitives | 6768a00 | FAITHFUL | `_util.py`; **deliberately left hook.py/store.py paths untouched** (151) |
| 003 correctness & robustness | e0fed31 | FAITHFUL | the 4 named defects, +5 tests (151→156) |
| 004 DX backstop | 44cfde0 + d4b9a05 | FAITHFUL | ruff/mypy/CI; format isolated; pip-audit intentionally not gated (156) |
| 005 engine protocol + registry | 0bba36b | FAITHFUL | Protocol + `ENGINE_REGISTRY` + attribute dispatch (156→165) |
| 006 decompose cli.py | f85680b | FAITHFUL | 289-LOC facade; **did NOT build the rejected `commands/` package** (165→167) |
| 007 decompose mcp.py | 4bd786a | FAITHFUL (1 accepted deviation) | 8-module package; see below (167) |
| 008 harden introspection | 359a21e | FAITHFUL | env-min + SSRF + lifecycle; OS sandboxing correctly out of scope (167→177) |

**The only deviation — and it's accounted for.** Plan 007's done-criterion was "No file under `skillguard/mcp/` exceeds **~200 LOC**." Two modules land over it: `engine.py` (273) and `discovery.py` (224). I verified this is **not** a silent breach:
- The criterion is written `~200` (soft target), and
- It is explicitly acknowledged in `plans/README.md:161-162` — *"Largest modules engine.py (273) and discovery.py (224) sit just over the ~200 soft target — intrinsic to the [concern]"* — and the sizes are recorded in the 007 session-memory file.

→ **Accepted tradeoff, documented at the time. No action required** unless you want them split further (not recommended — they're cohesive single-concern modules).

**Anti-over-engineering guardrails held:** the roadmap explicitly rejected a `commands/` package and gating `pip-audit`; neither was built. Status table matches git reality (001–007 on `main`@4bd786a; 008 on `refactor/harden-introspect`@359a21e). Test trajectory 131→151→156→165→167→177 is internally consistent across commits and the session log.

**Bottom line:** This is disciplined, plan-faithful execution. There is **no drift inside the refactor.**

---

## "What's Next" — the product backlog we must not forget

The refactor (`plans/`) and the product backlog (`task*.md`) are **two disconnected tracking systems**. The roadmap ends at plan 010 (a contributor `CLAUDE.md`) with **no "now resume product work" handoff line**, and it never references the `task*.md` files. That disconnection is the structural reason "what's next" can get dropped. Here is the live backlog, with where each is tracked:

| What's next | Tracked in | Type | Note |
|---|---|---|---|
| **PyPI publish** (`pip install skillguard` 404s today) | `task.md` | distribution | Blocked only on an API token. CHANGELOG already *claims* it's shipped. |
| **Portcullis rename** ("name undersells half the product") | `task-brand-names.md` | positioning | Mannan leaning Portcullis. **Explicitly "do before PyPI."** |
| **Cisco doc-table false-positives** (clean fixture → 1 high + 1 med) | `task-cisco-false-positives.md` | detection quality | Erodes trust; users `--mark-fp` reflexively → weakens enforcement. |
| **TOCTOU gap for plugin-namespaced skills** | `README.md` / `SECURITY.md` | security correctness | Hook can't locate plugin skills for the mtime check. |
| **True sandboxing of `--mcp-introspect`** | `plans/008` note | security | 008 reduces blast radius; real fix is container/seccomp. |
| **MCP detection depth + enforce-mode token match** | `plans/009-D` | detection quality | Loose token → risky server can inherit another's clean verdict. |

⚠️ **Sequencing constraint the roadmap doesn't encode:** **rename must precede the first PyPI publish.** Publishing as `skillguard` first turns the rename into a breaking migration (PyPI name squat, user muscle memory, stale cache dirs). `task-brand-names.md` says this; the roadmap doesn't, and `task.md` treats PyPI as "ready to ship." If 010 closes and someone grabs the PyPI token, we could ship the *old* name by accident. **This ordering is a decision for you** (see below).

---

## Q2 — Is the refactor building *proper architecture* for what's next?

Mostly yes. Verdicts grounded in live code:

| Upcoming work | Fit | Why (verified) |
|---|---|---|
| Add a new detection engine | 🟢 READY* | `ENGINE_REGISTRY` (`engines/__init__.py`) is a true single-registration point. *Caveat: author must also hand-add the module to `install.sh` MODULES (CI `test_install_sync.py` catches drift). |
| MCP detection depth + 009-D token fix | 🟢 READY | `mcp/rules.py` is pure data (drop-in rules); `mcp/engine.py` composes single-concern predicates; verdict-match logic isolated in `hook.py:find_mcp_verdict`. |
| Sandboxing follow-on (008) | 🟢 READY | `mcp/introspect.py` already isolates the untrusted launch (`_minimal_env`, `_kill_tree`, `start_new_session`). A sandbox wrapper replaces one function's spawn call. |
| PyPI publish + version sync | 🟢 READY | `test_version_sync.py` enforces 4-way version agreement. Token-blocked, **not** architecture-blocked. |
| TOCTOU plugin-namespaced skills | 🟡 PARTIAL | `hook.py:find_skill_mtime` iterates candidate paths — a clean seam to add a plugin-aware path — but currently silently no-ops (cached_mtime=0) when resolution fails. Needs the third candidate + a fail-closed-on-unresolved decision. |
| **Cisco FP fix** | 🔴 **GAP** | The doc-table suppression is an anonymous inline at `local.py:47` (`if "\|" in stripped and stripped.count("\|") >= 3`). The documented fix ("adapter-side post-filter **reusing** the local heuristic") **cannot import it.** |
| **Portcullis rename** | 🔴 **GAP** | **No naming authority exists.** Verified below. |

### GAP 1 — No naming authority (blocks a cheap rename) 🔴

The product name / cache path / env prefix are hardcoded across the tree with **no constant**:

- Cache dir `~/.claude/skillguard-cache` declared **independently 3×**: `store.py:49`, `config.py:52`, `hook.py:35`. A `config.default_cache_dir()` authority *exists* (used by `cli.py:96`) but `store.py` and `hook.py` **bypass it** with literals.
- DB name `skillguard.db`: `store.py:49`, `hook.py:88`, `paths.py:39`.
- Env prefix `SKILLGUARD_`: `config.py` (×2 live) + `engines/skillaudit.py:16,18`. No `ENV_PREFIX` constant.
- Entry-point name `skillguard`: `pyproject.toml`, `install.sh`, plugin manifest.
- `grep APP_NAME|ENV_PREFIX|branding` → **nothing.**

**Today the rename is a find-and-replace-and-pray across 6+ files.** That is the opposite of "refactor to proper architecture for what's next" — and the rename is the single biggest near-term product move.

**Important nuance the fix must respect (I verified this; the sub-agent's naive fix would break it):** `hook.py` imports the package *inside a try/except* (lines 41–47) and is installed as a **standalone script** (`install.sh` MODULES, runs as `python3 .../hook.py`). Its hardcoded `CACHE_DIR` at line 35 is **deliberate** — the hook must resolve its cache path even when the `skillguard` package is unimportable (this is the exact failure mode plan 009-A is about). So you **cannot** simply route `hook.py` through `config.default_cache_dir()`.

→ **The right fix:** a **zero-dependency** `skillguard/branding.py` holding `APP_NAME`, `CACHE_DIR_NAME`, `DB_NAME`, `ENV_PREFIX`. `config.py` and `store.py` consume it directly; `hook.py` can import *just that leaf module* under its existing import guard (it pulls in nothing else), collapsing the rename to: edit `branding.py` + two out-of-package files (`pyproject.toml`, `install.sh`). ~30 lines, zero behavior change, covered by existing tests.

### GAP 2 — Doc-table heuristic is not reusable (blocks the Cisco FP fix) 🔴

`local.py:47` is the only place that knows "a markdown table row isn't a real finding." The Cisco engine has no equivalent, which is *the entire cause* of the false positives in `task-cisco-false-positives.md`, and the documented fix depends on reusing this exact heuristic.

→ **The right fix:** hoist a 4-line `is_markdown_table_row(line)` into `skillguard/patterns.py` (already the ruleset home). `local.py` imports it; the future Cisco post-filter imports the same function. Turns GAP into READY for ~4 lines, today.

---

## Go / No-Go on the handoff (resume plan 009)

### ✅ GO.

Plan 009 is faithful next-step work and is **more product-aligned than the rest of the refactor** — roughly **50% real detection value**:

- **009-C (redaction hides malware)** — a genuine **false negative**: a malicious `node -e "<base64 payload>"` arg gets secret-redacted to `<redacted-literal>` *before* `LocalEngine` scans it, so the obfuscation/exec detector never sees it. Fixing it makes SkillGuard catch a class of attack it currently misses. (Hard STOP guard: the secret-never-persisted invariant must stay green.)
- **009-D (loose MCP token match)** — a genuine **fail-open under `enforce`**: a risky/unscanned server can inherit a *different* server's clean verdict.
- 009-A (hook fail-open on import failure) and 009-B (cache-glob DoS) are internal robustness — important, not new detection.

It's investigate-then-fix, characterization-test-first, MED effort (~8+ new tests, touches `hook.py` + `mcp/`), no new modules. It will **not** delay product work; two of its four items *are* product (detection-correctness) work.

### Two posture decisions are YOURS (the handoff correctly flags these — do not let them be flipped unilaterally):

1. **009-A — fail-open vs fail-closed for MCP when the package is unimportable.** Today a broken install silently downgrades configured `enforce`→`warn` (MCP calls that should block are allowed, no signal). Skills already fail *closed*. Options: (a) minimum — loud stderr notice on downgrade; (b) stronger — fail *closed* on `enforce` (broken install ⇒ MCP blocked until fixed; a reliability hit). **Which posture?**
2. **009-D — on ambiguous token match, resolve toward "unscanned" (safe, may add nudges) vs keep loose match (permissive).** Tightening is safer but could turn currently-resolving legit servers into "unscanned" and nudge users. **Tighten with the STOP condition that legit prefix matches must still resolve?**

---

## Proposed updates to move us toward intent

These keep us *in the spirit of the refactor* (they ARE "refactor to proper architecture") while making sure "what's next" isn't forgotten. None is large.

1. **Fold two cheap seams into the refactor** — either as items in 009 or a small new `plans/008.5`:
   - `branding.py` naming authority (GAP 1) — **highest leverage**; de-risks the rename, respects `hook.py` import-independence. ~30 LOC, no behavior change.
   - hoist `is_markdown_table_row()` to `patterns.py` (GAP 2) — makes the Cisco FP fix a drop-in. ~4 LOC.
2. **Reconnect the roadmap to the product backlog.** Add a "What's next after the refactor" section to `plans/README.md` linking the `task*.md` items, so closing 010 hands off cleanly instead of dead-ending. (010's `CLAUDE.md` is the natural place to also point contributors at the backlog.)
3. **Make the rename-before-PyPI ordering an explicit decision.** Recommend: decide the name → land `branding.py` → rename → *then* take the PyPI token. Encode this ordering wherever you'll actually see it (`task.md` and/or `task-brand-names.md`), because `task.md` currently presents PyPI as ship-ready.
4. **(Optional, later) TOCTOU partial seam** — when you do the plugin-namespaced fix, also resolve the silent-no-op (cached_mtime=0 on unresolved path) to fail-closed; that's the security-correct posture and another decision to make deliberately.

I did **not** modify the roadmap or code — these are proposals for your call, consistent with the handoff's "surface posture trade-offs, don't flip them" discipline.

---

## What I verified myself (crux re-checks, not inherited)

- GAP 1 duplication sites — `grep` confirmed `store.py:49`, `config.py:52`, `hook.py:35/88`, `paths.py:39`; no `APP_NAME`/`ENV_PREFIX`/`branding` anywhere.
- GAP 2 — `local.py:47` is the sole, inline occurrence.
- Plan 007 LOC — `wc -l`: engine.py 273, discovery.py 224; **acknowledged** in `plans/README.md:161-162` + 007 session-memory. (Corrected a sub-agent's "couldn't confirm" hedge.)
- `hook.py` import-independence — confirmed package import is `try/except`-guarded (lines 41–47) and the file ships standalone via `install.sh` MODULES; its hardcoded path is intentional, which changes GAP 1's fix.
- Detection-byte-identical claim — corroborated across three independent agents reading the diffs; no commit added/changed a rule, severity, engine output, or renderer.
