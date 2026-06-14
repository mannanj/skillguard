#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Pin the naming authority (``skillguard.branding``).

These tests are why a future product rename (e.g. SkillGuard -> Portcullis) is a
one-file edit instead of a scattered find-and-replace: they prove every functional
identifier — cache dir, history-DB filename, env-var prefix — is built from
``branding``, and that the one unavoidable duplicate (hook.py's standalone mirror)
cannot silently drift.
"""

from __future__ import annotations

import ast
from pathlib import Path

from skillguard import branding, config, store


def test_current_values_are_the_rename_tripwire():
    # Changing any of these is a deliberate rename. If you flip APP_NAME you must
    # update this test AND read branding.py's migration note (the cache dir and the
    # SKILLGUARD_* env vars move, orphaning existing user state).
    assert branding.APP_NAME == "skillguard"
    assert branding.CACHE_DIR_NAME == "skillguard-cache"
    assert branding.DB_NAME == "skillguard.db"
    assert branding.ENV_PREFIX == "SKILLGUARD_"


def test_identifiers_derive_from_app_name():
    assert branding.CACHE_DIR_NAME == f"{branding.APP_NAME}-cache"
    assert branding.DB_NAME == f"{branding.APP_NAME}.db"
    assert branding.ENV_PREFIX == f"{branding.APP_NAME.upper()}_"


def test_config_cache_dir_built_from_branding():
    cache = config.default_cache_dir()
    assert cache == Path.home() / ".claude" / branding.CACHE_DIR_NAME
    assert cache.name == branding.CACHE_DIR_NAME


def test_store_db_path_built_from_branding():
    db = store.default_db_path()
    assert db.name == branding.DB_NAME
    assert db.parent.name == branding.CACHE_DIR_NAME


def test_env_overrides_use_the_prefix(monkeypatch, tmp_path):
    # Proves config reads env vars built from ENV_PREFIX, not hardcoded literals.
    monkeypatch.setenv(f"{branding.ENV_PREFIX}MCP_POLICY", "enforce")
    assert config.mcp_policy(tmp_path) == "enforce"
    monkeypatch.setenv(f"{branding.ENV_PREFIX}ACTIVITY_LOG", "off")
    assert config.activity_logging_enabled(tmp_path) is False


def test_hook_mirrors_branding():
    # hook.py runs standalone and import-guards the package, so it cannot import
    # branding; it mirrors the names as inline literals. Pin them against branding
    # so a rename can't let the hook's cache path drift from the rest of the tool.
    import skillguard.hook as hook

    assert hook.CACHE_DIR.name == branding.CACHE_DIR_NAME
    assert hook.DB_NAME == branding.DB_NAME


def test_cache_dir_name_is_a_literal_only_in_branding_and_hook():
    # Anti-regression ratchet: the cache-dir name may appear as a *string literal*
    # only in branding.py (the authority) and hook.py (the documented standalone
    # mirror). Anywhere else, code must build it from branding.CACHE_DIR_NAME. The
    # AST check matches whole string constants, so docstrings mentioning the path
    # as a substring are not flagged.
    pkg = Path(branding.__file__).resolve().parent
    allowed = {"branding.py", "hook.py"}
    offenders = []
    for py in sorted(pkg.rglob("*.py")):
        if "__pycache__" in py.parts or py.name in allowed:
            continue
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == branding.CACHE_DIR_NAME:
                offenders.append(py.relative_to(pkg).as_posix())
    assert not offenders, (
        f"cache-dir name is a string literal outside branding.py/hook.py in "
        f"{sorted(set(offenders))} — build it from branding.CACHE_DIR_NAME instead."
    )
