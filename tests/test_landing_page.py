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
OG_PNG = ROOT / "landing" / "public" / "og.png"
FAVICON_ICO = ROOT / "landing" / "public" / "favicon.ico"
FAVICON_32 = ROOT / "landing" / "public" / "favicon-32x32.png"
APPLE_TOUCH_ICON = ROOT / "landing" / "public" / "apple-touch-icon.png"
LANDING_WORKER = ROOT / "landing" / "src" / "index.js"


def _html() -> str:
    return LANDING_HTML.read_text(encoding="utf-8")


def _docs_html() -> str:
    return DOCS_HTML.read_text(encoding="utf-8")


def _worker() -> str:
    return LANDING_WORKER.read_text(encoding="utf-8")


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    return struct.unpack(">II", data[16:24])


class LandingPageTests(unittest.TestCase):
    def test_landing_copy_is_gandalf_first_and_install_focused(self) -> None:
        html = _html()
        compact_html = re.sub(r"\s+", " ", html)

        self.assertIn("<title>Gandalf - Thou shall not pass.</title>", html)
        self.assertIn('content="Gandalf - Thou shall not pass."', html)
        self.assertIn('href="https://gandalf.sh/"', html)
        self.assertIn('src="/gandalf-mascot.png"', html)
        self.assertIn(">Gandalf</h1>", html)
        self.assertIn("Thou shall not pass.", html)
        self.assertIn("Gandalf blocks unsafe skills before they run.", html)
        self.assertIn(
            "Check agent skills and MCPs on Claude, Codex, and other agent harnesses",
            compact_html,
        )
        self.assertIn("No scan. No run.", html)
        self.assertNotIn("curl -fsSL https://gandalf.sh/install | sh", html)
        self.assertIn("gandalf --target all --engines local", html)
        self.assertIn("/plugin marketplace add mannanj/gandalf", html)
        self.assertIn("/plugin install gandalf@gandalf", html)
        self.assertIn("codex plugin add gandalf@personal", html)
        self.assertIn("gandalf --install-agent-adapters .", html)
        self.assertNotIn('data-platform="shell"', html)
        self.assertIn('data-platform="claude"', html)
        self.assertIn('data-platform="codex"', html)
        self.assertIn('data-platform="harness"', html)
        self.assertIn("Agent Harness", html)
        self.assertIn('aria-label="Project facts"', html)
        self.assertIn("<span>stars</span", html)
        self.assertIn("<span>release</span><strong>v0.3.1</strong>", html)
        self.assertIn("<span>works with</span", html)
        self.assertIn("<strong>13 agents</strong>", html)
        self.assertIn("<span>license</span><strong>AGPL</strong>", html)
        self.assertIn('<div class="strip-item">Free</div>', html)
        self.assertIn('<div class="strip-item">Open-source</div>', html)
        self.assertIn('<div class="strip-item">Claude Code</div>', html)
        self.assertIn('<div class="strip-item">Codex</div>', html)
        self.assertIn('<div class="strip-item">13 agent harnesses</div>', html)
        self.assertIn('<div class="strip-item">Multi-engine scanning</div>', html)
        self.assertIn('<div class="strip-item">Prompt injection</div>', html)
        self.assertIn('<div class="strip-item">Secrets redacted</div>', html)
        self.assertIn('<div class="strip-item">Malicious exfiltration</div>', html)
        self.assertIn('<div class="strip-item">Network abuse</div>', html)
        self.assertNotIn("<strong>2 agents</strong>", html)
        self.assertNotIn("<strong>agent skills</strong>", html)
        self.assertNotIn("<span>checks</span>", html)
        self.assertNotIn("<span>runs</span>", html)
        self.assertNotIn("<span>proof</span>", html)
        self.assertNotIn("<strong>0 commands</strong>", html)
        self.assertIn('href="/#faq"', html)
        self.assertIn('href="/docs/"', html)
        self.assertIn('href="/#install"', html)
        self.assertIn("scroll-margin-top: 118px;", html)
        self.assertIn('href="https://mannan.is"', html)
        self.assertIn('class="install-box hero-install"', html)
        self.assertIn('class="line-copy-btn"', html)
        self.assertIn('data-copy-line="/plugin marketplace add mannanj/gandalf"', html)
        self.assertIn("copy-install-command-line", html)
        self.assertIn('<h2 id="faq-heading">FAQ</h2>', html)
        self.assertNotIn('href="#top" aria-label="Gandalf home"', html)
        self.assertNotIn("<span>Gandalf</span>", html)
        self.assertNotIn('<h2 id="how-heading">', html)
        self.assertNotIn('<h2 id="install-heading">', html)
        self.assertNotIn('<h2 id="commands-heading">', html)
        self.assertNotIn('<h2 id="problem-heading">', html)
        self.assertNotIn('<h2 id="before-heading">', html)
        self.assertNotIn('<h2 id="numbers-heading">', html)
        self.assertNotIn('<section class="final-cta"', html)
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
        self.assertIn('data-tooltip="View Source Code"', html)
        self.assertIn('class="github-icon"', html)
        self.assertIn('<span class="sr-only">Source on GitHub</span>', html)
        self.assertIn("transform: scale(1.18);", html)
        self.assertIn("content: attr(data-tooltip);", html)

    def test_landing_metadata_uses_mascot_favicon_and_social_preview(self) -> None:
        html = _html()

        self.assertNotIn('href="data:image/svg+xml', html)
        self.assertIn('rel="icon" href="/favicon.ico" sizes="any"', html)
        self.assertIn(
            'rel="icon" href="/favicon-32x32.png" type="image/png"',
            html,
        )
        self.assertIn('rel="apple-touch-icon" href="/apple-touch-icon.png"', html)
        self.assertIn('property="og:title" content="Gandalf - Thou shall not pass."', html)
        self.assertIn('property="og:url" content="https://gandalf.sh/"', html)
        self.assertIn('property="og:image" content="https://gandalf.sh/og.png"', html)
        self.assertIn('property="og:image:alt"', html)
        self.assertIn('name="twitter:card" content="summary_large_image"', html)
        self.assertIn('name="twitter:image" content="https://gandalf.sh/og.png"', html)
        self.assertIn('name="twitter:image:alt"', html)

    def test_home_and_docs_share_header_and_footer_navigation(self) -> None:
        landing_header = re.search(
            r'<nav class="nav-links" aria-label="Primary">(.*?)</nav>',
            _html(),
            re.S,
        )
        docs_header = re.search(
            r'<header class="nav">(.*?)</header>',
            _docs_html(),
            re.S,
        )
        docs_nav_match = re.search(
            r'<nav class="nav-links" aria-label="Primary">(.*?)</nav>',
            _docs_html(),
            re.S,
        )

        self.assertIsNotNone(landing_header)
        self.assertIsNotNone(docs_header)
        self.assertIsNotNone(docs_nav_match)

        landing_nav = landing_header.group(1)
        docs_header_html = docs_header.group(1)
        docs_nav = docs_nav_match.group(1)

        self.assertLess(landing_nav.index('href="/#install"'), landing_nav.index('href="/#faq"'))
        self.assertLess(landing_nav.index('href="/#faq"'), landing_nav.index('href="/docs/"'))
        self.assertIn('href="/docs/"', landing_nav)
        self.assertNotIn('href="/">Home</a>', landing_nav)

        self.assertLess(
            docs_header_html.index('class="home-icon-link" href="/"'),
            docs_header_html.index('class="home-nav" href="/"'),
        )
        self.assertLess(
            docs_header_html.index('class="home-nav" href="/"'),
            docs_header_html.index('<nav class="nav-links"'),
        )
        self.assertLess(docs_nav.index('href="#quick-install"'), docs_nav.index('href="/#faq"'))
        self.assertLess(docs_nav.index('href="/#faq"'), docs_nav.index('href="/docs/"'))
        self.assertIn(
            '<a class="home-icon-link" href="/" aria-label="Gandalf home">', docs_header_html
        )
        self.assertIn('src="/favicon-32x32.png"', docs_header_html)
        self.assertIn("border-radius: 999px;", _docs_html())
        self.assertIn('<a class="home-nav" href="/">Home</a>', docs_header_html)
        self.assertNotIn('href="/">Home</a>', docs_nav)
        self.assertNotIn('href="/#install"', docs_nav)
        self.assertIn('href="/docs/"', docs_nav)

        self.assertIn('href="/#install"', landing_nav)
        self.assertNotIn('href="#quick-install"', landing_nav)

        for html in (_html(), _docs_html()):
            self.assertIn('<nav class="nav-links" aria-label="Primary">', html)
            self.assertIn('href="/#faq"', html)
            self.assertIn(">FAQ</a", html)
            self.assertIn(">Install</a", html)
            self.assertIn('href="/docs/"', html)
            self.assertIn('class="source-nav github-nav"', html)
            self.assertIn('aria-label="View source on GitHub"', html)
            self.assertIn('data-tooltip="View Source Code"', html)
            self.assertIn('<span class="sr-only">Source on GitHub</span>', html)
            self.assertIn('<nav class="footer-links" aria-label="Footer">', html)
            self.assertIn('href="/docs/"', html)
            self.assertIn('href="https://github.com/mannanj/skillguard"', html)
            self.assertIn('href="https://mannan.is"', html)
            self.assertNotIn('<span class="brand-mark"', html)
            self.assertNotIn("<span>Gandalf</span>", html)
            self.assertNotIn('class="primary-link"', html)
            self.assertNotIn(".nav-links .primary-link", html)

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
        self.assertIn("var landingExperiment = {", html)
        self.assertIn('goal: "install-intent"', html)
        self.assertIn('testedSlot: "headline"', html)
        self.assertIn('new URLSearchParams(window.location.search).get("v")', html)
        self.assertIn("data-landing-variant", html)
        self.assertIn("applyLandingVariant", html)
        self.assertIn("trackConversion", html)
        self.assertIn("gandalf_conversion", html)
        self.assertIn("gandalf:conversion", html)
        self.assertIn('plausible("Gandalf Install Intent"', html)
        self.assertNotIn('<section class="final-cta"', html)

    def test_docs_page_holds_command_reference(self) -> None:
        html = _docs_html()

        self.assertIn(
            "<title>Gandalf docs - install, scan, and runtime checks</title>",
            html,
        )
        self.assertIn('href="/"', html)
        self.assertNotIn('<h1 id="docs-heading">Install, scan, and runtime checks</h1>', html)
        self.assertNotIn(">Landing page</a>", html)
        self.assertIn(".docs-hero .kicker", html)
        self.assertIn("font-size: 15px;", html)
        self.assertIn('id="quick-install"', html)
        self.assertIn('id="first-scan"', html)
        self.assertIn('id="claude-code-plugin"', html)
        self.assertIn('id="codex-plugin"', html)
        self.assertIn('id="command-reference"', html)
        self.assertIn('id="mcp-checks"', html)
        self.assertIn('id="review-flow"', html)
        self.assertIn('id="cache-rescan"', html)
        self.assertIn('id="engines-privacy"', html)
        self.assertIn('id="troubleshooting"', html)
        self.assertIn('id="security-privacy"', html)
        self.assertIn("<code>/plugin marketplace add mannanj/gandalf</code>", html)
        self.assertIn("<code>/plugin install gandalf@gandalf</code>", html)
        self.assertIn("<code>codex plugin add gandalf@personal</code>", html)
        self.assertIn("<code>gandalf --target all --engines local</code>", html)
        self.assertIn("<code>gandalf --target all</code>", html)
        self.assertIn("<code>gandalf --agent-summary</code>", html)
        self.assertIn("<code>gandalf --review</code>", html)
        self.assertIn("<code>gandalf --activity</code>", html)
        self.assertIn("<code>gandalf --install-agent-adapters .</code>", html)
        self.assertIn("<code>gandalf --set-mcp-policy enforce</code>", html)
        self.assertIn(
            "<code>gandalf --target mcps --mcp-introspect --engines local,skillaudit</code>", html
        )
        self.assertIn("mark-fp", html)
        self.assertIn("ack", html)
        self.assertIn("Static MCP scans never launch servers.", html)
        self.assertIn('href="https://mannan.is"', html)

    def test_mascot_assets_are_optimized_web_images(self) -> None:
        png = MASCOT_PNG.read_bytes()
        jpg = LOCKUP_JPG.read_bytes()

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(_png_dimensions(MASCOT_PNG), (480, 588))
        self.assertLess(MASCOT_PNG.stat().st_size, 300_000)

        self.assertTrue(jpg.startswith(b"\xff\xd8\xff"))
        self.assertLess(LOCKUP_JPG.stat().st_size, 150_000)

    def test_favicon_and_social_assets_have_expected_sizes(self) -> None:
        ico = FAVICON_ICO.read_bytes()

        self.assertTrue(ico.startswith(b"\x00\x00\x01\x00"))
        self.assertEqual(_png_dimensions(FAVICON_32), (32, 32))
        self.assertEqual(_png_dimensions(APPLE_TOUCH_ICON), (180, 180))
        self.assertEqual(_png_dimensions(OG_PNG), (1200, 630))
        self.assertLess(OG_PNG.stat().st_size, 500_000)

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
