#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""Terminal color helpers, gated so ANSI never leaks into piped output.

Every helper consults ``color_enabled()`` at call time and returns ``""`` when
color is off — i.e. when stdout is not a TTY (output is piped or redirected) or
``NO_COLOR`` is set to a non-empty value. This keeps human-readable color for
interactive use while guaranteeing plain, machine-readable text for
``skillguard ... | cat``, ``> file``, and CI. Evaluating per call (not at import)
means one decision tracks the actual stdout in use.
"""

from __future__ import annotations

import os
import sys

_SEVERITY_COLORS = {
    "critical": "\033[91m",
    "high": "\033[93m",
    "medium": "\033[33m",
    "low": "\033[36m",
    "info": "\033[37m",
    "clean": "\033[92m",
}
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


def color_enabled() -> bool:
    """True only when writing to an interactive terminal with NO_COLOR unset.

    Follows the NO_COLOR convention (https://no-color.org): any non-empty value
    of ``NO_COLOR`` disables color; an empty value or absence does not.
    """
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def severity_color(sev: str) -> str:
    """ANSI color for a severity level, or "" when color is disabled/unknown."""
    return _SEVERITY_COLORS.get(sev, "") if color_enabled() else ""


def reset() -> str:
    return _RESET if color_enabled() else ""


def bold() -> str:
    return _BOLD if color_enabled() else ""


def dim() -> str:
    return _DIM if color_enabled() else ""
