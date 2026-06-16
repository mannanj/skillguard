# Task: Represent rising malicious skill counts

**Status:** future
**Created:** 2026-06-16

## Idea

Explore a future landing-page or product surface that shows malicious skill counts
rising over time, then connects those counts to SkillGuard's reproduced
third-party detections and local blocking behavior.

## Why This Is Not In The Current Revamp

The current landing needs a tighter runtime-gate story. A live or rising counter
could be useful, but only after we decide which published numbers, reproduced
samples, and SkillGuard-found samples we want to show.

## Questions To Answer

1. What data source is trustworthy enough to cite or refresh?
2. Is the count manually curated, periodically fetched, generated from
   SkillGuard's own scan corpus, or split across those buckets?
3. Should the presentation be a static evidence strip, a timeline, a counter, or
   a product demo that replays detections?
4. Which third-party samples has SkillGuard reproduced, and which samples did
   SkillGuard find independently?
5. Does the count belong on the marketing page, in docs, or inside the
   CLI/report output?

## Completion Criteria

- Pick a source and update policy.
- Define exact copy constraints for claims.
- Prototype at least two presentations.
- Publish or link the reproducible sample/methodology set behind any
  SkillGuard-specific count.
- Verify every number against primary sources before shipping.
