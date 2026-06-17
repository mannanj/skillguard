from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


LANDING_HTML = Path(__file__).resolve().parent.parent / "landing" / "public" / "index.html"


def _html() -> str:
    return LANDING_HTML.read_text(encoding="utf-8")


def _scan_items(html: str) -> list[dict[str, str]]:
    match = re.search(r"var scanItems = (\[.*?\]);", html, re.DOTALL)
    assert match, "landing page should define data-driven scan items"
    return json.loads(match.group(1))


class LandingPageTests(unittest.TestCase):
    def test_landing_copy_is_direct_and_install_focused(self) -> None:
        html = _html()
        compact_html = re.sub(r"\s+", " ", html)

        self.assertIn("<title>SkillGuard - trust your agent tools</title>", html)
        self.assertIn('content="SkillGuard - trust your agent tools"', html)
        self.assertIn("<span>Trust</span>your agent tools", html)
        self.assertIn(
            "SkillGuard checks Agent Skills and MCP server",
            html,
        )
        self.assertIn("guarding against malicious behavior", compact_html)
        self.assertNotIn("guarding against prompt injection", html)
        self.assertIn("/plugin marketplace add mannanj/skillguard", html)
        self.assertIn("/plugin install skillguard@skillguard", html)
        self.assertIn("/reload-plugins", html)
        self.assertIn("codex plugin add skillguard@personal", html)
        self.assertIn("Use: /skillguard:skillguard", html)
        self.assertIn("Use: new Codex thread, /skills, $skillguard", html)
        self.assertIn('class="install-box"', html)
        self.assertIn('class="install-tabs"', html)
        self.assertIn('data-platform="claude"', html)
        self.assertIn('data-platform="codex"', html)
        self.assertNotIn('class="install-grid"', html)
        self.assertIn('<h2 id="how-heading">How it works</h2>', html)
        self.assertIn('<h2 id="faq-heading">FAQ</h2>', html)
        self.assertIn('aria-label="SkillGuard home"', html)
        self.assertIn('stroke="#D91F2F"', html)
        self.assertIn("stroke='%23D91F2F'", html)
        self.assertNotIn("#3DDC97", html)
        self.assertNotIn("%233DDC97", html)
        self.assertIn('d="M12 2 4 5v6c0 5 3.5 8.5 8 10 4.5-1.5 8-5 8-10V5l-8-3Z"', html)
        self.assertNotIn('class="mark-box"', html)
        self.assertNotIn('aria-hidden="true">!</span>', html)

    def test_animation_keeps_original_wall_ui(self) -> None:
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
        self.assertNotIn('class="scanner"', html)
        self.assertNotIn('class="scan-stage"', html)
        self.assertNotIn('class="skill-card"', html)
        self.assertNotIn('class="scan-count"', html)
        self.assertNotIn('class="reset-btn"', html)
        self.assertNotIn('id="scanCount"', html)
        self.assertNotIn('id="scanReset"', html)

    def test_scan_animation_uses_25_realistic_skill_names(self) -> None:
        items = _scan_items(_html())

        self.assertEqual(len(items), 25)
        names = {item["name"] for item in items}
        self.assertTrue({"docs-helper", "release-notes", "skillguard"}.issubset(names))
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

    def test_scan_animation_updates_old_wall_text_from_25_skill_items(self) -> None:
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
