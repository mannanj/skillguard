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
```

No required runtime dependencies — the core scanner is stdlib-only by design. Keep it that way; optional engines belong behind `[project.optional-dependencies]` extras and graceful availability checks.

## Pull request checklist

- [ ] Tests pass (`pytest`)
- [ ] New patterns ship with a malicious fixture **and** a false-positive guard
- [ ] No new required dependencies
- [ ] `CHANGELOG.md` entry under *Unreleased*
