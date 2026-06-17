# Task: Community reporting and scan clarity

**Status:** future
**Created:** 2026-06-16

## Idea

Add a way for SkillGuard users to report malicious or suspicious artifacts they
discover, including skills, MCP servers, launch commands, configs, bundled
scripts, and other agent-tool extensions. The report flow should make it easy
for trusted friends or collaborators to investigate, reproduce, discuss, and
triage findings.

This should also improve how users understand scan results while using
SkillGuard in their agent tools, so they can see what happened, why it matters,
and what intervention is available.

## User Needs

- Report suspicious skills, MCP servers, or related agent artifacts from scan
  output.
- Attach enough evidence for another person to investigate without exposing
  secrets by accident.
- Discuss a finding with collaborators before deciding whether it is malicious,
  benign, a false positive, or needs more research.
- Understand scan results in plain language:
  - what was scanned
  - what changed since the last scan
  - which rules or engines flagged it
  - why the behavior is risky
  - whether SkillGuard blocked, warned, or only recorded the finding
  - what actions are available next
- Intervene from the agent-tool workflow when needed: block, quarantine, allow
  once, ignore with justification, open a report, or escalate for review.

## Possible Product Surfaces

1. `skillguard report <finding>` command that creates a redacted local report
   bundle.
2. Optional submission flow to a shared queue or private workspace.
3. Report pages with status, reproduction notes, labels, severity, source links,
   and discussion threads.
4. Agent-facing scan explanations that summarize current protection state and
   next actions without requiring users to read raw JSON or logs.
5. A triage dashboard for reviewing unresolved suspicious artifacts.

## Safety And Privacy Requirements

- Reports must be local/private by default.
- Secret values, env values, auth headers, tokens, and private local paths must
  be redacted before any share/export action.
- The UI must clearly distinguish local findings, user-submitted reports,
  reproduced detections, and confirmed malicious samples.
- Public or shared submissions should require explicit consent.
- Discussion threads should preserve provenance: who submitted, who reproduced,
  what version of SkillGuard scanned it, and which files/configs were included.

## Questions To Answer

1. Is the first version local-only export, a private hosted queue, or both?
2. What is the minimum report bundle needed for reliable reproduction?
3. Who can mark something as confirmed malicious, false positive, duplicate, or
   needs more evidence?
4. Should discussion happen inside SkillGuard, GitHub issues, a lightweight
   hosted workspace, or an external chat/link-out flow?
5. How should agent-tool integrations present intervention choices without
   making routine scans noisy?
6. What retention and deletion controls are required for submitted artifacts?

## Completion Criteria

- Define a report schema for skills, MCP servers, configs, launch commands, and
  scan verdicts.
- Implement redacted local report export.
- Add scan-result explanations that show the reason, evidence, enforcement
  outcome, and next actions for each important finding.
- Design a collaborator triage flow with statuses, labels, comments, and
  reproduction notes.
- Add tests proving report export redacts secrets and private values before
  sharing.
- Document the trust model for shared/community reports.
