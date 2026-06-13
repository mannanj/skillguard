"""The curl installer (install.sh) must stay in sync with the plugin.

Two ways install.sh has silently diverged from the plugin before:

  1. It fetched only cli.py/hook.py/__init__.py on a remote install, so when
     cli.py grew top-level imports of config/mcp/model/store, a remote curl
     install imported nothing — the scanner was DOA.
  2. It registered only the ``Skill`` PreToolUse matcher, while the plugin's
     hooks.json gates both ``Skill`` and ``mcp__.*``. Curl-installer users got
     skill gating but no MCP gating at all.

Both gaps are invisible at runtime until a user on that install path hits them.
These tests fail in CI the moment install.sh drifts from the package modules or
the plugin's matcher set.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = (ROOT / "install.sh").read_text()


def test_remote_fetch_lists_every_package_module():
    """Every skillguard/*.py module must be in install.sh's remote-fetch loop,
    or a remote curl install ships an incomplete package that fails to import."""
    modules = {p.name for p in (ROOT / "skillguard").glob("*.py")}
    assert modules, "no package modules found — wrong ROOT?"
    missing = [m for m in sorted(modules) if m not in INSTALL_SH]
    assert not missing, (
        f"install.sh does not fetch these package modules on remote install: {missing}. "
        f"Add them to the `for f in ...` loop."
    )


def test_registers_every_plugin_matcher():
    """install.sh must register the same PreToolUse matchers as the plugin's
    hooks.json, so the curl install gates exactly what the plugin gates."""
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    matchers = [e["matcher"] for e in hooks["hooks"]["PreToolUse"]]
    assert "Skill" in matchers and "mcp__.*" in matchers, "hooks.json lost a matcher"
    missing = [m for m in matchers if m not in INSTALL_SH]
    assert not missing, (
        f"install.sh does not register these matchers that the plugin gates: {missing}. "
        f"Keep the matcher tuple in install.sh in sync with hooks/hooks.json."
    )
