# Task: Mine Nesbitt's "Skills Registry Threat Models" for SkillGuard

**Status:** research / evaluation (no code yet)
**Created:** 2026-06-26
**Source:** Andrew Nesbitt, "Skills Registry Threat Models" (2026-06-03) —
<https://nesbitt.io/2026/06/03/skills-registry-threat-models.html>
**Author context:** Nesbitt runs Ecosyste.ms / Libraries.io; this is a
package-registry veteran applying a decade of npm/PyPI supply-chain lessons to
skills registries. Treat it as the most complete public threat enumeration for
this space to date (the post's own thesis: *no skills registry has a published
threat model yet*).

## Why we care

The post is, in effect, **a spec for what a skills/MCP scanner has to defend
against — and a catalogue of how to evade one.** SkillGuard is a client/loader-
and scanner-side tool, so it sits squarely inside one slice of Nesbitt's
landscape. Two parts of the post are directly about products like ours:

1. The **scanner-evasion** section reads like an attack plan against exactly the
   regex-plus-optional-LLM design SkillGuard ships. If those evasions work, they
   work on us. This is the highest-value content.
2. The **agent-as-registry-client** threats (selection bias, description framing,
   discovery-ranking injection) are a *genuinely new detection category* that no
   amount of "scan the bash for `curl`" covers — and that nobody else is shipping
   detection for. Potential differentiator.

The rest of the post (registry-side controls: typosquatting, revival hijack,
maintainer lifecycle, provenance, cooldowns) is mostly **out of scope for a
scanner** — it's the registry operator's job, not ours. We should be deliberate
about that boundary instead of pretending a scanner can fix a registry's slug
policy.

## SkillGuard's actual position in this landscape

SkillGuard is **not** a registry. It is:
- a CLI scanner over local skill/MCP artifacts (static content), and
- a PreToolUse hook that gates invocation, failing closed on skills (no scan /
  corrupted cache / modified-since-scan → block) and `off|warn|enforce` for MCP.

So Nesbitt's threats partition cleanly for us into **in-scope** (scanner/client/
loader), **partially-in-scope**, and **out-of-scope** (registry operator).

## Coverage map — threats vs. what SkillGuard ships TODAY

Grounded against `skillguard/patterns.py` shipped categories
(`credential_theft, prompt_injection, reverse_shell, obfuscation, env_exfil,
data_exfil, recon, persistence, network, dangerous_op, container_escape,
shell_pipe`), the `mcp/` analyzer, and `hook.py`. **Verified 2026-06-26** by
reading the live code — note the correction on role-injection below.

### In scope — already covered (at least partially)
| Nesbitt threat | SkillGuard today |
|---|---|
| Code-exec at load / dangerous scripts | `reverse_shell`, `dangerous_op`, `container_escape`, `shell_pipe`, `persistence` patterns |
| Prompt injection in descriptions/body | `prompt_injection` category (7 rules) |
| Secret/credential exfiltration | `credential_theft`, `env_exfil`, `data_exfil` (and `mcp/secrets.py` redaction authority) |
| Transitive PM calls (`pip/npm/cargo` in scripts) | partial — caught only when the command line also matches a dangerous pattern; no dependency-graph view |
| Mutable-version / modified-since-scan (local TOCTOU slice) | hook fails closed on mtime change vs. cached scan |

### In scope — GAP (this is the product backlog the post implies)
| Nesbitt threat | Why we miss it | Note |
|---|---|---|
| **Role-injection / special-token attacks** (`<|im_start|>`, `assistant:` forgery) | **NO shipped category.** `plans/011` is authored **design-only, TODO** — *not executed*. (Earlier synthesis wrongly called this "covered.") | Greenlight 011 → first concrete win |
| **Truncation-past-limit evasion** (payload at char 10,001) | Need to confirm the LocalEngine scans *full* content with no cap; any LLM/remote engine must too | Cited as "strongest single evasion" |
| **Paraphrase / synonym evasion** | Regex keys on literal tokens; benign synonyms slip the local layer | Structural limit of regex-only |
| **Decomposition evasion** (malice split into an innocent "definition-of-done" checklist) | No multi-line / multi-step intent correlation | Hard; flag as research |
| **Multi-mode coordination** (clean code + injected prose, or vice-versa) | We scan both modes but **surface them independently** — no "this skill primes the agent *and* ships the payload" correlation | Snyk ToxicSkills: 91% of malicious used both |
| **Manipulative description framing** ("officially verified", directive/recency language → 77.6% adversarial-selection win rate) | No detector for trust-claim / social-engineering language in manifests | New category; strong differentiator |
| **Scanner-jailbreak / DAN-style reviewer prompts** in the manifest | Only relevant once/if a SkillGuard LLM engine exists; harden its prompt | Applies to SkillAudit/remote engines |
| **Remote content injection at runtime** (RAG/doc-fetch into context) | Static scan can't see runtime fetches; we flag URLs but not the injection | Inherent static-analysis blind spot — document it |
| **Slopsquatting** (hallucinated PM names pre-registered by attacker) | No package-name reputation/existence check | Needs upstream data |

