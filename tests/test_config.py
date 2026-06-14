"""Tests for SkillGuard settings (skillguard/config.py): the activity-logging
toggle and the MCP hook policy, including env-over-file-over-default precedence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillguard import config

# ── activity_logging ──────────────────────────────────────────────────────────


def test_activity_logging_defaults_on(tmp_path: Path):
    assert config.activity_logging_enabled(tmp_path) is True


def test_set_activity_logging_persists(tmp_path: Path):
    config.set_activity_logging(False, tmp_path)
    assert config.activity_logging_enabled(tmp_path) is False
    config.set_activity_logging(True, tmp_path)
    assert config.activity_logging_enabled(tmp_path) is True


def test_env_overrides_persisted_logging(tmp_path: Path, monkeypatch):
    config.set_activity_logging(True, tmp_path)  # persisted ON
    monkeypatch.setenv("SKILLGUARD_ACTIVITY_LOG", "off")
    assert config.activity_logging_enabled(tmp_path) is False
    monkeypatch.setenv("SKILLGUARD_ACTIVITY_LOG", "0")
    assert config.activity_logging_enabled(tmp_path) is False
    monkeypatch.setenv("SKILLGUARD_ACTIVITY_LOG", "on")
    assert config.activity_logging_enabled(tmp_path) is True


def test_invalid_env_value_falls_back_to_file(tmp_path: Path, monkeypatch):
    config.set_activity_logging(False, tmp_path)
    monkeypatch.setenv("SKILLGUARD_ACTIVITY_LOG", "maybe")  # unrecognized → ignore env
    assert config.activity_logging_enabled(tmp_path) is False


# ── mcp_policy ────────────────────────────────────────────────────────────────


def test_mcp_policy_defaults_warn(tmp_path: Path):
    assert config.mcp_policy(tmp_path) == "warn"


def test_set_mcp_policy_persists(tmp_path: Path):
    config.set_mcp_policy("enforce", tmp_path)
    assert config.mcp_policy(tmp_path) == "enforce"
    config.set_mcp_policy("off", tmp_path)
    assert config.mcp_policy(tmp_path) == "off"


def test_mcp_policy_env_override(tmp_path: Path, monkeypatch):
    config.set_mcp_policy("off", tmp_path)
    monkeypatch.setenv("SKILLGUARD_MCP_POLICY", "enforce")
    assert config.mcp_policy(tmp_path) == "enforce"


def test_set_mcp_policy_rejects_garbage(tmp_path: Path):
    with pytest.raises(ValueError):
        config.set_mcp_policy("nonsense", tmp_path)


def test_settings_file_corruption_is_tolerated(tmp_path: Path):
    config.settings_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    config.settings_path(tmp_path).write_text("{ broken json :::")
    # Falls back to defaults rather than raising.
    assert config.activity_logging_enabled(tmp_path) is True
    assert config.mcp_policy(tmp_path) == "warn"


def test_settings_coexist(tmp_path: Path):
    """Two settings in the same file don't clobber each other."""
    config.set_activity_logging(False, tmp_path)
    config.set_mcp_policy("enforce", tmp_path)
    assert config.activity_logging_enabled(tmp_path) is False
    assert config.mcp_policy(tmp_path) == "enforce"
