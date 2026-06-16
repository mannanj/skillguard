#!/bin/sh
# SkillGuard installer — fallback path for setups not using the Claude Code plugin system.
# Preferred install:   /plugin marketplace add mannanj/skillguard
#                      /plugin install skillguard@skillguard
#
# What this script does (and nothing else):
#   1. Copies the skillguard package to ~/.claude/skillguard/
#   2. Registers the PreToolUse hook in ~/.claude/settings.json (atomic, via python3)
#   3. Adds a ~/.local/bin/skillguard shim for terminal use
#   4. Adds a small zsh integration so `codex`/`claude` show cached findings first
#   5. Backs up settings.json first
set -eu

REPO="https://github.com/mannanj/skillguard"
DEST="$HOME/.claude/skillguard"
SETTINGS="$HOME/.claude/settings.json"
BIN_DIR="$HOME/.local/bin"
SHIM="$BIN_DIR/skillguard"
ZSHRC="$HOME/.zshrc"
SHELL_INTEGRATION="$DEST/shell.sh"

command -v python3 >/dev/null 2>&1 || { echo "python3 is required"; exit 1; }

echo "→ Installing SkillGuard to $DEST"
mkdir -p "$DEST"

# Every package module the scanner imports, as a path relative to skillguard/.
# cli.py imports the whole package tree (engines/, render/, and the top-level
# helpers) at import time, so ALL of these must be present or a curl install
# imports nothing and the scanner is DOA. Sub-package files are listed by their
# relative path. Keep this list in sync with skillguard/**/*.py — enforced by
# tests/test_install_sync.py, which fails CI the moment it drifts.
MODULES="
__init__.py
_util.py
args.py
cli.py
hook.py
config.py
branding.py
model.py
store.py
mcp/__init__.py
mcp/model.py
mcp/discovery.py
mcp/secrets.py
mcp/launch.py
mcp/rules.py
mcp/materialize.py
mcp/engine.py
mcp/introspect.py
patterns.py
discovery.py
paths.py
cache.py
triage.py
commands.py
scan.py
engines/__init__.py
engines/local.py
engines/cisco.py
engines/skillaudit.py
engines/snyk.py
render/__init__.py
render/colors.py
render/summary.py
render/reports.py
"

if [ -d "${SKILLGUARD_SRC:-}" ]; then
    # Local install (from a cloned repo): SKILLGUARD_SRC=. sh install.sh
    for f in $MODULES; do
        mkdir -p "$DEST/$(dirname "$f")"
        cp "$SKILLGUARD_SRC/skillguard/$f" "$DEST/$f"
    done
else
    # Remote install: fetch every package module from the main branch, recreating
    # the sub-package directory layout (engines/, render/) under $DEST.
    for f in $MODULES; do
        python3 -c "
import urllib.request
from pathlib import Path
dest = Path('$DEST/$f')
dest.parent.mkdir(parents=True, exist_ok=True)
urllib.request.urlretrieve('$REPO/raw/main/skillguard/$f', str(dest))
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

# Idempotent and self-healing: drop any prior skillguard entries, then add the
# current matcher set. This keeps the curl install in sync with the plugin's
# hooks.json (which gates BOTH `Skill` and `mcp__.*`) even on re-run/upgrade —
# an older install that registered only `Skill` gains MCP gating here.
def _is_ours(entry):
    return any(
        "skillguard" in h.get("command", "") and "hook.py" in h.get("command", "")
        for h in entry.get("hooks", [])
    )

pre[:] = [e for e in pre if not _is_ours(e)]
for matcher in ("Skill", "mcp__.*"):
    pre.append({
        "matcher": matcher,
        "hooks": [{"type": "command", "command": hook_cmd}],
    })

settings_path.parent.mkdir(parents=True, exist_ok=True)
tmp = settings_path.with_suffix(f".tmp.{os.getpid()}")
tmp.write_text(json.dumps(settings, indent=2) + "\n")
tmp.replace(settings_path)
print("  hook registered")
PYEOF

echo "→ Adding skillguard command to $SHIM"
mkdir -p "$BIN_DIR"
cat > "$SHIM" <<'SHEOF'
#!/bin/sh
exec python3 "$HOME/.claude/skillguard/cli.py" "$@"
SHEOF
chmod 755 "$SHIM"

echo "→ Installing codex/claude launch summary integration"
cat > "$SHELL_INTEGRATION" <<'SHEOF'
# SkillGuard shell integration. Sourced by ~/.zshrc.
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

_skillguard_agent_summary() {
  [ "${SKILLGUARD_AGENT_SUMMARY:-1}" = "0" ] && return 0
  if command -v skillguard >/dev/null 2>&1; then
    command skillguard --agent-summary 2>/dev/null || true
  elif [ -x "$HOME/.local/bin/skillguard" ]; then
    "$HOME/.local/bin/skillguard" --agent-summary 2>/dev/null || true
  fi
}

claude() {
  _skillguard_agent_summary
  command claude "$@"
}

codex() {
  _skillguard_agent_summary
  command codex "$@"
}
SHEOF

touch "$ZSHRC"
if ! grep -F "# >>> skillguard >>>" "$ZSHRC" >/dev/null 2>&1; then
    {
        printf '\n# >>> skillguard >>>\n'
        printf 'source "$HOME/.claude/skillguard/shell.sh"\n'
        printf '# <<< skillguard <<<\n'
    } >> "$ZSHRC"
    echo "  added SkillGuard shell integration to $ZSHRC"
else
    echo "  SkillGuard shell integration already present in $ZSHRC"
fi

echo "→ Done. Scan your skills now:"
echo "    skillguard --engines local"
echo "  Unscanned skills will be blocked the next time Claude tries to use them."
