#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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


def write_file(rel: str, text: str) -> None:
    dst = OUT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text)


def main() -> None:
    from skillguard.agent_skill import agent_skill_source, claude_command_source, quoted_command
    from skillguard.shell_integration import codex_plugin_manifest

    if OUT.exists():
        shutil.rmtree(OUT)
    for rel in ALLOW_FILES:
        if (ROOT / rel).exists():
            copy_file(rel)
    if (ROOT / "commands").exists():
        shutil.copytree(ROOT / "commands", OUT / "commands")
    if (ROOT / "skills").exists():
        shutil.copytree(ROOT / "skills", OUT / "skills")
    shutil.copytree(ROOT / "skillguard", OUT / "skillguard")
    plugin_cli = quoted_command("${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py")
    write_file(
        "commands/skillguard.md",
        claude_command_source(
            plugin_cli,
            allowed_tools_command="${CLAUDE_PLUGIN_ROOT}/skillguard/cli.py",
        ),
    )
    write_file("skills/skillguard/SKILL.md", agent_skill_source(plugin_cli))
    write_file(
        ".codex-plugin/plugin.json",
        json.dumps(codex_plugin_manifest(), indent=2) + "\n",
    )
    for junk in OUT.rglob("__pycache__"):
        shutil.rmtree(junk)
    print(f"built {OUT}")


if __name__ == "__main__":
    main()
