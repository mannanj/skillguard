#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The Snyk agent-scan engine: wraps the ``snyk-agent-scan`` CLI via ``uvx``."""

from __future__ import annotations

import json
import os
import subprocess

from skillguard.model import Finding, SkillInfo, normalize_severity


class SnykEngine:
    """Snyk agent-scan CLI wrapper."""

    name = "snyk"
    inter_target_delay = 0.0
    unavailable_hint = "Snyk engine: SNYK_TOKEN not set"

    def __init__(self) -> None:
        self.token = os.environ.get("SNYK_TOKEN", "")

    @property
    def available(self) -> bool:
        return bool(self.token)

    def scan(self, skill: SkillInfo) -> list[Finding]:
        if not self.available:
            return []

        findings: list[Finding] = []
        try:
            result = subprocess.run(
                ["uvx", "snyk-agent-scan@latest", "--skills", str(skill.path), "--json"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "SNYK_TOKEN": self.token},
            )

            if result.stdout.strip():
                data = json.loads(result.stdout)
                for issue in (
                    data if isinstance(data, list) else data.get("issues", data.get("findings", []))
                ):
                    if isinstance(issue, dict):
                        severity = normalize_severity(issue.get("severity", "medium"))
                        findings.append(
                            Finding(
                                engine="snyk",
                                severity=severity,
                                category=str(issue.get("code", issue.get("type", "unknown"))),
                                message=str(
                                    issue.get("message", issue.get("description", str(issue)))
                                ),
                                file=issue.get("file", ""),
                                line=issue.get("line", 0),
                            )
                        )

        except FileNotFoundError:
            findings.append(
                Finding(
                    engine="snyk",
                    severity="info",
                    category="engine_error",
                    message="uvx not found. Install uv: https://docs.astral.sh/uv/",
                )
            )
        except subprocess.TimeoutExpired:
            findings.append(
                Finding(
                    engine="snyk",
                    severity="info",
                    category="engine_error",
                    message="Snyk agent-scan timed out (90s limit)",
                )
            )
        except Exception as e:
            findings.append(
                Finding(
                    engine="snyk",
                    severity="info",
                    category="engine_error",
                    message=f"Snyk error: {e}",
                )
            )

        return findings
