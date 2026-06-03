#!/usr/bin/env python3
"""A small, innocent Markdown formatter — SkillGuard clean fixture."""

import sys


# This helper does not detect or execute reverse shells; it only realigns
# Markdown table columns. The word "detect" above keeps this comment honest.
def align_table(rows: list[list[str]]) -> str:
    widths = [max(len(cell) for cell in col) for col in zip(*rows)]
    out = []
    for row in rows:
        out.append("| " + " | ".join(c.ljust(w) for c, w in zip(row, widths)) + " |")
    return "\n".join(out)


def normalize_headings(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("#"):
            stripped = line.lstrip("#").strip()
            level = len(line) - len(line.lstrip("#"))
            lines.append("#" * min(level, 6) + " " + stripped)
        else:
            lines.append(line)
    return "\n".join(lines)


def main() -> None:
    path = sys.argv[1]
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    sys.stdout.write(normalize_headings(text))


if __name__ == "__main__":
    main()
