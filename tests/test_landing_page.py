from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LANDING_HTML = ROOT / "landing" / "public" / "index.html"
MASCOT_SVG = ROOT / "landing" / "public" / "gandalf-mascot.svg"


def _html() -> str:
    return LANDING_HTML.read_text(encoding="utf-8")


def _scan_items(html: str) -> list[dict[str, str]]:
    match = re.search(r"var scanItems = (\[.*?\]);", html, re.DOTALL)
    assert match, "landing page should define data-driven scan items"
    return json.loads(match.group(1))


class LandingPageTests(unittest.TestCase):
    def test_landing_copy_is_gandalf_first_and_install_focused(self) -> None:
        html = _html()
        compact_html = re.sub(r"\s+", " ", html)

        self.assertIn("<title>Gandalf - Thou shall not pass.</title>", html)
        self.assertIn('content="Gandalf - Thou shall not pass."', html)
        self.assertIn('href="https://gandalf.sh/"', html)
        self.assertIn('aria-label="Gandalf home"', html)
        self.assertIn('src="/gandalf-mascot.svg"', html)
        self.assertIn(">Gandalf</h1>", html)
        self.assertIn("Thou shall not pass.", html)
        self.assertIn("Block unsafe skills before they run.", html)
        self.assertIn(
            "Gandalf checks Claude Code skills and MCP servers",
            compact_html,
        )
        self.assertIn("0 commands ran.", html)
        self.assertIn("No scan. No run.", html)
        self.assertIn("curl -fsSL https://gandalf.sh/install | sh", html)
        self.assertIn("gandalf --target all --engines local", html)
        self.assertIn("/plugin marketplace add mannanj/gandalf", html)
        self.assertIn("/plugin install gandalf@gandalf", html)
        self.assertIn("codex plugin add gandalf@personal", html)
        self.assertIn('data-platform="shell"', html)
        self.assertIn('data-platform="claude"', html)
        self.assertIn('data-platform="codex"', html)
        self.assertIn("<h2 id=\"how-heading\">Scan. Decide. Enforce. Remember.</h2>", html)
        self.assertIn("<h2 id=\"install-heading\">", html)
        self.assertIn("<h2 id=\"faq-heading\">Sharp answers only.</h2>", html)
        self.assertNotIn("SkillGuard - trust your agent tools", html)
        self.assertNotIn("<span>Trust</span>your agent tools", html)
        self.assertNotIn("guarding against malicious behavior", html)

    def test_mascot_asset_matches_black_white_cartoon_direction(self) -> None:
        svg = MASCOT_SVG.read_text(encoding="utf-8")

        self.assertIn("<title id=\"title\">Gandalf mascot</title>", svg)
        self.assertIn("black and white cartoon wizard guard", svg)
        self.assertIn("viewBox=\"0 0 720 560\"", svg)
        self.assertIn("stroke=\"#070707\"", svg)
        self.assertIn("fill=\"#fff\"", svg)
        self.assertIn("glasses", svg)
        self.assertNotIn("<text", svg)

    def test_animation_keeps_runtime_gate_ui(self) -> None:
        html = _html()

        self.assertIn('class="wall"', html)
        self.assertIn('class="wall-stage"', html)
        self.assertIn('class="request-card blocked-card"', html)
        self.assertIn('class="request-card good-one"', html)
        self.assertIn('class="request-card good-two"', html)
        self.assertIn('class="stamp stamp-block"', html)
        self.assertIn('class="stamp stamp-pass stamp-good-one"', html)
        self.assertIn('class="stamp stamp-pass stamp-good-two"', html)
        self.assertIn('class="receipt"', html)
        self.assertIn('class="receipt-grid"', html)
        self.assertIn("@keyframes bad-block", html)
        self.assertIn("@keyframes good-one-pass", html)
        self.assertIn("@keyframes good-two-pass", html)
        self.assertIn("animation: bad-block 5s", html)
        self.assertIn("Gandalf gating runtime calls", html)
        self.assertNotIn('class="scanner"', html)
        self.assertNotIn('class="scan-stage"', html)
        self.assertNotIn('class="skill-card"', html)
        self.assertNotIn('id="scanCount"', html)
        self.assertNotIn('id="scanReset"', html)

    def test_scan_animation_uses_25_realistic_skill_names(self) -> None:
        items = _scan_items(_html())

        self.assertEqual(len(items), 25)
        names = {item["name"] for item in items}
        self.assertTrue({"docs-helper", "release-notes", "gandalf"}.issubset(names))
        self.assertTrue(
            {
                "reverse-shell-helper",
                "browser-cookie-exporter",
                "ssh-key-harvester",
                "env-token-relay",
                "repo-wiper",
            }.issubset(names)
        )
        self.assertEqual({item["verdict"] for item in items}, {"approved", "blocked"})
        self.assertGreaterEqual(sum(item["verdict"] == "blocked" for item in items), 8)
        self.assertTrue(all(item["summary"] for item in items))

    def test_scan_animation_updates_wall_text_from_skill_items(self) -> None:
        html = _html()

        self.assertIn('id="blockedName"', html)
        self.assertIn('id="blockedRisk"', html)
        self.assertIn('id="goodOneName"', html)
        self.assertIn('id="goodTwoName"', html)
        self.assertIn('id="receiptBlocked"', html)
        self.assertIn('id="receiptPassed"', html)
        self.assertIn("nextItemByVerdict", html)
        self.assertIn("completedCount += 1", html)
        self.assertIn("completedCount >= scanItems.length", html)
        self.assertIn("blockedNames.push(item.name)", html)
        self.assertIn("passedNames.push(item.name)", html)
        self.assertIn('join(", ")', html)
        self.assertIn("cycleMs = reduceMotion ? 4000 : 5000", html)
        self.assertIn("blockedName.textContent", html)
        self.assertIn("nameNode.textContent", html)
        self.assertIn("receiptBlocked.textContent", html)
        self.assertIn("receiptPassed.textContent", html)
        self.assertIn("setInterval(advanceScan", html)
        self.assertNotIn("receiptGrid.prepend", html)
        self.assertNotIn("request-card--blocked", html)
        self.assertNotIn("request-card--approved", html)


if __name__ == "__main__":
    unittest.main()
