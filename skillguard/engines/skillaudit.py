#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The SkillAudit REST API engine (skillaudit.vercel.app)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from skillguard import branding
from skillguard.discovery import rel_to
from skillguard.model import Finding, SkillInfo, normalize_severity

SKILLAUDIT_BASE = os.environ.get(
    f"{branding.ENV_PREFIX}SKILLAUDIT_BASE", "https://skillaudit.vercel.app"
)
# Delay between SkillAudit API calls (default respects the 30 req/min limit)
SKILLAUDIT_DELAY = float(os.environ.get(f"{branding.ENV_PREFIX}SKILLAUDIT_DELAY", "2.1"))


class SkillAuditEngine:
    """SkillAudit.vercel.app REST API scanner."""

    name = "skillaudit"
    available = True
    # Throttle between targets to respect the API's 30 req/min limit. The
    # dispatcher reads this generically; no engine-name special-case.
    inter_target_delay = SKILLAUDIT_DELAY

    def scan(self, skill: SkillInfo) -> list[Finding]:
        findings: list[Finding] = []

        # Collect file contents for multi-file scan
        files_payload: list[dict] = []
        for file_path in skill.files[:30]:  # API limit: 30 files
            try:
                content = file_path.read_text(errors="replace")
                rel = rel_to(file_path, skill.path)
                files_payload.append({"name": rel, "content": content})
            except OSError:
                continue

        if not files_payload:
            return []

        # Use /scan/files for multi-file analysis
        try:
            payload = json.dumps(
                {
                    "projectName": skill.name,
                    "files": files_payload,
                }
            ).encode()

            req = urllib.request.Request(
                f"{SKILLAUDIT_BASE}/scan/files",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())

            # Parse findings from response. /scan/files nests them under
            # files[].topFindings ({severity, name, rule, line}); accept a
            # top-level findings list too for older response shapes.
            raw_findings: list[dict] = list(data.get("findings", []))
            for file_entry in data.get("files", []):
                file_name = file_entry.get("file", "")
                for nested in file_entry.get("topFindings", []):
                    entry = dict(nested)
                    entry.setdefault("file", file_name)
                    raw_findings.append(entry)

            for f in raw_findings:
                # SkillAudit layers its own risk vocabulary ("clean", "moderate")
                # on top of the standard severities; translate those first, then
                # defer to the shared normalizer for the unknown → medium clamp.
                raw_sev = str(f.get("severity", f.get("level", "medium"))).lower()
                risk_map = {"clean": "info", "moderate": "medium"}
                severity = risk_map.get(raw_sev, normalize_severity(raw_sev))

                findings.append(
                    Finding(
                        engine="skillaudit",
                        severity=severity,
                        category=f.get("category", f.get("rule", f.get("ruleId", "unknown"))),
                        message=f.get("message", f.get("description", f.get("name", str(f)))),
                        file=f.get("file", ""),
                        line=f.get("line", 0),
                        context=f.get("context", f.get("evidence", ""))[:120],
                    )
                )

            # topFindings is capped per file: never let a truncated list
            # read as the complete report.
            total = data.get("totalFindings", 0)
            if isinstance(total, int) and total > len(raw_findings):
                findings.append(
                    Finding(
                        engine="skillaudit",
                        severity="info",
                        category="truncated",
                        message=(
                            f"SkillAudit reported {total} finding(s), "
                            f"{len(raw_findings)} returned in topFindings; "
                            "see the per-file SkillAudit report for the rest."
                        ),
                    )
                )

        except urllib.error.HTTPError as e:
            if e.code == 429:
                findings.append(
                    Finding(
                        engine="skillaudit",
                        severity="info",
                        category="rate_limited",
                        message="SkillAudit API rate limited (30 req/min). Try again later.",
                    )
                )
            else:
                findings.append(
                    Finding(
                        engine="skillaudit",
                        severity="info",
                        category="engine_error",
                        message=f"SkillAudit API error: HTTP {e.code}",
                    )
                )
        except Exception as e:
            findings.append(
                Finding(
                    engine="skillaudit",
                    severity="info",
                    category="engine_error",
                    message=f"SkillAudit error: {e}",
                )
            )

        return findings
