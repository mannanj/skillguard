#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""
SkillGuard — Multi-engine security scanner for Claude Code skills.

Scans skills through up to 4 independent detection engines:
  - local:      50+ regex patterns (instant, no deps)
  - cisco:      YARA + YAML static rules, Python AST behavioral analysis
  - skillaudit: 401 patterns via REST API (skillaudit.vercel.app)
  - snyk:       LLM-powered semantic analysis via Snyk agent-scan CLI

Usage:
  skillguard                           # scan all, local engine
  skillguard --scope global            # global skills only
  skillguard --engines all             # all 4 engines
  skillguard --skill security          # single skill
  skillguard --format json             # JSON output
  skillguard --quiet                   # minimal output (for hooks)
"""

from __future__ import annotations

import argparse
import sys
import time  # noqa: F401  (patch seam: tests monkeypatch cli.time.sleep, which scan.py reads)
from datetime import datetime, timezone
from pathlib import Path

# Allow `python3 /path/to/skillguard/cli.py` to run standalone — the hook prints
# exactly that as its fallback scan command for plugin-only installs, where the
# package isn't pip-installed. Running a file puts only its own dir on sys.path,
# so add the repo root before importing sibling modules.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skillguard import config, store  # noqa: F401  (store: patch seam for cli.store.*)
from skillguard._util import atomic_write_json as _atomic_write_json
from skillguard.args import build_parser
from skillguard.cache import (
    write_ack_cache,
    write_cache,
    write_skip_cache,
)
from skillguard.commands import (
    _dispatch_early_exit,
    log_activity,
)
from skillguard.discovery import discover_skills
from skillguard.engines import (
    ENGINE_REGISTRY,
    CiscoEngine,
    LocalEngine,
    SkillAuditEngine,
    SnykEngine,
    _build_engines,
    resolve_engine_names,
)
from skillguard.mcp import (
    McpConfigEngine,
    discover_mcps,
    introspect,
    materialize_surface,
    write_introspection_surface,
)
from skillguard.model import (
    Engine,
    Finding,
    SkillInfo,
    normalize_severity,
)
from skillguard.paths import (
    MCP_CACHE_SUBDIR,
)
from skillguard.patterns import LOCAL_PATTERNS
from skillguard.render.colors import dim, reset
from skillguard.render.reports import (
    report_json,
    report_markdown,
    report_quiet,
    report_table,
)
from skillguard.scan import _dedupe_mcp_findings, run_scan_pipeline
from skillguard.triage import (
    apply_triage,
    finding_fingerprint,
    load_triage,
    mark_fp_command,
    save_triage,
    unmark_fp_command,
)

# ─── Constants ───────────────────────────────────────────────────────────────

__version__ = "0.3.2"

CACHE_DIR = config.default_cache_dir()

# The public surface of the facade: every name the package decomposition moved
# out is re-imported above and re-exported here so `from skillguard.cli import X`
# (used by tests and hook.py) keeps working. Listing them in __all__ also marks
# the re-export-only ones as intentionally exported (not dead imports).
__all__ = [
    "__version__",
    "CACHE_DIR",
    "Engine",
    "Finding",
    "SkillInfo",
    "normalize_severity",
    "LocalEngine",
    "CiscoEngine",
    "SkillAuditEngine",
    "SnykEngine",
    "McpConfigEngine",
    "ENGINE_REGISTRY",
    "resolve_engine_names",
    "_build_engines",
    "LOCAL_PATTERNS",
    "discover_skills",
    "discover_mcps",
    "write_cache",
    "write_skip_cache",
    "write_ack_cache",
    "_atomic_write_json",
    "apply_triage",
    "finding_fingerprint",
    "load_triage",
    "save_triage",
    "mark_fp_command",
    "unmark_fp_command",
    "report_table",
    "report_json",
    "report_markdown",
    "report_quiet",
    "_dedupe_mcp_findings",
    "run_scan_pipeline",
    "log_activity",
]


# ─── Data Types ──────────────────────────────────────────────────────────────
# Finding, SkillInfo, and SEVERITY_ORDER now live in skillguard.model (so the
# MCP scanner can share them without a circular import). They are imported at
# the top of this module and re-exported here, so existing callers and tests
# that do `from skillguard.cli import Finding, SkillInfo` keep working.


# ─── Main ────────────────────────────────────────────────────────────────────


def run_scan(args: argparse.Namespace) -> int:
    """Discover targets, build engines, optionally introspect, run the scan
    pipeline, log the run, and print the report. Returns the process exit code."""
    project_dir = Path.cwd()

    # ── Decide what kinds to scan ────────────────────────────────────────────
    if args.target is None:
        if args.skill and not args.mcp:
            want_skills, want_mcps = True, False
        elif args.mcp and not args.skill:
            want_skills, want_mcps = False, True
        else:
            want_skills, want_mcps = True, True
    else:
        want_skills = args.target in ("skills", "all")
        want_mcps = args.target in ("mcps", "all")

    # ── Engines ──────────────────────────────────────────────────────────────
    engine_names = resolve_engine_names(args.engines)
    engines, engine_names_used = _build_engines(engine_names, args.quiet)

    # ── Discover + materialize targets ───────────────────────────────────────
    targets: list[SkillInfo] = []
    if want_skills:
        targets += discover_skills(args.scope, project_dir, single_skill=args.skill)
    mcp_targets: list[SkillInfo] = []
    if want_mcps:
        servers = discover_mcps(
            args.scope, project_dir, single=args.mcp, include_plugins=not args.no_plugins
        )
        mcp_base = CACHE_DIR / MCP_CACHE_SUBDIR
        for srv in servers:
            mcp_targets.append(materialize_surface(srv, mcp_base))
        targets += mcp_targets

    # The MCP structural engine always runs for MCP targets (it is the core MCP
    # analysis); it is a no-op for skills, so adding it is harmless.
    if mcp_targets:
        engines.append(McpConfigEngine())
        engine_names_used.append("mcp")

    if not engines:
        print("No engines available. At minimum, use --engines local", file=sys.stderr)
        return 1
    if not targets:
        if args.skill:
            what = f"skill named '{args.skill}'"
        elif args.mcp:
            what = f"MCP server named '{args.mcp}'"
        elif want_mcps and not want_skills:
            what = "MCP servers"
        elif want_skills and not want_mcps:
            what = "skills"
        else:
            what = "targets"
        print(f"No {what} found in {args.scope} scope", file=sys.stderr)
        return 1

    # ── Opt-in live introspection (executes servers) ─────────────────────────
    if args.mcp_introspect and mcp_targets:
        if not args.quiet:
            print(
                f"{dim()}⚠ --mcp-introspect LAUNCHES each MCP server to read its tool "
                f"descriptions/instructions. Only do this for servers you trust.{reset()}",
                file=sys.stderr,
            )
        for t in mcp_targets:
            srv = t.extra["mcp"]
            intro = introspect(srv, allow_local=args.allow_local)
            if intro.get("ok"):
                write_introspection_surface(t, intro)
            elif not args.quiet:
                # A deliberately-requested introspection that fails must be
                # visible — not buried in the activity log, which the toggle can
                # silence. stderr so it never corrupts json/markdown on stdout.
                print(
                    f"⚠ introspection of {srv.name} failed: {intro.get('error')}", file=sys.stderr
                )
            log_activity(
                actor="user",
                action="introspect",
                target_kind="mcp",
                target_name=srv.name,
                outcome="ok" if intro.get("ok") else "error",
                detail=(intro.get("error") or f"{len(intro.get('tools', []))} tool(s) read"),
            )

    # ── Scan ─────────────────────────────────────────────────────────────────
    scan_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = len(targets)
    target_kind_label = "all" if want_skills and want_mcps else "mcps" if want_mcps else "skills"
    total_findings, worst = run_scan_pipeline(
        targets,
        engines,
        engine_names_used,
        scope=args.scope,
        target_kind_label=target_kind_label,
        quiet=args.quiet,
        fmt=args.format,
    )

    # One activity entry summarizing the run (gated by the toggle).
    log_activity(
        actor="user",
        action="scan",
        target_kind=target_kind_label if total > 1 else (targets[0].kind if targets else None),
        target_name=(targets[0].name if total == 1 else None),
        outcome="findings" if total_findings else "clean",
        severity=worst if worst != "clean" else None,
        detail=f"{total} target(s) scanned, {total_findings} active finding(s)",
        metadata={"engines": engine_names_used, "scope": args.scope, "kind": target_kind_label},
    )

    # ── Report ───────────────────────────────────────────────────────────────
    if args.quiet:
        report_quiet(targets)
    elif args.format == "json":
        report_json(targets, engine_names_used, scan_time)
    elif args.format == "markdown":
        report_markdown(targets, engine_names_used, scan_time, verbose=args.verbose)
    else:
        report_table(targets, engine_names_used, scan_time, verbose=args.verbose)
    return 0


def main() -> None:
    parser = build_parser()
    parser.add_argument("--version", action="version", version=f"skillguard {__version__}")
    args = parser.parse_args()
    code = _dispatch_early_exit(args)
    if code is None:
        code = run_scan(args)
    # A successful run (code 0) returns normally so in-process callers (tests that
    # drive main() and assert afterward) aren't interrupted by SystemExit; only a
    # nonzero status raises. Running as a script then exits 0 by falling off the end.
    if code:
        sys.exit(code)


if __name__ == "__main__":
    main()
