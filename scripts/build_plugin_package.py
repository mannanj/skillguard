#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "skillguard-plugin"

ALLOW_FILES = [
    "README.md",
    "LICENSE",
    "NOTICE",
    "pyproject.toml",
    "install.sh",
    ".claude-plugin/plugin.json",
    "hooks/hooks.json",
]


def copy_file(rel: str) -> None:
    src = ROOT / rel
    dst = OUT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    for rel in ALLOW_FILES:
        if (ROOT / rel).exists():
            copy_file(rel)
    shutil.copytree(ROOT / "skillguard", OUT / "skillguard")
    for junk in OUT.rglob("__pycache__"):
        shutil.rmtree(junk)
    print(f"built {OUT}")


if __name__ == "__main__":
    main()
