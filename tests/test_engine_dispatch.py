"""Plan 005: the scan dispatcher honors ``inter_target_delay`` generically.

Before plan 005 the scan loop special-cased ``engine.name == "skillaudit"`` to
sleep ``SKILLAUDIT_DELAY`` between targets. The delay is now a per-engine
attribute, so *any* engine declaring ``inter_target_delay > 0`` is throttled — by
attribute, never by name. These tests drive ``main()`` in-process with discovery
and the history DB stubbed (the same seams test_scan_lifecycle uses) and assert
the recorded sleeps come from the engine's own delay value.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import skillguard.cli as cli
from skillguard.cli import SkillInfo


class _FakeConn:
    def close(self) -> None:  # the scan loop's finally always closes its handle
        pass


class _DelayEngine:
    """A non-skillaudit engine carrying a distinctive per-target delay sentinel."""

    name = "slowfake"  # deliberately NOT "skillaudit"
    available = True
    inter_target_delay = 0.123  # a value no real engine uses

    def scan(self, target):
        return []


def _skill(tmp_path: Path, name: str) -> SkillInfo:
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n# hi\n")
    return SkillInfo(name=name, path=d, scope="global")


@pytest.fixture
def two_target_scan(tmp_path, monkeypatch):
    """Reach main()'s scan loop with two skill targets, history DB stubbed."""
    monkeypatch.setattr(cli, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(
        cli, "discover_skills", lambda *a, **k: [_skill(tmp_path, "one"), _skill(tmp_path, "two")]
    )
    monkeypatch.setattr(cli, "discover_mcps", lambda *a, **k: [])
    monkeypatch.setattr(cli, "log_activity", lambda *a, **k: None)
    monkeypatch.setattr(cli.store, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(cli.store, "start_scan_run", lambda *a, **k: 1)
    monkeypatch.setattr(cli.store, "record_scan", lambda *a, **k: None)
    monkeypatch.setattr(cli.store, "finish_scan_run", lambda *a, **k: None)


def test_dispatch_sleeps_by_engine_attribute_not_name(two_target_scan, monkeypatch):
    """An engine named 'slowfake' (NOT 'skillaudit') with a positive delay must
    still throttle between targets — proving the loop reads the attribute, not a
    hard-coded engine name. The pre-005 code would never sleep here."""
    slept: list[float] = []
    monkeypatch.setattr(cli.time, "sleep", lambda secs: slept.append(secs))
    monkeypatch.setitem(cli.ENGINE_REGISTRY, "slowfake", _DelayEngine)

    monkeypatch.setattr(
        sys, "argv", ["skillguard", "--target", "skills", "--engines", "slowfake", "--quiet"]
    )
    cli.main()

    # Two targets → exactly one inter-target gap, slept for the engine's own delay.
    assert slept == [_DelayEngine.inter_target_delay]


def test_zero_delay_engine_never_sleeps(two_target_scan, monkeypatch):
    """An engine with ``inter_target_delay == 0`` (e.g. the real LocalEngine) must
    introduce no sleep at all — guards the truthiness check in the dispatcher."""
    slept: list[float] = []
    monkeypatch.setattr(cli.time, "sleep", lambda secs: slept.append(secs))

    monkeypatch.setattr(
        sys, "argv", ["skillguard", "--target", "skills", "--engines", "local", "--quiet"]
    )
    cli.main()

    assert slept == []
