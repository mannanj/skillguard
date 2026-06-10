# Contributing to SkillGuard

Thanks for helping make the skill ecosystem safer. The highest-value contribution is almost always a **new detection pattern with a test fixture** — that's how this tool compounds.

## Contributing a detection pattern

1. Add the pattern in `skillguard/cli.py` under the matching category block using the `_p(category, severity, regex, description)` helper. Severity guide:
   - `critical` — remote code execution, reverse shells, confirmed exfiltration endpoints
   - `high` — credential/secret access, prompt injection, obfuscation, piped shell execution
   - `medium` — persistence, recon-adjacent network ops, dangerous file operations
   - `low` — reconnaissance and fingerprinting
2. Add a fixture: a minimal file under `tests/fixtures/malicious-skill/` (or a new fixture skill) containing the pattern in a realistic disguise.
3. Add an assertion in `tests/` proving the local engine flags it — and that an innocent look-alike does **not** (false-positive guard).
4. Run `pytest`. All green before you open the PR.

Patterns are compiled with `re.IGNORECASE`. Keep them tight: a pattern that fires on documentation *about* attacks is worse than no pattern. The scanner already suppresses comment lines containing "detect" and markdown table rows — work with that, not around it.

## Other welcome contributions

- New engine adapters (the contract is one class with `name` and `scan(skill: SkillInfo) -> list[Finding]`; degrade gracefully when the dependency is absent)
- Hook hardening (see `SECURITY.md` for the threat model)
- Docs, examples, and install-path improvements

## Development setup

```bash
git clone https://github.com/mannanj/skillguard
cd skillguard
pip install -e ".[dev]"
pytest
git config core.hooksPath .githooks   # enable repo git hooks (recommended)
```

The `.githooks/pre-push` hook keeps live installs honest: it refuses a push to
main that changes plugin-runtime files (`skillguard/`, `hooks/`,
`.claude-plugin/`, `install.sh`) without a version bump — installed Claude Code
plugins only refresh on a bump — and, after a push lands, auto-runs
`claude plugin update skillguard@skillguard` so a locally-installed plugin
tracks the repo (log: `~/.claude/logs/skillguard-plugin-autoupdate.log`).
`tests/test_version_sync.py` enforces that all four version declarations move
together.

No required runtime dependencies — the core scanner is stdlib-only by design. Keep it that way; optional engines belong behind `[project.optional-dependencies]` extras and graceful availability checks.

## Shipping changes

How a change reaches users, by channel:

- **Claude Code plugin** (live installs): bump the version in all four places —
  `pyproject.toml`, `skillguard/cli.py` `__version__`, `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json` (`tests/test_version_sync.py` enforces lockstep) —
  then commit and `git push`. Installed plugins only refresh on a version bump; the
  pre-push hook refuses runtime changes without one and auto-refreshes your local
  install once the push lands. Other users pick it up via `/plugin update skillguard`.
- **Landing site** (skillguard.sh): `cd landing && wrangler deploy` —
  see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
- **PyPI**: not yet published — tracked in [task.md](task.md).

Changes outside the runtime paths (docs, `landing/`, `tests/`) push without a bump.

## Pull request checklist

- [ ] Tests pass (`pytest`)
- [ ] New patterns ship with a malicious fixture **and** a false-positive guard
- [ ] No new required dependencies
- [ ] `CHANGELOG.md` entry under *Unreleased*

## Licensing of contributions

SkillGuard is dual-licensed: [AGPL-3.0-only](LICENSE) plus a
[commercial license](LICENSE-COMMERCIAL.md) sold by the maintainer. For the
dual-licensing model to work, the maintainer must hold sufficient rights to
every line in the repo.

By submitting a contribution you agree that:

1. Your contribution is licensed to the project under **AGPL-3.0-only**, and
2. You grant Mannan Javid a perpetual, worldwide, non-exclusive, royalty-free
   right to relicense your contribution as part of SkillGuard under other
   terms, including commercial licenses.

You retain copyright in your contribution. If you can't agree to this (e.g.
your employer owns your work), please say so in the PR instead of submitting.
