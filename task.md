# Task: Publish skillguard to PyPI

**Status:** blocked on a PyPI API token — everything else is done and verified.
**Created:** 2026-06-05 · **Updated:** 2026-06-10 (mannan: no PyPI push yet, parked for later)

## Goal

First PyPI release so `pip install skillguard` and `uvx skillguard` work.
Until this ships, the `CHANGELOG.md` `[0.2.0]` header line "First PyPI release —
`pip install skillguard` / `uvx skillguard`" is **not yet true** (package 404s on PyPI).

## Already done (verified 2026-06-05; test count re-verified 2026-06-10)

- [x] PyPI name `skillguard` confirmed free (`https://pypi.org/pypi/skillguard/json` → 404)
- [x] Version bumped to 0.2.0 (`pyproject.toml`, `skillguard/cli.py` `__version__`,
      `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`)
- [x] `CHANGELOG.md`: 0.2.0 section dated 2026-06-05 (first PyPI release + AGPL relicense)
- [x] License metadata correct: PEP 639 expression `AGPL-3.0-only OR LicenseRef-Commercial`,
      license-files LICENSE / LICENSE-COMMERCIAL.md / NOTICE all land in the sdist+wheel
- [x] Tests: 57/57 pass (`uv run --extra dev pytest -q`)
- [x] Distributions built: `dist/skillguard-0.2.0.tar.gz` + `.whl` — **STALE, rebuild before
      publishing**: built 2026-06-05, before the FP-triage feature and the SkillAudit
      parser fix (both currently in CHANGELOG `[Unreleased]`). Before publishing, fold
      `[Unreleased]` into the release section (or bump the version) and `uv build` fresh

## Remaining steps

1. Get a PyPI API token:
   - Account (if needed): https://pypi.org/account/register/ (email verify + 2FA)
   - Token: https://pypi.org/manage/account/token/ — scope **Entire account**
     (required for first upload of a new project; swap to a project-scoped token after)
2. Publish from repo root:
   ```bash
   uv build                      # if dist/ is empty
   uv publish --token pypi-XXXX  # or put token in ~/.pypirc / UV_PUBLISH_TOKEN
   ```
3. Verify from the live index:
   ```bash
   uvx skillguard@0.2.0 --version   # expect: skillguard 0.2.0
   curl -s https://pypi.org/pypi/skillguard/json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['info']['version'], d['info']['license_expression'])"
   ```
4. Tag and push the release:
   ```bash
   git tag v0.2.0 && git push origin v0.2.0
   ```
5. Aftercare:
   - Replace the account-scoped token with a project-scoped one (or set up
     [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) from GitHub Actions
     in `.github/workflows/` so future releases need no token at all)
   - Update README install section to lead with `uvx skillguard` / `pip install skillguard`
   - Consider a PyPI version badge in README
   - Delete this task.md when done

## Gotchas

- If publish happens on a later date, update the `## [0.2.0] — 2026-06-05` date in CHANGELOG.md
- `uv run` creates a `uv.lock` — the project doesn't track one; delete it after test runs
- Core package is intentionally zero-dependency; don't add runtime deps as part of release
