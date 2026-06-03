# SkillGuard demo — scan a malicious skill, then show the hook blocking an unscanned one.
# Render: vhs demo/demo.tape  (run from repo root)

Output demo/demo.gif
Output demo/demo.mp4

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 660
Set Padding 20
Set Theme { "name": "skillguard", "background": "#0B0E14", "foreground": "#e6edf3", "cursor": "#3DDC97", "black": "#0B0E14", "red": "#FF5C5C", "green": "#3DDC97", "yellow": "#FFB454", "blue": "#79c0ff", "magenta": "#d2a8ff", "cyan": "#56d4dd", "white": "#e6edf3", "brightBlack": "#6e7681", "brightRed": "#FF5C5C", "brightGreen": "#3DDC97", "brightYellow": "#FFB454", "brightBlue": "#79c0ff", "brightMagenta": "#d2a8ff", "brightCyan": "#56d4dd", "brightWhite": "#ffffff" }

Hide
Type "export HOME=$PWD/demo/fixture-home"
Enter
Type `skillguard() { python3 skillguard/cli.py "$@"; }`
Enter
Type "skillguard-hook() { python3 skillguard/hook.py; }"
Enter
Type "export PS1='$ '"
Enter
Type "clear"
Enter
Show

Sleep 600ms
Type@40ms "skillguard --skill pretty-formatter"
Sleep 500ms
Enter
Sleep 5.5s

Type@40ms "# unscanned skills never reach Claude — the hook refuses them:"
Sleep 400ms
Enter
Type@40ms `echo '{"tool_input":{"skill":"sketchy-skill"}}' | skillguard-hook`
Sleep 500ms
Enter
Sleep 4s
