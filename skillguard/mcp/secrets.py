#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""The single authority for "what is a secret / how is it redacted".

Every redaction regex, the credential heuristics, and the materialization-safe
renderers live here. Any new redaction or detection rule goes here, not into
``engine.py`` — the engine asks these helpers, it does not re-implement them.
"""

from __future__ import annotations

import re
from typing import Any

from skillguard.mcp.model import McpServer

_ENV_REF = re.compile(r"^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?$")
_SECRET_PREFIX = re.compile(
    r"^(sk-|pk-|ghp_|gho_|ghu_|ghs_|github_pat_|xox[baprs]-|AKIA|ASIA|AIza|ya29\.|glpat-|hf_|r8_)"
)
# `--flag=SECRET` style argument carrying an inline credential.
_INLINE_KV_SECRET = re.compile(
    r"^(--?[A-Za-z0-9_-]*(?:key|token|secret|password|auth)[A-Za-z0-9_-]*=)(.+)$", re.I
)
# A long-form credential flag whose *next* argument is the value, e.g.
# `--token SECRET`. Restricted to unambiguous long flags so we never redact the
# value after a benign short flag like `-p 8080`.
_CRED_FLAG = re.compile(
    r"^--(api[-_]?key|access[-_]?token|auth[-_]?token|client[-_]?secret|api[-_]?secret|"
    r"token|secret|password|passwd|bearer|credential)$",
    re.I,
)
# Credential-bearing URL query parameters, e.g. `?api_key=…&access_token=…`.
_URL_QS_SECRET = re.compile(
    r"([?&])([^=&\s]*(?:key|token|secret|password|auth|sig|access)[^=&\s]*)=([^&\s]+)", re.I
)


def _is_env_ref(value: str) -> bool:
    return bool(_ENV_REF.match(str(value).strip()))


def _has_interpolation(value: str) -> bool:
    return "${" in str(value)


def _is_safe_ref(value: str) -> bool:
    """A value that is an env reference (``$VAR`` / ``${VAR}``) or contains
    interpolation — i.e. NOT a bare literal that could be a plaintext secret.
    Collapses the doubled ``not _is_env_ref(x) and not _has_interpolation(x)``
    guard that was open-coded at every redaction/detection site."""
    return _is_env_ref(value) or _has_interpolation(value)


def redact_value(value: str) -> str:
    """Materialization-safe rendering of an env/header value: keep ``${REF}``
    style references (informative, not secret); replace any literal with a
    marker so a real secret can never reach disk."""
    s = str(value)
    if s == "" or _is_safe_ref(s):
        return s
    return "<redacted-literal>"


def looks_secretish(value: str) -> bool:
    """Heuristic: does this literal look like a credential? Conservative — paths,
    URLs, and sentences are excluded so we don't cry wolf on benign config."""
    s = str(value).strip()
    if not s or _is_safe_ref(s):
        return False
    if "/" in s or "\\" in s or "://" in s or " " in s or s.startswith("-"):
        return False  # paths / URLs / prose / flags — not bare credential tokens
    if _SECRET_PREFIX.match(s):
        return True
    return len(s) >= 20 and bool(re.fullmatch(r"[A-Za-z0-9_\-\.=+]{20,}", s))


def _is_secretish_header(name: str) -> bool:
    n = name.lower()
    return (
        n in ("authorization", "proxy-authorization")
        or "key" in n
        or "token" in n
        or "secret" in n
        or "password" in n
    )


def _header_has_inline_secret(name: str, value: str) -> bool:
    if not _is_secretish_header(name):
        return False
    v = str(value).strip()
    return bool(v) and not _is_safe_ref(v)


def redact_arg(arg: str) -> str:
    """Materialization-safe rendering of one launch argument: hide a bare
    credential token or a ``--flag=SECRET`` literal; keep everything else (args
    are the scan surface, and a non-secret arg like ``curl … | sh`` must stay
    visible to the regex engines)."""
    s = str(arg)
    if looks_secretish(s):
        return "<redacted-literal>"
    m = _INLINE_KV_SECRET.match(s)
    if m and not _is_safe_ref(m.group(2)):
        return m.group(1) + "<redacted-literal>"
    return s


def redact_url_secrets(url: str) -> str:
    """Redact credential-bearing query parameters in a URL, keeping ``${REF}``s."""

    def sub(m: re.Match) -> str:
        val = m.group(3)
        if _is_safe_ref(val):
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}=<redacted-literal>"

    return _URL_QS_SECRET.sub(sub, str(url))


def redacted_args(args: list) -> list[str]:
    """Redact inline credentials across an argument list, including the value
    that *follows* a credential flag (``--token SECRET`` → two args)."""
    out: list[str] = []
    i, n = 0, len(args)
    while i < n:
        a = str(args[i])
        out.append(redact_arg(a))
        if _CRED_FLAG.match(a) and i + 1 < n:
            nxt = str(args[i + 1])
            if nxt and not _is_safe_ref(nxt) and not nxt.startswith("-"):
                out.append("<redacted-literal>")
                i += 2
                continue
        i += 1
    return out


def redacted_launch_line(mcp: McpServer) -> str:
    """The launch command with any inline-credential argument redacted."""
    parts = [mcp.command, *redacted_args(mcp.args)]
    return " ".join(p for p in parts if p != "").strip()


def redacted_config(mcp: McpServer) -> dict:
    """A copy of the raw config with every value that could hold a secret made
    materialization-safe: env/header values, credential-bearing args, and
    credential-bearing URL query params. Non-secret command/args/url text passes
    through — it is the scan surface."""
    out: dict[str, Any] = {}
    for k, v in mcp.raw.items():
        if k == "env" and isinstance(v, dict):
            out["env"] = {ek: redact_value(ev) for ek, ev in v.items()}
        elif k == "headers" and isinstance(v, dict):
            out["headers"] = {hk: redact_value(hv) for hk, hv in v.items()}
        elif k == "args" and isinstance(v, list):
            out["args"] = redacted_args(v)
        elif k == "url" and isinstance(v, str):
            out["url"] = redact_url_secrets(v)
        else:
            out[k] = v
    return out
