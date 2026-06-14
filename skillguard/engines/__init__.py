#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Content scan engines and the engine registry.

``ENGINE_REGISTRY`` is the single source of truth for "what content engines
exist". Adding an engine is one entry here plus the engine class. ``cli``
re-exports these names (and the four engine classes) so
``from skillguard.cli import LocalEngine, ENGINE_REGISTRY, _build_engines, ...``
keeps working — and so that ``cli.CiscoEngine`` / ``cli.ENGINE_REGISTRY``, which
tests monkeypatch, are these exact objects.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from skillguard.engines.cisco import CiscoEngine
from skillguard.engines.local import LocalEngine
from skillguard.engines.skillaudit import SkillAuditEngine
from skillguard.engines.snyk import SnykEngine
from skillguard.model import Engine
from skillguard.render.colors import dim, reset

__all__ = [
    "LocalEngine",
    "CiscoEngine",
    "SkillAuditEngine",
    "SnykEngine",
    "ENGINE_REGISTRY",
    "resolve_engine_names",
    "_build_engines",
]

# The single source of truth for "what content engines exist". Adding an engine
# is one entry here (plus the engine class itself): `_build_engines`, the
# `--engines all` expansion, and `resolve_engine_names` all derive from this map,
# so there is no second list to keep in sync. `McpConfigEngine` is deliberately
# NOT registered — it is the structural MCP analyzer that `main()` appends only
# when MCP targets exist (a no-op on skills), never a user-selectable engine.

ENGINE_REGISTRY: dict[str, Callable[[], Engine]] = {
    "local": LocalEngine,
    "cisco": CiscoEngine,
    "skillaudit": SkillAuditEngine,
    "snyk": SnykEngine,
}


def resolve_engine_names(spec: str) -> list[str]:
    """Expand an ``--engines`` argument into a list of engine names.

    ``"all"`` expands to every registered engine in registry order; any other
    value is a comma-separated selection trimmed of surrounding whitespace.
    Unknown names are not rejected here — ``_build_engines`` validates them so the
    error names the offender.
    """
    if spec == "all":
        return list(ENGINE_REGISTRY)
    return [e.strip() for e in spec.split(",")]


def _build_engines(engine_names: list[str], quiet: bool) -> tuple[list[Engine], list[str]]:
    """Instantiate the requested engines, skipping any that are unavailable.

    Fully data-driven over ``ENGINE_REGISTRY``: each requested name is looked up,
    instantiated, and kept only if it reports ``available``. An unavailable engine
    is announced (unless quiet) via its own ``unavailable_hint``; an unknown name
    is a hard error (exit 1). Returns ``(engines, names-actually-used)``.
    """
    engines: list[Engine] = []
    used: list[str] = []
    for name in engine_names:
        factory = ENGINE_REGISTRY.get(name)
        if factory is None:
            print(f"Unknown engine: {name}", file=sys.stderr)
            sys.exit(1)
        engine = factory()
        if engine.available:
            engines.append(engine)
            used.append(name)
        elif not quiet:
            hint = getattr(engine, "unavailable_hint", "")
            print(f"{dim()}[skip] {hint}{reset()}", file=sys.stderr)
    return engines, used
