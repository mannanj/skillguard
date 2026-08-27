# OpenExecutive-Format SkillGuard README Design

**Date:** 2026-08-26

**Status:** Approved direction; pending written-spec review

**Reference:** [SenteLabsAI/OpenExecutive README](https://github.com/SenteLabsAI/OpenExecutive)

## Objective

Replace `README.md` with a project-specific adaptation of the OpenExecutive
README's information architecture. Match the reference's section order, heading
rhythm, tables, code blocks, architecture overview, repository tree, and level
of operational detail while using only accurate SkillGuard content.

The result should read as the SkillGuard counterpart to the reference README,
not as a generic security-product page and not as a copy of OpenExecutive's
product language.

## Selected Approach

Use a literal section-for-section translation. Preserve every major structural
role from the reference and rename only sections that have no meaningful direct
equivalent. Redistribute the useful material in the current SkillGuard README
into that structure instead of deleting technical detail.

Alternatives considered and rejected:

1. Copy only the visual conventions while retaining SkillGuard's current order.
   This would not meet the request for the reference's precise format.
2. Create a shorter hybrid README. This would lose the reference's engineering
   depth and several important SkillGuard operating boundaries.

## Information Architecture

| Reference section | SkillGuard section | Content responsibility |
|---|---|---|
| Title, badges, description | Title, badges, description | Plain H1, CI/license/Python badges, one-paragraph product definition |
| Demo | Demo | Existing `demo/demo.gif` and a short explanation of the blocked invocation |
| What It Does | What It Does | Skill and MCP scanning, detection engines, runtime gating, history, and triage |
| Architecture | Architecture | Discovery, materialization/redaction, engine fan-out, cache/history, and runtime hook |
| Tech Stack | Tech Stack | Python stdlib core, SQLite, shell integration, optional engines, and static site |
| Repo Layout | Repo Layout | Accurate tree of the package, hooks, Agent Skill, tests, installer, demo, and landing site |
| Quick Start | Quick Start | Claude plugin install, Codex/local installer, first scan, and expected result |
| Run the Discord Bot | Run the Runtime Guard | Claude PreToolUse behavior and Codex MCP-hook setup, with honest platform differences |
| Onboarding Your Company | Protect Your Agent Environment | First inventory scan, policy choice, review, and re-scan workflow |
| Interfaces | Interfaces | Claude Code, Codex, CLI, JSON/Markdown output, and repository adapters |
| Document Upload | Scan Targets | Skills, MCP configurations, one named target, all targets, and opt-in introspection |
| Deployment | Installation and Distribution | Claude plugin, Codex plugin wrapper, curl/local install, editable Python install, and adapters |
| Configuration | Configuration | MCP policy, activity logging, cache paths, environment controls, and engine credentials |
| Running on Local Models | Optional Detection Engines | Local, MCP structural, Cisco, SkillAudit, and Snyk selection and requirements |
| Adding a New Specialist Agent | Adding a Detection Engine | Engine protocol, registration, graceful degradation, fixtures, and tests |
| Development | Development | Editable development install, pytest, Ruff, mypy, and packaging checks |
| Evaluation System | Detection and Test System | Malicious/clean fixtures, false-positive guards, security invariants, and current verified test count |
| Privacy | Privacy | Local persistence, secret redaction, external-engine boundaries, and introspection risk |
| Contributing | Contributing | Contribution link and concise quality checklist |
| License | License | AGPL-3.0-only plus the separate commercial license and NOTICE requirement |

## Content Design

### Opening

Use the reference's plain, left-aligned opening rather than the current centered
HTML hero. Keep SkillGuard's verified badges and follow them with a concise
description that states the protected surfaces and runtime behavior without an
unqualified security guarantee.

### Technical narrative

The README should move from product behavior to implementation detail in the
same progression as the reference:

```text
problem and behavior
    -> architecture and stack
    -> repository orientation
    -> installation and operation
    -> advanced configuration
    -> extension and development
    -> privacy, contribution, and license
```

The architecture block must distinguish static scanning from opt-in live MCP
introspection. It must also distinguish Claude skill gating from Codex MCP tool
gating so the README does not claim unsupported Codex skill hooks.

### Examples and tables

- Use commands supported by `skillguard/args.py`, `skillguard/commands.py`, and
  the installer tests.
- Prefer the reference's compact operational tables for interfaces,
  installation channels, configuration, engines, and exit behavior.
- Keep examples short enough to scan but complete enough to run.
- Preserve the existing demo asset rather than adding a remote video thumbnail.
- Link detailed security and contribution material to `SECURITY.md` and
  `CONTRIBUTING.md` instead of duplicating their full contents.

## Accuracy and Safety Rules

- Treat the implementation, tests, `pyproject.toml`, `SECURITY.md`, and
  `CONTRIBUTING.md` as the authority for product claims.
- Do not claim that SkillGuard prevents every malicious skill, guarantees a
  clean dependency, or protects GitHub agentic workflows that are still only a
  research spike.
- Do not expose credential values in configuration examples.
- Label network-backed engines and live MCP introspection clearly.
- Preserve the dual-license wording; do not simplify it to a single open-source
  license.
- Avoid copying OpenExecutive prose. Its section structure is the template;
  SkillGuard's words and evidence remain original.

## Repository Hygiene

The README commit must contain only `README.md` and any explicitly approved
design/plan documents. Existing unrelated working-tree changes must remain
untouched and unstaged.

Local or generated files such as the tracked Wrangler account cache, raw image
API responses, machine-local source paths, and locally installed `.agents`
skills are outside the README change and must not enter its commit.

## Validation

Before completion:

1. Check every relative README link against the repository.
2. Check every documented command and option against the CLI or its tests.
3. Run `git diff --check` for the README and documentation changes.
4. Run the full test suite from the repository virtual environment.
5. Inspect the staged diff to prove unrelated working-tree files are excluded.
6. Commit the README separately and push it to `origin/main` only after the
   written spec has been reviewed.

## Acceptance Criteria

- The major sections appear in the same order and serve the same structural
  purpose as the OpenExecutive README.
- Every renamed section is the closest truthful SkillGuard equivalent.
- A new user can understand the product, install it, run a first scan, and find
  advanced operational guidance without leaving the README.
- Claude and Codex capabilities are described separately and accurately.
- Existing coverage of skills, MCPs, engines, runtime policies, history,
  triage, privacy, contribution, and licensing is retained.
- No unrelated or generated files are included in the README commit.
- The repository test suite passes before push.
