# Task: Cisco engine false-positives on the clean fixture

**Status:** open — upstream behavior, low priority, workaround exists.
**Created:** 2026-06-10

## Problem

The optional Cisco engine (`pip install "skillguard[cisco]"` → `cisco-ai-skill-scanner`)
flags the clean fixture (`tests/fixtures/clean-skill/`) with 1 high + 1 medium finding.
The trigger is the fixture's documentation table that *mentions* attack phrases without
containing instructions. Our local engine correctly suppresses markdown doc-table rows
(see `tests/test_local_engine.py::test_markdown_table_rows_suppressed`); the Cisco
scanner has no equivalent suppression, so any skill that documents threats reads as one.

## Repro

```bash
rm -rf /tmp/sg-cisco && mkdir -p /tmp/sg-cisco/.claude/skills
cp -r tests/fixtures/clean-skill /tmp/sg-cisco/.claude/skills/
HOME=/tmp/sg-cisco .venv/bin/skillguard --skill clean-skill --engines cisco
# expected clean; actual: 1 high + 1 medium on the doc table
```

## Options (pick when revisiting)

1. **Report upstream** to cisco-ai-skill-scanner with the doc-table repro — the
   principled fix, helps everyone.
2. **Adapter-side post-filter** in `CiscoEngine.scan()` (`skillguard/cli.py`): reuse the
   local engine's doc-table heuristic to demote/annotate findings whose matched line is
   a markdown table row. Keeps the engine useful on doc-heavy skills, but means we
   silently second-guess an engine users explicitly opted into — if doing this, mark the
   findings as suppressed-by-heuristic rather than dropping them.
3. **Document + triage** (current de-facto answer): README already notes engine
   disagreement is expected; users mark known-good skills once with `--mark-fp NAME`
   and the mark persists across re-scans.

## Notes

- Do NOT "fix" this by weakening the fixture — the doc table exists precisely to prove
  scanners can tell documentation from instructions. It's the Cisco engine that fails
  the test, not the fixture.
- Local engine and (post-2026-06-10 parser fix) SkillAudit both pass the clean fixture.
