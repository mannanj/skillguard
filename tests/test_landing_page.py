from __future__ import annotations

import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANDING_HTML = ROOT / "landing" / "public" / "index.html"
GANDALF_PREVIEW_HTML = ROOT / "landing" / "public" / "gandalf" / "index.html"
DOCS_HTML = ROOT / "landing" / "public" / "docs" / "index.html"
DEMO_VIDEO = ROOT / "landing" / "public" / "demo.mp4"
DEMO_POSTER = ROOT / "landing" / "public" / "demo-poster.png"
OG_PNG = ROOT / "landing" / "public" / "og.png"
FAVICON_ICO = ROOT / "landing" / "public" / "favicon.ico"
FAVICON_32 = ROOT / "landing" / "public" / "favicon-32x32.png"
APPLE_TOUCH_ICON = ROOT / "landing" / "public" / "apple-touch-icon.png"
LANDING_WORKER = ROOT / "landing" / "src" / "index.js"
WRANGLER_CONFIG = ROOT / "landing" / "wrangler.jsonc"


def _html() -> str:
    return LANDING_HTML.read_text(encoding="utf-8")


def _gandalf_preview_html() -> str:
    return GANDALF_PREVIEW_HTML.read_text(encoding="utf-8")


def _docs_html() -> str:
    return DOCS_HTML.read_text(encoding="utf-8")


def _worker() -> str:
    return LANDING_WORKER.read_text(encoding="utf-8")


def _wrangler() -> str:
    return WRANGLER_CONFIG.read_text(encoding="utf-8")


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    return struct.unpack(">II", data[16:24])


