#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""
SkillGuard user settings, shared by the CLI and the PreToolUse hook.

Settings resolve in this order (first hit wins):
  1. An environment variable (one-off override for a single invocation).
  2. The persistent settings file ``~/.claude/skillguard-cache/_settings.json``.
  3. A built-in default.

Two toggles live here:

  * ``activity_logging`` (default **on**) — whether SkillGuard appends to the
    activity audit log. This gates ONLY the ``activities`` table; scan history
    (what was scanned and what was found) is always preserved regardless, so
    turning logging off never loses scan data. Env override:
    ``SKILLGUARD_ACTIVITY_LOG=off``. Persist it with:
    ``skillguard --set-activity-logging off``.

  * ``mcp_policy`` (default **warn**) — how the hook treats MCP tool calls:
    ``off`` (ignore), ``warn`` (allow but warn on unscanned/risky), or
    ``enforce`` (block, symmetric with skills). Env override:
    ``SKILLGUARD_MCP_POLICY=enforce``.

This module imports only the dependency-free ``_util`` helper from the package,
so both the CLI and the dependency-light hook can use it without a circular
import.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from skillguard._util import atomic_write_json

_TRUTHY = {"1", "on", "true", "yes", "enabled"}
_FALSEY = {"0", "off", "false", "no", "disabled"}

VALID_MCP_POLICIES = ("off", "warn", "enforce")

DEFAULTS = {
    "activity_logging": True,
    "mcp_policy": "warn",
}


def default_cache_dir() -> Path:
    return Path.home() / ".claude" / "skillguard-cache"


def settings_path(cache_dir: Path | None = None) -> Path:
    return (cache_dir or default_cache_dir()) / "_settings.json"


def load_settings(cache_dir: Path | None = None) -> dict[str, Any]:
    """Read the persistent settings file, tolerating absence/corruption."""
    try:
        data = json.loads(settings_path(cache_dir).read_text())
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_settings(settings: dict[str, Any], cache_dir: Path | None = None) -> None:
    path = settings_path(cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, settings)


def _coerce_bool(value: str) -> bool | None:
    v = value.strip().lower()
    if v in _TRUTHY:
        return True
    if v in _FALSEY:
        return False
    return None


# ─── activity_logging ────────────────────────────────────────────────────────

def activity_logging_enabled(cache_dir: Path | None = None) -> bool:
    """Is the activity audit log on? Env var overrides the persisted setting."""
    env = os.environ.get("SKILLGUARD_ACTIVITY_LOG")
    if env is not None:
        coerced = _coerce_bool(env)
        if coerced is not None:
            return coerced
    return bool(load_settings(cache_dir).get("activity_logging", DEFAULTS["activity_logging"]))


def set_activity_logging(enabled: bool, cache_dir: Path | None = None) -> None:
    settings = load_settings(cache_dir)
    settings["activity_logging"] = bool(enabled)
    save_settings(settings, cache_dir)


# ─── mcp_policy ──────────────────────────────────────────────────────────────

def mcp_policy(cache_dir: Path | None = None) -> str:
    """Hook policy for MCP tool calls: off | warn | enforce."""
    env = os.environ.get("SKILLGUARD_MCP_POLICY")
    if env is not None and env.strip().lower() in VALID_MCP_POLICIES:
        return env.strip().lower()
    val = str(load_settings(cache_dir).get("mcp_policy", DEFAULTS["mcp_policy"])).lower()
    return val if val in VALID_MCP_POLICIES else DEFAULTS["mcp_policy"]


def set_mcp_policy(policy: str, cache_dir: Path | None = None) -> None:
    policy = policy.strip().lower()
    if policy not in VALID_MCP_POLICIES:
        raise ValueError(f"mcp_policy must be one of {VALID_MCP_POLICIES}, got {policy!r}")
    settings = load_settings(cache_dir)
    settings["mcp_policy"] = policy
    save_settings(settings, cache_dir)
