"""Shared pytest configuration for the SkillGuard test suite.

Adds the repository root to ``sys.path`` so ``import skillguard`` works even
when the package is not pip-installed, and exposes the fixture skill paths.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Make `import skillguard.cli` / `import skillguard.hook` resolve without install.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def malicious_skill_dir() -> Path:
    return FIXTURES_DIR / "malicious-skill"


@pytest.fixture
def clean_skill_dir() -> Path:
    return FIXTURES_DIR / "clean-skill"


@pytest.fixture
def hook_path() -> Path:
    return REPO_ROOT / "skillguard" / "hook.py"
