#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Small dependency-free helpers shared across the package (atomic IO, time).

Imports nothing from the rest of ``skillguard`` so it stays safe to import from
any module without risking a circular import.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON via temp-file-then-rename so concurrent writers never leave a torn file."""
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