class LandingPageTests(unittest.TestCase):
    def test_landing_is_skillguard_first_and_install_focused(self) -> None:
        html = _html()
        compact_html = re.sub(r"\s+", " ", html)

        self.assertIn(
            "<title>SkillGuard - Scan agent skills before runtime</title>",
            html,
        )
        self.assertIn('href="https://skillguard.sh/"', html)
        self.assertIn('property="og:site_name" content="SkillGuard"', html)
        self.assertIn('property="og:url" content="https://skillguard.sh/"', html)
        self.assertIn('name="twitter:image" content="https://skillguard.sh/og.png"', html)
        self.assertIn('<h1 id="hero-heading">SkillGuard</h1>', html)
        self.assertIn("Scan skills and MCP servers locally.", compact_html)
        self.assertIn("Stop changed or unscanned tools at runtime.", compact_html)
        self.assertIn('href="#install"', html)
        self.assertIn('href="#faq"', html)
        self.assertIn('href="/docs/"', html)
        self.assertIn('href="https://github.com/mannanj/skillguard"', html)
        self.assertIn("Copy install", html)
        self.assertIn("curl -fsSL https://skillguard.sh/install | sh", html)
        self.assertIn("skillguard --target all --engines local", html)
        self.assertIn('poster="/demo-poster.png"', html)
        self.assertIn('<source src="/demo.mp4" type="video/mp4" />', html)

    def test_landing_content_covers_evidence_methods_install_and_faq(self) -> None:
        html = _html()
        compact_html = re.sub(r"\s+", " ", html)

        self.assertIn("Agent tooling is a supply chain now.", compact_html)
        self.assertIn("341", html)
        self.assertIn("13.4%", html)
        self.assertIn("https://www.koi.ai/blog/clawhavoc-341", html)
        self.assertIn("https://snyk.io/blog/toxicskills", html)
        self.assertIn("The gate has three jobs.", compact_html)
        self.assertIn("Read the whole tool surface", compact_html)
        self.assertIn("Refuse what has not cleared", compact_html)
        self.assertIn("Remember every decision", compact_html)
        self.assertIn('id="install"', html)
        self.assertIn('data-platform="local"', html)
        self.assertIn('data-platform="claude"', html)
        self.assertIn('data-platform="codex"', html)
        self.assertIn('data-platform="adapters"', html)
        self.assertIn("Questions security teams ask first.", compact_html)
        self.assertIn("What does SkillGuard scan?", compact_html)
        self.assertIn("Does it block MCP tool calls?", compact_html)

    def test_install_modes_match_current_skillguard_commands(self) -> None:
        html = _html()

        self.assertIn("/plugin marketplace add mannanj/skillguard", html)
        self.assertIn("/plugin install skillguard@skillguard", html)
        self.assertIn("codex plugin add skillguard@personal", html)
        self.assertIn("skillguard --install-agent-adapters .", html)
        self.assertNotIn("/plugin marketplace add mannanj/gandalf", html)
        self.assertNotIn("/plugin install gandalf@gandalf", html)
        self.assertNotIn("codex plugin add gandalf@personal", html)
        self.assertNotIn("gandalf --target all", html)

    def test_landing_has_conversion_and_copy_hooks(self) -> None:
        html = _html()

        self.assertIn('data-conversion-goal="install-intent"', html)
        self.assertIn('data-primary-cta="install"', html)
        self.assertIn('data-conversion-action="copy-install-command"', html)
        self.assertIn("trackConversion", html)
        self.assertIn("skillguard_conversion", html)
        self.assertIn("skillguard:conversion", html)
        self.assertIn('plausible("SkillGuard Install Intent"', html)
        self.assertIn("navigator.clipboard.writeText", html)
        self.assertIn("document.execCommand", html)
        self.assertIn("copy-install-command-line", html)

    def test_landing_does_not_render_old_gandalf_brand_or_ai_tells(self) -> None:
        html = _html()

        self.assertNotIn("Gandalf", html)
        self.assertNotIn("gandalf", html)
        self.assertNotIn("Thou shall not pass", html)
        self.assertNotIn("No scan. No run.", html)
        self.assertNotIn("Quietly", html)
        self.assertNotIn("SECTION", html)
        self.assertNotIn("QUESTION", html)
        self.assertNotIn("BETA", html)
        self.assertNotIn("ALPHA", html)
        self.assertNotIn("—", html)
        self.assertNotIn("–", html)

    def test_gandalf_preview_page_is_separate_route(self) -> None:
        html = _gandalf_preview_html()
        compact_html = re.sub(r"\s+", " ", html)

        self.assertIn("<title>Gandalf - Thou shall not pass.</title>", html)
        self.assertIn('href="/gandalf/"', html)
        self.assertIn('href="/">SkillGuard</a>', html)
        self.assertIn('<h1 id="hero-heading">Gandalf</h1>', html)
        self.assertIn("Thou shall not pass.", compact_html)
        self.assertIn(
            "Check agent skills and MCPs on Claude, Codex, and other agent harnesses"
            " before runtime",
            compact_html,
        )
        self.assertIn('class="mascot"', html)
        self.assertIn('src="/gandalf-mascot.png"', html)
        self.assertIn('id="install"', html)
        self.assertIn('id="faq"', html)
        self.assertNotIn('id="how"', html)

    def test_gandalf_preview_has_install_modes_and_stays_short(self) -> None:
        html = _gandalf_preview_html()

        self.assertIn("gandalf --target all --engines local", html)
        self.assertIn("/plugin marketplace add mannanj/gandalf", html)
        self.assertIn("/plugin install gandalf@gandalf", html)
        self.assertIn("codex plugin add gandalf@personal", html)
        self.assertIn("gandalf --install-agent-adapters .", html)
        self.assertIn('event: "gandalf_conversion"', html)
        self.assertNotIn("data-threat=", html)
        self.assertNotIn("GANDALF: THOU SHALL NOT PASS", html)
        self.assertNotIn('class="hero-mascot"', html)
        self.assertNotIn("gandalf-mascot-v2.svg", html)
        self.assertNotIn("gandalf-lockup.jpg", html)
        self.assertNotIn('window.addEventListener("scroll"', html)
        self.assertNotIn("h-screen", html)
        self.assertNotIn("—", html)
        self.assertNotIn("–", html)
        self.assertLess(
            html.count("<section"),
            4,
            "gandalf preview should stay to hero/strip/faq, not regrow extra sections",
        )

    def test_docs_page_is_skillguard_branded_and_holds_command_reference(self) -> None:
        html = _docs_html()
        compact_html = re.sub(r"\s+", " ", html)

        self.assertIn(
            "<title>SkillGuard docs - install, scan, and runtime checks</title>",
            html,
        )
        self.assertIn('href="https://skillguard.sh/docs/"', html)
        self.assertIn("SkillGuard scans agent skills and MCP servers", compact_html)
        self.assertIn('id="quick-install"', html)
        self.assertIn('id="first-scan"', html)
        self.assertIn('id="command-reference"', html)
        self.assertIn('id="mcp-checks"', html)
        self.assertIn('id="troubleshooting"', html)
        self.assertIn("<code>/plugin marketplace add mannanj/skillguard</code>", html)
        self.assertIn("<code>/plugin install skillguard@skillguard</code>", html)
        self.assertIn("<code>codex plugin add skillguard@personal</code>", html)
        self.assertIn("<code>skillguard --target all --engines local</code>", html)
        self.assertIn("<code>skillguard --review</code>", html)
        self.assertIn("<code>skillguard --set-mcp-policy warn</code>", html)
        self.assertIn(
            "<code>skillguard --target mcps --mcp-introspect --engines local,skillaudit</code>",
            html,
        )
        self.assertNotIn("Gandalf", html)
        self.assertNotIn("gandalf", html)

    def test_home_and_docs_share_core_navigation(self) -> None:
        landing = _html()
        docs = _docs_html()

        for html in (landing, docs):
            self.assertIn('<nav class="nav-links" aria-label="Primary">', html)
            self.assertIn('href="/docs/"', html)
            self.assertIn('href="https://github.com/mannanj/skillguard"', html)
            self.assertIn('<nav class="footer-links" aria-label="Footer">', html)
            self.assertIn('href="https://mannan.is"', html)

        self.assertIn('href="#install"', landing)
        self.assertIn('href="#faq"', landing)
        self.assertIn('href="#quick-install"', docs)
        self.assertIn('href="/#faq"', docs)

    def test_github_stars_badge_is_dynamic(self) -> None:
        html = _html()

        self.assertIn('id="githubStars"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('fetch("/api/github-repo"', html)
        self.assertIn("formatStars", html)

    def test_worker_caches_github_repo_metadata_and_redirects_hosts(self) -> None:
        worker = _worker()
        wrangler = _wrangler()

        self.assertIn('url.pathname === "/api/github-repo"', worker)
        self.assertIn("https://api.github.com/repos/mannanj/skillguard", worker)
        self.assertIn('"User-Agent": "skillguard.sh"', worker)
        self.assertIn("stargazers_count", worker)
        self.assertIn("caches.default", worker)
        self.assertIn("Cache-Control", worker)
        self.assertIn('url.hostname === "www.skillguard.sh"', worker)
        self.assertIn('url.hostname === "gandalf.sh"', worker)
        self.assertIn('url.hostname = "skillguard.sh"', worker)
        self.assertIn('"name": "skillguard"', wrangler)
        self.assertIn('"pattern": "skillguard.sh"', wrangler)
        self.assertIn('"pattern": "www.skillguard.sh"', wrangler)

    def test_visual_assets_are_valid_web_assets(self) -> None:
        ico = FAVICON_ICO.read_bytes()
        video = DEMO_VIDEO.read_bytes()

        self.assertTrue(ico.startswith(b"\x00\x00\x01\x00"))
        self.assertTrue(video[4:8] == b"ftyp")
        self.assertEqual(_png_dimensions(FAVICON_32), (32, 32))
        self.assertEqual(_png_dimensions(APPLE_TOUCH_ICON), (180, 180))
        self.assertEqual(_png_dimensions(OG_PNG), (1200, 630))
        self.assertGreater(DEMO_POSTER.stat().st_size, 50_000)
        self.assertLess(OG_PNG.stat().st_size, 500_000)

    def test_runtime_wall_animation_stays_removed(self) -> None:
        html = _html()

        self.assertNotIn('class="wall"', html)
        self.assertNotIn('class="wall-stage"', html)
        self.assertNotIn('class="request-card blocked-card"', html)
        self.assertNotIn('class="stamp stamp-block"', html)
        self.assertNotIn("@keyframes bad-block", html)
        self.assertNotIn("@keyframes good-one-pass", html)
        self.assertNotIn("animation: bad-block 5s", html)


if __name__ == "__main__":
    unittest.main()
