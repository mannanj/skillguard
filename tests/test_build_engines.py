"""Characterization tests for the engine selector ``_build_engines``.

Pins the (engines, used) contract:
- ``local`` and ``skillaudit`` are always selected (no availability gate);
- ``cisco`` and ``snyk`` are gated on ``.available`` and silently skipped when
  absent (in quiet mode);
- an unknown engine name exits 1.

The skip-when-unavailable test forces *both* gated engines unavailable so it is
deterministic regardless of whether ``cisco-ai-skill-scanner`` happens to be
installed in the test environment. A separate test pins the available-engine
path by forcing cisco available.
"""

from __future__ import annotations

import pytest

from skillguard import cli
from skillguard.cli import _build_engines
from skillguard.model import Engine


def test_local_always_selected():
    engines, used = _build_engines(["local"], quiet=True)
    assert used == ["local"]
    assert len(engines) == 1


def test_skillaudit_always_selected():
    # skillaudit is ungated: it must always appear, no token/binary required.
    engines, used = _build_engines(["local", "skillaudit"], quiet=True)
    assert used == ["local", "skillaudit"]


def test_unknown_engine_exits_1():
    with pytest.raises(SystemExit) as e:
        _build_engines(["bogus"], quiet=True)
    assert e.value.code == 1


def test_unavailable_engines_skipped(monkeypatch):
    """Gated engines whose ``.available`` is False are dropped from ``used``.

    Forced deterministic: CiscoEngine instances report unavailable (no-op
    ``__init__`` leaves the class default ``available = False``) and SNYK_TOKEN
    is unset so SnykEngine.available is False.
    """
    monkeypatch.setattr(cli.CiscoEngine, "__init__", lambda self: None)
    monkeypatch.setattr(cli.CiscoEngine, "available", False, raising=False)
    monkeypatch.delenv("SNYK_TOKEN", raising=False)

    engines, used = _build_engines(["local", "cisco", "snyk"], quiet=True)
    assert used == ["local"]
    assert len(engines) == 1


def test_available_gated_engine_included(monkeypatch):
    """When a gated engine IS available, it is included in ``used``."""
    monkeypatch.setattr(cli.CiscoEngine, "__init__", lambda self: None)
    monkeypatch.setattr(cli.CiscoEngine, "available", True, raising=False)

    engines, used = _build_engines(["local", "cisco"], quiet=True)
    assert used == ["local", "cisco"]
    assert len(engines) == 2


# ─── Engine protocol + registry (plan 005) ──────────────────────────────────

EXPECTED_ENGINES = ["local", "cisco", "skillaudit", "snyk"]


def test_registry_lists_exactly_the_known_engines():
    """The registry is the single source of truth for what engines exist; pin
    its membership AND order — the order is what ``--engines all`` expands to."""
    assert list(cli.ENGINE_REGISTRY) == EXPECTED_ENGINES


def test_all_expands_to_the_registry_keys():
    """``--engines all`` resolves to the registry keys, not a separate list."""
    assert cli.resolve_engine_names("all") == list(cli.ENGINE_REGISTRY)
    assert cli.resolve_engine_names("all") == EXPECTED_ENGINES


def test_all_tracks_the_registry_dynamically(monkeypatch):
    """``all`` is DERIVED from the registry, not a frozen copy: a newly
    registered engine must show up in the expansion (guards against re-introducing
    a hand-maintained ``["local", "cisco", ...]`` list)."""
    monkeypatch.setitem(cli.ENGINE_REGISTRY, "zzfake", cli.LocalEngine)
    assert cli.resolve_engine_names("all")[-1] == "zzfake"
    assert cli.resolve_engine_names("all") == list(cli.ENGINE_REGISTRY)


def test_explicit_engine_spec_is_split_and_trimmed():
    assert cli.resolve_engine_names("local, snyk ") == ["local", "snyk"]


def test_registered_engines_satisfy_the_protocol():
    """Every registered factory must build something the dispatcher can drive:
    name / available / inter_target_delay / scan — i.e. a structural ``Engine``."""
    for name, factory in cli.ENGINE_REGISTRY.items():
        assert isinstance(factory(), Engine), f"{name!r} does not satisfy the Engine protocol"


def test_mcp_engine_satisfies_the_protocol():
    """``McpConfigEngine`` is intentionally NOT registered (it is target-gated and
    appended by ``main()``), but the same dispatcher reads its
    ``inter_target_delay`` — so it must conform too, or MCP scans would crash."""
    assert isinstance(cli.McpConfigEngine(), Engine)


def test_engine_protocol_is_not_vacuous():
    """A class missing the engine members must NOT pass the check — proves the
    ``isinstance`` assertions above actually discriminate (catches a protocol that
    accidentally requires nothing)."""

    class NotAnEngine:
        name = "nope"

    assert not isinstance(NotAnEngine(), Engine)
