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
    """Every skillguard package module — top-level AND nested in sub-packages
    (engines/, render/) — must be in install.sh's fetch list by its relative path,
    or a remote curl install ships an incomplete package that fails to import.

    Recursive + path-aware: a basename match isn't enough once sub-packages exist
    (two ``__init__.py`` files, same name, different paths), so we assert the exact
    relative path (``engines/local.py``) appears in install.sh."""
    pkg = ROOT / "skillguard"
    modules = {
        p.relative_to(pkg).as_posix() for p in pkg.rglob("*.py") if "__pycache__" not in p.parts
    }
    assert modules, "no package modules found — wrong ROOT?"
    missing = [m for m in sorted(modules) if m not in INSTALL_SH]
    assert not missing, (
        f"install.sh does not fetch these package modules on remote install: {missing}. "
        f"Add them to the MODULES list (use the path relative to skillguard/)."
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
