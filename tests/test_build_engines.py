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