### Out of scope for a scanner (registry-operator's job — note, don't build)
Flat-namespace typosquatting · revival hijack · maintainer lifecycle / account
takeover · provenance attestation / trusted publishing · publish-credential
hygiene · cooldown windows · yank-vs-ban-vs-hide separation · moderation-cap DoS ·
PURL type registration · discovery-ranking (GASLITE) index manipulation.
→ These belong in `SECURITY.md` "out of scope / known limitations" or a
"what a scanner can and can't do" explainer, **not** in the engine.

## The strategic question to answer

**Does this post change SkillGuard's offering, and if so how?** Candidate
answers to weigh (pick, don't do all):

1. **Evasion-hardening pass** — treat the scanner-evasion list as a red-team
   backlog. For each evasion (truncation, paraphrase, decomposition, multi-mode,
   scanner-jailbreak): write a malicious fixture that *currently passes clean*,
   prove the gap, then close it (per the contribution contract: malicious fixture
   + false-positive guard). This is the most defensible use of the post.
2. **New "social-engineering / selection-bias" detection category** — flag
   manifest/description language engineered to win model selection ("officially
   verified", "always use this", exaggerated capability, recency bait). Nobody
   ships this; it maps to a measured 77.6% attack success rate.
3. **Multi-mode correlation** — upgrade reporting so a finding can say "prose
   primes + code executes," not two unrelated rows. Raises severity when both
   modes co-occur in one artifact.
4. **Honesty/positioning** — publish a crisp "SkillGuard's threat model vs.
   Nesbitt's map": what we catch, what's a static-analysis blind spot, what's the
   registry's job. Turns the post into marketing credibility instead of a gap list.
5. **No-op** — decide the post is mostly registry-side and our roadmap already
   covers the scanner slice (011 + existing categories). Valid if the evasion
   fixtures all already fail clean (test #1 below decides this).

## Questions to answer (do these before committing to code)

1. **Does the LocalEngine scan full content with no length cap?** Read
   `engines/local.py`; if there's any truncation, truncation-evasion is live.
   (Cheap, decisive — do first.)
2. For each evasion (truncation, paraphrase, decomposition, multi-mode,
   description-framing): does a crafted fixture **pass clean today**? Build the
   five fixtures; the red/green result *is* the prioritization.
3. Is "description framing" detection a regex job, an embedding/heuristic job, or
   an LLM-engine job? What's the false-positive cost on legit "verified"/"official"
   skills?
4. Should multi-mode correlation live in `scan.py` (dedupe/aggregate stage) or in
   `render/` (presentation)? It changes severity, so likely scan-side.
5. Where does the in/out-of-scope boundary get documented — `SECURITY.md`,
   `README` known-limitations, or a new explainer page on the Gandalf site?
6. Does plan 011 (role-injection) get greenlit as the concrete first deliverable
   this post argues for, or stay parked?

## Update 2026-06-26 — Option 2 BUILT (`selection_manipulation` category)

Strategic-option decisions recorded:
- **Option 2 (new selection-manipulation category) — DONE, shipped this session.**
- Option 1 (evasion-hardening sweep) — defer; the five-fixture red/green pass is
  the next chunk.
- Option 3 (multi-mode correlation) — defer; scan-side aggregation, larger change.
- Option 4 (positioning / threat-model page) — defer to docs work.
- Option 5 (no-op) — rejected; description-framing genuinely escaped before this.

What shipped:
- New `selection_manipulation` category in `patterns.py` (8 rules, two tiers):
  **high** = anti-competitive directives (`ignore other skills`, `do not use
  other skills`, `use this skill instead of`, `the only skill you should use`);
  **medium** = unverifiable trust/authority framing (`officially verified|
  approved|endorsed`, `<vendor>-approved|verified`, `100% safe`, `fully trusted`).
- `engines/local.py`: frontmatter scan is now **category-aware** — every other
  category still skips the YAML `name:`/`description:` lines, but
  selection_manipulation scans them, because the description IS the selection
  surface. This is the load-bearing architectural change.
- `review_text.py`: human-readable explanation branch for the category.
- Fixtures + `tests/test_selection_manipulation.py` (13 tests): malicious fixture
  flagged at both tiers, description-frontmatter detection pinned, FP guard
  (honest "official Stripe integration" stays silent), table-suppression honored.
- **Mutation-proven** (3 transient mutations, all caught): severity-flip →
  per-rule severity test RED; frontmatter-exemption removed → description test
  RED; over-broaden `officially verified`→`official` → FP guards RED.

Empirical precision (the answer to "any false positives?"):
- **0 selection_manipulation findings across 1,212 real installed skills
  (4,481 files).** The corpus contains the near-miss words it must NOT flag —
  `official` ×164, `verified` ×380, `trusted` ×86, `this skill` ×1070,
  `always use` ×187, `100%` ×61 files — and the detector stayed silent on all.

Deliberate scope boundaries (NOT bugs — documented choices):
- **High-precision regex only.** Fuzzy recency/superlative framing ("most
  up-to-date", "the best", generic "always use") is intentionally NOT matched —
  it is not separable from honest description by regex and belongs to a future
  semantic/LLM engine. This is the paraphrase-evasion gap the post predicts;
  owning it honestly beats a low-precision regex.
- **MCP coverage is partial and intentional.** MCP tool/param descriptions are
  materialized to `tools.md`/`server-instructions.md` (`mcp/materialize.py:85`)
  and scanned by LocalEngine via `scan.py:100`, so the **medium trust-tier fires
  on MCP tool descriptions for free**. The **high directive-tier is keyed on the
  word "skill"** (a domain term → high precision) and deliberately does NOT
  generalize to "tool" (everyday English → would wreck precision). MCP-tool
  directive-framing ("ignore other tools") is a future MCP-surface-aware rule.

Open follow-ups this spun off:
- [ ] MCP-surface-aware selection-manipulation rule (tool-worded directives,
      scoped to `kind == "mcp"` targets where the FP tradeoff differs).
- [ ] Semantic/LLM tier for paraphrase/recency framing the regex can't catch.

## Completion criteria

- [ ] Five evasion fixtures built under `tests/fixtures/`, each with a recorded
      CAUGHT/ESCAPED verdict against the current engine set.
- [ ] A decision recorded (in this file) on each of the 5 strategic options:
      build / defer / reject, with one-line rationale.
- [ ] In/out-of-scope boundary written into `SECURITY.md` (or linked explainer)
      so we're explicit that registry-layer threats are not a scanner's job.
- [ ] If any evasion ESCAPES: a follow-up `task-*.md` (or plan) per closed gap,
      each honoring the contribution contract (malicious fixture + FP guard +
      mutation-proven test).
- [ ] Plan 011 greenlight/park decision logged in `plans/README.md`.

## References worth following (from the post)
- Snyk **ToxicSkills** audit (3,984 skills; 100% code + 91% prompt-injection
  co-occurrence) — our multi-mode correlation evidence base.
- arXiv:2605.11418 "Under the Hood of SKILL.md" — discovery/selection/governance
  framework; 77.6% adversarial-selection rate; truncation-as-strongest-evasion.
- arXiv:2412.20953 GASLITE — embedding-index corpus-insertion (registry-side; note
  as out-of-scope but relevant to why discovery is attackable).
- OWASP Agentic Skills Top 10; OpenSSF Package Repository Security Principles;
  npm Threats & Mitigations — benchmarks for "what a documented threat model
  looks like."
- Nesbitt companion posts: "Package Security Problems/Defenses for AI Agents"
  (2026-04-08/09), "Install-Script Allowlists" (2026-06-05), "Scrutineer"
  (2026-06-25 — scanning without flooding maintainers).

## Drift / trust notes
- Coverage map verified against live `patterns.py` categories on 2026-06-26.
- **Correction carried in:** the role-injection row was initially mis-stated as
  "covered" — it is **not shipped**; only `plans/011` exists, design-only/TODO.
- The post does **not** cover MCP servers as a distinct class — all MCP mapping
  here is our inference from the skills threats. Don't cite the post for MCP claims.
