# Gandalf Rebrand Copy

Date: 2026-06-16

Use this as the copy source for the landing page, README, CLI, hook output, social posts, screenshots, and launch notes.

## Rule

The product is **Gandalf**.

The promise is **Thou shall not pass.**

Everything else serves that line.

## Position

Gandalf blocks unsafe agent tools before they run.

Claude may read a skill.

Gandalf decides if it runs.

## Product Truth

Gandalf scans Claude Code skills and MCP servers.

It reads skill files, bundled scripts, MCP configs, launch commands, endpoint metadata, and env/header names.

It redacts secret values.

It caches verdicts locally.

It records scan history.

Its hook blocks unscanned, changed, corrupted, critical, and high-risk skills.

MCP enforcement defaults on.

Optional engines add coverage. Local checks work without them.

## Brand Hierarchy

### Primary Line

Thou shall not pass.

### Product Line

Block unsafe skills before they run.

### Mechanism Line

Gandalf checks skills and MCP servers before runtime, then blocks what has not cleared.

### Proof Line

0 commands ran.

## Voice

Short.

Certain.

Calm.

Concrete.

Runtime-first.

Use verbs people can test:

- scan
- block
- redact
- record
- enforce
- clear

Cut words that hide:

- empower
- unleash
- unlock
- seamless
- next-generation
- AI-native
- trust layer
- security posture
- workflow

No jokes in safety copy.

No fantasy lore.

No costume copy.

No old name.

## Copy Rules

Lead with refusal.

Explain with runtime.

Prove with outcome.

Do not say "secure your AI."

Say "block before it runs."

Do not say "protect your workflow."

Say "unscanned code stops."

Do not say "trusted automation."

Say "checked code runs."

Do not say "magic."

Say what happened.

## Landing Page

One page.

One primary action.

One promise.

### Nav

Left: Gandalf

Right: Install

Secondary: Source

### Hero

#### Headline

Thou shall not pass.

#### Subhead

Gandalf checks Claude Code skills and MCP servers before they run, then blocks anything unscanned, changed, or high-risk.

#### Primary CTA

Install Gandalf

#### Secondary Link

View source

#### Command

```sh
curl -fsSL https://gandalf.sh/install | sh
gandalf --target all --engines local
```

#### Hero Terminal

```text
$ claude uses pretty-formatter

GANDALF: THOU SHALL NOT PASS
  reason: credential exfiltration
  file: scripts/setup.sh:14

0 commands ran.
```

### Trust Strip

Skills checked.

MCP servers checked.

Secrets redacted.

History kept.

Local by default.

### Problem

Agent tools run with your permissions.

A helpful skill can hide a shell script, steal credentials, or inject prompts.

Claude sees a tool.

Gandalf sees what it can do.

### Proof

341 malicious skills were found in one agent-skill marketplace.

13.4% of one studied registry had critical issues.

This is not theoretical.

### Solution

Gandalf checks before runtime.

No scan. No run.

Changed code stops.

High-risk code stops.

Secrets stay redacted.

### How It Works

#### Scan

Reads skill files, scripts, MCP surfaces, commands, endpoints, and env/header names.

#### Decide

Combines local rules, cache state, change checks, and optional engines.

#### Enforce

Blocks unsafe calls in the PreToolUse hook before execution.

#### Remember

Keeps local scan history and hook activity.

### Feature Copy

Runtime blocking

Stops unsafe calls before execution.

MCP enforcement

Gates MCP tool calls, not just skills.

Local-first scanning

Runs deterministic checks without sending secrets away.

Secret redaction

Names risky fields without writing secret values.

Scan history

Keeps what was scanned, when, and why it passed or stopped.

### FAQ

#### Does Gandalf replace reading code?

No. Gandalf blocks known risk and unscanned runtime. You still own trust.

#### Can Claude still inspect a skill?

Yes. Reading is allowed. Running is gated.

#### What gets blocked?

Unscanned skills, changed skills, corrupted cache entries, and critical or high findings. MCP tools are blocked under enforcement.

#### Are secrets sent anywhere?

No. Secret values are redacted and never written to cache or history.

#### Does it need cloud services?

No. Local scanning works by default. Optional engines can add coverage.

### Final CTA

Thou shall not pass.

```sh
curl -fsSL https://gandalf.sh/install | sh
```

Install Gandalf

## App Surfaces

Every public surface says Gandalf.

### Product

Product name: Gandalf

Domain: gandalf.sh

Repo name: gandalf

Package name: gandalf

CLI: `gandalf`

Hook: `gandalf-hook`

Cache: `~/.claude/gandalf-cache/`

DB: `gandalf.db`

Env prefix: `GANDALF_`

### CLI Output

Use this blocked shape:

```text
GANDALF: THOU SHALL NOT PASS
  target: pretty-formatter
  reason: never scanned
  run: gandalf --skill pretty-formatter

0 commands ran.
```

Use this clean shape:

```text
GANDALF: cleared
  target: clean-skill
  verdict: clean
  engines: local

Claude may run it.
```

Use this changed shape:

```text
GANDALF: THOU SHALL NOT PASS
  target: deploy-helper
  reason: changed since last scan
  run: gandalf --skill deploy-helper

0 commands ran.
```

### Runtime States

CLEARED

Scanned clean.

NEEDS SCAN

Never checked.

CHANGED

Different from last scan.

HIGH RISK

Critical or high finding.

BLOCKED

Thou shall not pass.

### Buttons

Install Gandalf

Scan my skills

Check MCP servers

View source

Read docs

### Social Lines

Thou shall not pass.

Claude may read it. Gandalf decides if it runs.

No scan. No run.

Changed code stops.

Helpful skills can still steal credentials.

Gandalf blocks before runtime.

0 commands ran.

### Sticker Lines

Thou shall not pass.

No scan. No run.

Changed code stops.

0 commands ran.

Checked code runs.

Unsafe code stops.

## Rare Secondary Analogy

Use metaphor only after the product truth is clear.

Never in the hero.

Never in nav.

Never in CTA text.

Acceptable:

Gandalf stands between read and run.

Better:

Claude may read it. Gandalf decides if it runs.

## Cut

Cut:

- You shall not run.
- Gate my skills.
- Staff down.
- Claude may cross.
- Safe side.
- Keeper.
- Sentinel.
- Watchtower.
- Fortress.
- Shield.
- Wizard.
- Spell.
- Magic.
- Robes.
- Beard.

Cut any copy where the metaphor is louder than the mechanism.

## Rename Checklist

Replace the public name everywhere.

Replace CLI output.

Replace install commands.

Replace hook messages.

Replace package metadata.

Replace docs, README, changelog copy, screenshots, OG images, demo captions, and landing assets.

Replace cache, DB, and env names or ship a migration.

Keep compatibility only if it is silent.

Run a case-insensitive legacy-name search before release.

Run domain, registry, and trademark checks before launch.

## Final Test

Can a new visitor answer this in five seconds?

What is it?

Gandalf.

What does it do?

Blocks unsafe skills before they run.

What is the line?

Thou shall not pass.
