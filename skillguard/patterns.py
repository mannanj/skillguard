#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The local-engine detection ruleset: 50+ regex patterns.

``LOCAL_PATTERNS`` is the single registry of ``(category, severity, compiled
regex, description)`` tuples that ``LocalEngine`` scans every line against. It is
built once at import via ``_p``. ``cli`` re-exports ``LOCAL_PATTERNS`` for
back-compat; ``skillguard.engines.local`` imports it directly.
"""

from __future__ import annotations

import re

# Each pattern: (category, severity, compiled_regex, description)
LOCAL_PATTERNS: list[tuple[str, str, re.Pattern, str]] = []


def _p(cat: str, sev: str, pattern: str, desc: str) -> None:
    """Register a detection pattern."""
    LOCAL_PATTERNS.append((cat, sev, re.compile(pattern, re.IGNORECASE), desc))


_VENDOR_INSTALL_URL = re.compile(
    r"(?:resend|tailscale)\.com/install\.(?:sh|ps1)|code-server\.dev/install\.sh",
    re.IGNORECASE,
)

_PLACEHOLDER_WEBHOOK_SITE = re.compile(
    r"webhook\.site/(?:\.\.\.|…)(?:[\"'`)\],}\s;]|$)",
    re.IGNORECASE,
)


def is_vendor_install_pipe(line: str) -> bool:
    """True when a curl|sh/bash line documents an official vendor install script.

    Hoisted beside ``is_markdown_table_row`` so ``LocalEngine`` and any future
    adapter can share the same suppression instead of re-deriving it.
    """
    if not re.search(r"\|\s*(?:ba)?sh\b", line, re.IGNORECASE):
        return False
    return bool(_VENDOR_INSTALL_URL.search(line))


def is_placeholder_webhook_site(line: str) -> bool:
    """True for non-routable ``webhook.site/...`` documentation placeholders.

    Real webhook.site collector paths still flag; only the literal ellipsis
    placeholder is suppressed.
    """
    return bool(_PLACEHOLDER_WEBHOOK_SITE.search(line))


def is_cloudflared_service_management(line: str) -> bool:
    """True for Cloudflare Tunnel service lifecycle examples.

    Keep the generic systemd rule active for unknown services; only suppress
    lines where every systemctl lifecycle command targets ``cloudflared``.
    """
    commands = re.findall(
        r"\bsystemctl\s+(?:enable|start|restart)\s+([^\s;&|]+)",
        line,
        flags=re.IGNORECASE,
    )
    return bool(commands) and all(service.lower() == "cloudflared" for service in commands)


def is_prompt_injection_education_line(line: str) -> bool:
    """True for explicit prompt-injection teaching examples, not directives."""
    lower = line.strip().lower()
    return lower.startswith(("**classic scenario:**", "classic scenario:"))


def is_explicit_non_finding_line(line: str) -> bool:
    """True when prose explicitly labels an example as non-actionable.

    This is deliberately narrow. It catches documentation guardrails such as
    "not a finding" without treating every security-themed paragraph as safe.
    """
    lower = line.lower()
    return any(
        phrase in lower
        for phrase in (
            "not a finding",
            "must not flag",
            "should not flag",
            "false positive",
        )
    )


def is_markdown_table_row(line: str) -> bool:
    """True if ``line`` is a markdown table row or separator (three or more ``|``).

    Hoisted out of ``LocalEngine`` so engines that lack their own documentation-
    table suppression (e.g. a Cisco post-filter) can reuse the *exact* same rule
    instead of re-deriving it and drifting. Pipe-counting is unaffected by leading
    or trailing whitespace, so callers may pass a stripped or raw line.
    """
    return "|" in line and line.count("|") >= 3


def is_package_cache_cleanup(line: str) -> bool:
    """True for common package-manager cache cleanup, not destructive deletion."""
    lower = line.lower()
    return bool(re.search(r"\brm\s+-rf\s+/var/lib/apt/lists/?\*", lower))


# --- Reverse shells & RCE (CRITICAL) ---
_p("reverse_shell", "critical", r"/dev/tcp/", "Reverse shell via /dev/tcp")
_p("reverse_shell", "critical", r"nc\s+(-e|-c)\s+", "Netcat reverse shell")
_p("reverse_shell", "critical", r"bash\s+-i\s+>&?\s*/dev/", "Bash interactive reverse shell")
_p(
    "reverse_shell",
    "critical",
    r"python[23]?\s+-c\s+['\"]import\s+socket",
    "Python socket reverse shell",
)
_p("reverse_shell", "critical", r"mkfifo\s+/tmp/", "Named pipe reverse shell")
_p("reverse_shell", "critical", r"socat\s+exec:", "Socat reverse shell")

# --- Data exfiltration (CRITICAL) ---
_p("data_exfil", "critical", r"webhook\.site", "Data exfiltration via webhook.site")
_p("data_exfil", "critical", r"requestbin\.(com|net)", "Data exfiltration via requestbin")
_p("data_exfil", "critical", r"burpcollaborator\.net", "Data exfiltration via Burp Collaborator")
_p(
    "data_exfil",
    "critical",
    r"(?:curl|wget|nc)\s+[^\n]{0,160}ngrok\.(io|com|app)",
    "Data exfiltration via ngrok tunnel",
)
_p("data_exfil", "critical", r"pipedream\.net", "Data exfiltration via Pipedream")
_p("data_exfil", "critical", r"interact\.sh", "Data exfiltration via interactsh")

# --- Prompt injection (HIGH) ---
_p(
    "prompt_injection",
    "high",
    r"ignore\s+(all\s+)?previous\s+instructions",
    "Prompt injection: ignore previous instructions",
)
_p(
    "prompt_injection",
    "high",
    r"forget\s+(all\s+)?(your|prior)\s+instructions",
    "Prompt injection: forget instructions",
)
_p(
    "prompt_injection",
    "high",
    r"you\s+are\s+now\s+(a|an)\s+",
    "Prompt injection: role reassignment",
)
_p(
    "prompt_injection",
    "high",
    r"disregard\s+(all\s+)?(prior|previous|above)",
    "Prompt injection: disregard prior",
)
_p("prompt_injection", "high", r"new\s+system\s+prompt", "Prompt injection: new system prompt")
_p(
    "prompt_injection",
    "high",
    r"override\s+your\s+(instructions|rules|guidelines)",
    "Prompt injection: override rules",
)
_p("prompt_injection", "high", r"\bjailbreak\s+mode\b", "Prompt injection: jailbreak mode")

# --- Selection manipulation (description framing that games skill-selection) ---
# Distinct from prompt_injection: these do not override the agent's instructions,
# they game which skill the agent *picks*. The skill name + description are
# injected into the system prompt and drive selection, so (unlike every other
# category) LocalEngine scans the frontmatter for these — see engines/local.py.
# Deliberately high-precision: phrasings with near-zero legitimate use. Fuzzier
# recency/superlative framing ("most up-to-date", "best") is left to a semantic
# engine because it is not separable from honest description by regex.
#
# HIGH — anti-competitive directives that suppress alternative skills.
_p(
    "selection_manipulation",
    "high",
    r"ignore\s+(?:all\s+|any\s+|the\s+)?other\s+skills?\b",
    "Selection manipulation: tells the agent to ignore other skills",
)
_p(
    "selection_manipulation",
    "high",
    r"(?:do\s+not|don['’]?t)\s+use\s+(?:any\s+)?(?:other\s+)?skills?\b",
    "Selection manipulation: tells the agent not to use other skills",
)
_p(
    "selection_manipulation",
    "high",
    r"(?:always\s+)?(?:use|prefer|choose|select)\s+this\s+skill\s+"
    r"(?:instead\s+of|over|rather\s+than|in\s+place\s+of)\b",
    "Selection manipulation: tells the agent to prefer this skill over others",
)
_p(
    "selection_manipulation",
    "high",
    r"\bthe\s+only\s+skill\s+(?:you\s+)?(?:should|must|need|ever)\b",
    "Selection manipulation: claims to be the only skill the agent should use",
)
# MEDIUM — unverifiable trust / authority / safety framing.
_p(
    "selection_manipulation",
    "medium",
    r"official(?:ly)?\s+(?:verified|approved|endorsed|certified|sanctioned)\b",
    "Selection manipulation: unverifiable official-verification claim",
)
_p(
    "selection_manipulation",
    "medium",
    r"\b(?:anthropic|claude|openai)[\s-]+(?:approved|verified|endorsed|certified|trusted)\b",
    "Selection manipulation: claims vendor approval or endorsement",
)
_p(
    "selection_manipulation",
    "medium",
    r"\b(?:100\s*%|guaranteed)\s+(?:safe|secure|trusted|trustworthy)\b",
    "Selection manipulation: absolute safety guarantee",
)
_p(
    "selection_manipulation",
    "medium",
    r"\b(?:fully|completely)\s+(?:trusted|trustworthy)\b",
    "Selection manipulation: absolute trust claim",
)

# --- Environment variable exfiltration (HIGH) ---
_p("env_exfil", "high", r"cat\s+(/etc/passwd|/etc/shadow)", "Reading system password files")
_p("env_exfil", "high", r"printenv\s*\|", "Piping environment variables")
_p("env_exfil", "high", r"env\s*\|\s*(curl|wget|nc)", "Exfiltrating env vars via network")
_p("env_exfil", "high", r"\$\{?[A-Z_]*KEY[A-Z_]*\}?\s*[|>]", "Piping API keys")
_p("env_exfil", "high", r"\$\{?[A-Z_]*SECRET[A-Z_]*\}?\s*[|>]", "Piping secrets")
_p("env_exfil", "high", r"\$\{?[A-Z_]*TOKEN[A-Z_]*\}?\s*[|>]", "Piping tokens")

# --- Credential theft (HIGH) ---
_p(
    "credential_theft",
    "high",
    r"~/.ssh/(id_rsa|id_ed25519|config|known_hosts)",
    "Accessing SSH keys/config",
)
_p("credential_theft", "high", r"~/.aws/(credentials|config)", "Accessing AWS credentials")
_p("credential_theft", "high", r"~/.gcloud/", "Accessing GCloud credentials")
_p("credential_theft", "high", r"~/.kube/config", "Accessing Kubernetes config")
_p("credential_theft", "high", r"~/.npmrc", "Accessing npm auth token")
_p("credential_theft", "high", r"~/.netrc", "Accessing netrc credentials")
_p(
    "credential_theft",
    "high",
    r"KeychainAccess|security\s+(?:find-generic-password|find-internet-password|dump-keychain|unlock-keychain)\b",
    "Accessing system keychain",
)
_p("credential_theft", "high", r"seed\s*phrase", "References to seed phrases")
_p("credential_theft", "high", r"wallet\.dat|MetaMask", "Crypto wallet access")

# --- Shell pipe execution (HIGH) ---
_p("shell_pipe", "high", r"curl\s+[^\n]*\|\s*(?:ba)?sh\b", "curl piped to shell execution")
_p("shell_pipe", "high", r"wget\s+[^\n]*\|\s*(?:ba)?sh\b", "wget piped to shell execution")
_p("shell_pipe", "high", r"curl\s+[^\n]*\|\s*python", "curl piped to Python execution")

# --- Obfuscation (HIGH) ---
_p(
    "obfuscation",
    "high",
    r"(?:eval|exec|Function)\s*\([^)]*(?:base64\.b64decode|b64decode|atob)\s*\(",
    "Base64 decoding execution",
)
_p(
    "obfuscation",
    "high",
    r"base64\s+--?(?:d|decode)\b[^\n]*\|\s*(?:ba)?sh\b",
    "Base64 decoding piped to shell",
)
_p(
    "obfuscation",
    "high",
    r"\\x[0-9a-f]{2}\\x[0-9a-f]{2}\\x[0-9a-f]{2}\\x[0-9a-f]{2}",
    "Hex-encoded strings (4+ bytes)",
)
_p("obfuscation", "high", r"[\u200b\u200c\u200d\ufeff]{3,}", "Zero-width character obfuscation")
# Unicode/terminal text-safety rules (see skillguard/sanitize.py). These match
# the RAW line and surface the obfuscation TECHNIQUE itself; fold_for_detection()
# additionally lets every rule above see the de-obfuscated payload. They are
# exempt from the frontmatter skip in engines/local.py because a skill's
# name/description is injected into the agent verbatim. Char classes are built
# from explicit code points (not literal invisibles) to keep this source ASCII.
# Detection subsets are intentionally NARROWER than sanitize.STRIP_CHARS:
#   - zero-width: the true zero-advance chars, so even a SINGLE one is flagged,
#     but only where it splits an ASCII token — an emoji ZWJ sits between
#     non-ASCII code points, so it never matches (the documented emoji FP guard);
#   - bidi: the embedding/override/isolate controls (Trojan Source), excluding
#     the benign LRM/RLM marks that legitimately appear in RTL text.
_ZERO_WIDTH = "".join(chr(cp) for cp in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF))
_BIDI_OVERRIDES = "".join(
    chr(cp) for cp in (0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069)
)
_p(
    "obfuscation",
    "high",
    rf"[A-Za-z0-9][{_ZERO_WIDTH}]|[{_ZERO_WIDTH}][A-Za-z0-9]",
    "Invisible character splitting a token",
)
_p(
    "obfuscation",
    "high",
    rf"[{_BIDI_OVERRIDES}]",
    "Bidirectional control character (Trojan Source)",
)
_p("obfuscation", "high", r"\x1b", "Terminal escape sequence in skill source")
_p(
    "obfuscation",
    "high",
    r"String\.fromCharCode\s*\(\s*\d+\s*(,\s*\d+\s*){3,}",
    "String.fromCharCode obfuscation",
)
_p(
    "obfuscation",
    "high",
    r"\\u00[0-9a-f]{2}\\u00[0-9a-f]{2}\\u00[0-9a-f]{2}",
    "Unicode escape obfuscation",
)

# --- Persistence (MEDIUM) ---
_p("persistence", "medium", r"crontab\s+-[el]", "Crontab manipulation")
_p("persistence", "medium", r"LaunchAgents|LaunchDaemons", "macOS launch agent/daemon persistence")
_p("persistence", "medium", r"systemctl\s+(enable|start|restart)", "Systemd service manipulation")
_p("persistence", "medium", r"~/.bashrc|~/.zshrc|~/.profile", "Shell profile modification")

# --- Suspicious network (MEDIUM) ---
_p("network", "medium", r"nc\s+-l", "Netcat listener")
_p("network", "medium", r"nmap\s+", "Port scanning with nmap")
_p("network", "medium", r"tcpdump\s+", "Packet capture")
_p("network", "medium", r"dns\s+exfil|dns\s+tunnel", "DNS exfiltration/tunneling reference")

# --- Dangerous operations (MEDIUM) ---
_p(
    "dangerous_op",
    "medium",
    r"rm\s+-rf\s+/(?!tmp\b|var/lib/apt/lists\b)",
    "Recursive deletion from root",
)
_p("dangerous_op", "medium", r"chmod\s+777\s+", "World-writable permissions")
_p("dangerous_op", "medium", r"dd\s+if=.*of=/dev/", "Disk overwrite with dd")
_p("dangerous_op", "medium", r":(){ :\|:& };:", "Fork bomb")

# --- Container escape (MEDIUM) ---
_p("container_escape", "medium", r"/var/run/docker\.sock", "Docker socket access")
_p("container_escape", "medium", r"nsenter\s+", "Namespace entry (container escape)")
_p("container_escape", "medium", r"LD_PRELOAD", "LD_PRELOAD injection")
_p("container_escape", "medium", r"/proc/self/", "Process self-inspection")

# --- Reconnaissance (LOW) ---
_p("recon", "low", r"^\s*(?:whoami|id\s+-[anu])\b", "User reconnaissance")
_p("recon", "low", r"uname\s+-a", "System reconnaissance")
_p("recon", "low", r"\bifconfig\b|\bip\s+addr\b", "Network interface reconnaissance")
_p("recon", "low", r"hostname\s+-[fI]", "Hostname reconnaissance")
