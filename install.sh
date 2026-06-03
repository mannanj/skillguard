#!/bin/sh
# SkillGuard installer — fallback path for setups not using the Claude Code plugin system.
# Preferred install:   /plugin marketplace add mannanj/skillguard
#                      /plugin install skillguard@skillguard
#
# What this script does (and nothing else):
#   1. Copies the skillguard package to ~/.claude/skillguard/
#   2. Registers the PreToolUse hook in ~/.claude/settings.json (atomic, via python3)
#   3. Backs up settings.json first
set -eu

REPO="https://github.com/mannanj/skillguard"
DEST="$HOME/.claude/skillguard"
SETTINGS="$HOME/.claude/settings.json"

command -v python3 >/dev/null 2>&1 || { echo "python3 is required"; exit 1; }

echo "→ Installing SkillGuard to $DEST"
mkdir -p "$DEST"

if [ -d "${SKILLGUARD_SRC:-}" ]; then
    # Local install (from a cloned repo): SKILLGUARD_SRC=. sh install.sh
    cp "$SKILLGUARD_SRC"/skillguard/*.py "$DEST/"
else
    # Remote install: fetch the two package files from the main branch
    for f in cli.py hook.py __init__.py; do
        python3 -c "
import urllib.request
url = '$REPO/raw/main/skillguard/$f'
urllib.request.urlretrieve(url, '$DEST/$f')
print('  fetched', '$f')
"
    done
fi

echo "→ Registering PreToolUse hook in $SETTINGS"
python3 - "$SETTINGS" "$DEST" <<'PYEOF'
import json, shutil, sys, os
from pathlib import Path

settings_path = Path(sys.argv[1])
hook_cmd = f"python3 {sys.argv[2]}/hook.py"

settings = {}
if settings_path.exists():
    shutil.copy2(settings_path, str(settings_path) + ".skillguard-backup")
    print(f"  backed up settings to {settings_path}.skillguard-backup")
    settings = json.loads(settings_path.read_text())

hooks = settings.setdefault("hooks", {})
pre = hooks.setdefault("PreToolUse", [])

# Idempotent: skip if a skillguard hook is already registered
for entry in pre:
    for h in entry.get("hooks", []):
        if "skillguard" in h.get("command", "") and "hook.py" in h.get("command", ""):
            print("  hook already registered — nothing to do")
            sys.exit(0)

pre.append({
    "matcher": "Skill",
    "hooks": [{"type": "command", "command": hook_cmd}],
})

settings_path.parent.mkdir(parents=True, exist_ok=True)
tmp = settings_path.with_suffix(f".tmp.{os.getpid()}")
tmp.write_text(json.dumps(settings, indent=2) + "\n")
tmp.replace(settings_path)
print("  hook registered")
PYEOF

echo "→ Done. Scan your skills now:"
echo "    python3 $DEST/cli.py --engines local"
echo "  Unscanned skills will be blocked the next time Claude tries to use them."
