from __future__ import annotations

import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANDING_HTML = ROOT / "landing" / "public" / "index.html"
DOCS_HTML = ROOT / "landing" / "public" / "docs" / "index.html"
MASCOT_PNG = ROOT / "landing" / "public" / "gandalf-mascot.png"
LOCKUP_JPG = ROOT / "landing" / "public" / "gandalf-lockup.jpg"
LANDING_WORKER = ROOT / "landing" / "src" / "index.js"


def _html() -> str:
    return LANDING_HTML.read_text(encoding="utf-8")


def _docs_html() -> str:
    return DOCS_HTML.read_text(encoding="utf-8")


def _worker() -> str:
    return LANDING_WORKER.read_text(encoding="utf-8")


class LandingPageTests(unittest.TestCase):
    def test_landing_copy_is_gandalf_first_and_install_focused(self) -> None:
        html = _html()
        compact_html = re.sub(r"\s+", " ", html)

        self.assertIn("<title>Gandalf - Thou shall not pass.</title>", html)
        self.assertIn('content="Gandalf - Thou shall not pass."', html)
        self.assertIn('href="https://gandalf.sh/"', html)
        self.assertIn('aria-label="Gandalf home"', html)
        self.assertIn('src="/gandalf-mascot.png"', html)
        self.assertIn(">Gandalf</h1>", html)
        self.assertIn("Thou shall not pass.", html)
        self.assertIn("Block unsafe skills before they run.", html)
        self.assertIn(
            "Gandalf checks Claude Code skills and MCP servers",
            compact_html,
        )
        self.assertIn("No scan. No run.", html)
        self.assertIn("curl -fsSL https://gandalf.sh/install | sh", html)
        self.assertIn("gandalf --target all --engines local", html)
        self.assertIn("/plugin marketplace add mannanj/gandalf", html)
        self.assertIn("/plugin install gandalf@gandalf", html)
        self.assertIn("codex plugin add gandalf@personal", html)
        self.assertIn('data-platform="shell"', html)
        self.assertIn('data-platform="claude"', html)
        self.assertIn('data-platform="codex"', html)
        self.assertIn('aria-label="Project facts"', html)
        self.assertIn("<span>stars</span", html)
        self.assertIn("<span>release</span><strong>v0.3.1</strong>", html)
        self.assertIn("<span>works with</span", html)
        self.assertIn("<strong>13 agents</strong>", html)
        self.assertIn("<span>license</span><strong>AGPL</strong>", html)
        self.assertNotIn("<strong>2 agents</strong>", html)
        self.assertNotIn("<strong>agent skills</strong>", html)
        self.assertNotIn("<span>checks</span>", html)
        self.assertNotIn("<span>runs</span>", html)
        self.assertNotIn("<span>proof</span>", html)
        self.assertNotIn("<strong>0 commands</strong>", html)
        self.assertIn('href="/docs/"', html)
        self.assertIn('class="install-box hero-install"', html)
        self.assertIn("<h2 id=\"faq-heading\">FAQ</h2>", html)
        self.assertNotIn("<h2 id=\"how-heading\">", html)
        self.assertNotIn("<h2 id=\"install-heading\">", html)
        self.assertNotIn("<h2 id=\"commands-heading\">", html)
        self.assertNotIn("<h2 id=\"problem-heading\">", html)
        self.assertNotIn("<h2 id=\"before-heading\">", html)
        self.assertNotIn("<h2 id=\"numbers-heading\">", html)
        self.assertNotIn("<section class=\"final-cta\"", html)
        self.assertNotIn('class="terminal"', html)
        self.assertNotIn('class="wall"', html)
        self.assertNotIn("var scanItems =", html)
        self.assertNotIn("SkillGuard - trust your agent tools", html)
        self.assertNotIn("<span>Trust</span>your agent tools", html)
        self.assertNotIn("guarding against malicious behavior", html)

    def test_source_nav_uses_github_icon(self) -> None:
        html = _html()

        self.assertIn('class="source-nav github-nav"', html)
        self.assertIn('href="https://github.com/mannanj/skillguard"', html)
        self.assertIn('aria-label="View source on GitHub"', html)
        self.assertIn('class="github-icon"', html)

    def test_github_stars_badge_is_dynamic(self) -> None:
        html = _html()

        self.assertIn('id="githubStars"', html)
        self.assertIn('aria-label="GitHub stars"', html)
        self.assertIn('fetch("/api/github-repo"', html)
        self.assertIn("formatStars", html)

    def test_worker_caches_github_repo_metadata(self) -> None:
        worker = _worker()

        self.assertIn('url.pathname === "/api/github-repo"', worker)
        self.assertIn("https://api.github.com/repos/mannanj/skillguard", worker)
        self.assertIn("stargazers_count", worker)
        self.assertIn("caches.default", worker)
        self.assertIn("Cache-Control", worker)

    def test_landing_page_has_conversion_skill_hooks(self) -> None:
        html = _html()

        self.assertIn('data-conversion-goal="install-intent"', html)
        self.assertIn('data-primary-cta="install"', html)
        self.assertIn('data-variant-slot="headline"', html)
        self.assertIn('data-variant-control="Thou shall not pass."', html)
        self.assertIn('data-variant-b="No scan. No run."', html)
        self.assertIn('var landingExperiment = {', html)
        self.assertIn('goal: "install-intent"', html)
        self.assertIn('testedSlot: "headline"', html)
        self.assertIn('new URLSearchParams(window.location.search).get("v")', html)
        self.assertIn('data-landing-variant', html)
        self.assertIn("applyLandingVariant", html)
        self.assertIn("trackConversion", html)
        self.assertIn("gandalf_conversion", html)
        self.assertIn("gandalf:conversion", html)
        self.assertIn('plausible("Gandalf Install Intent"', html)
        self.assertNotIn('<section class="final-cta"', html)

    def test_docs_page_holds_command_reference(self) -> None:
        html = _docs_html()

        self.assertIn("<title>Gandalf docs - commands</title>", html)
        self.assertIn('href="/"', html)
        self.assertIn("Command reference", html)
        self.assertIn("<code>gandalf --target all</code>", html)
        self.assertIn("<code>gandalf --agent-summary</code>", html)
        self.assertIn("<code>gandalf --review</code>", html)
        self.assertIn("<code>gandalf --activity</code>", html)
        self.assertIn("<code>gandalf --install-agent-adapters .</code>", html)

    def test_mascot_assets_are_optimized_web_images(self) -> None:
        png = MASCOT_PNG.read_bytes()
        jpg = LOCKUP_JPG.read_bytes()

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack(">II", png[16:24]), (480, 588))
        self.assertLess(MASCOT_PNG.stat().st_size, 300_000)

        self.assertTrue(jpg.startswith(b"\xff\xd8\xff"))
        self.assertLess(LOCKUP_JPG.stat().st_size, 150_000)

    def test_runtime_animation_has_been_removed(self) -> None:
        html = _html()

        self.assertNotIn('class="wall"', html)
        self.assertNotIn('class="wall-stage"', html)
        self.assertNotIn('class="request-card blocked-card"', html)
        self.assertNotIn('class="stamp stamp-block"', html)
        self.assertNotIn('class="receipt"', html)
        self.assertNotIn("@keyframes bad-block", html)
        self.assertNotIn("@keyframes good-one-pass", html)
        self.assertNotIn("@keyframes good-two-pass", html)
        self.assertNotIn("animation: bad-block 5s", html)
        self.assertNotIn("Gandalf gating runtime calls", html)
        self.assertNotIn('class="scanner"', html)
        self.assertNotIn('class="scan-stage"', html)
        self.assertNotIn('class="skill-card"', html)
        self.assertNotIn('id="scanCount"', html)
        self.assertNotIn('id="scanReset"', html)


if __name__ == "__main__":
    unittest.main()
