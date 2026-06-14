#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Single source of truth for SkillGuard's name and the identifiers derived from it.

Everything the product is *called* in a functional sense derives from ``APP_NAME``
here: the import/dist package name, the CLI command, the on-disk cache directory,
the history-DB filename, and the environment-variable namespace. Renaming the
product (e.g. SkillGuard -> Portcullis) is therefore an edit to THIS file plus the
two out-of-package declarations that cannot import it -- ``pyproject.toml``
(``[project.scripts]`` + ``name``) and ``install.sh`` (the ``$DEST`` path).

Two deliberate carve-outs, each pinned by a test so it cannot silently drift:
  * ``hook.py`` mirrors ``CACHE_DIR_NAME`` / ``DB_NAME`` as inline literals -- it
    runs as a standalone script and must resolve its cache path even when the
    ``skillguard`` package cannot be imported, so it cannot import this module.
    See ``tests/test_branding.py::test_hook_mirrors_branding``.
  * Human-facing display strings (the capitalized "SkillGuard", README, landing
    copy) are prose, not functional identifiers, and are intentionally not
    centralized here.

Migration note for a future rename: flipping ``APP_NAME`` also moves the cache dir
and the ``SKILLGUARD_*`` env namespace, which orphans an existing
``~/.claude/skillguard-cache`` and any env vars users have set. Handle that in the
rename plan (read-through to the old dir, or a one-time move); it is out of scope
for this naming seam.

This module has no internal imports, so it is safe to import from anywhere --
including the dependency-light hook/config contexts -- with no circular-import risk.
"""

from __future__ import annotations

APP_NAME = "skillguard"
CACHE_DIR_NAME = f"{APP_NAME}-cache"
DB_NAME = f"{APP_NAME}.db"
ENV_PREFIX = f"{APP_NAME.upper()}_"
