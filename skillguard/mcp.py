#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
# Copyright (C) 2026 Mannan Javid — SkillGuard <https://github.com/mannanj/skillguard>
"""
MCP (Model Context Protocol) server discovery and scanning.

Claude Code loads MCP servers — third-party processes and remote endpoints that
inject tool descriptions and "instructions" straight into the model's context —
from several config files. Those servers are an unaudited supply chain with the
same trust problem as skills, plus a prompt-injection surface skills don't have:
their tool descriptions and server instructions are model-facing text.

This module:
  * **discovers** every configured server (``~/.claude.json`` global + per
    project, ``~/.claude/mcp.json``, and plugin ``.mcp.json`` files);
  * **materializes** each server's scannable surface — a *redacted* config plus
    the launch command / endpoint / env-var NAMES — to inspectable files so the
    existing engines (local regex, Cisco, SkillAudit, Snyk) scan it unchanged;
  * **analyzes** the config structurally for MCP-specific risks (remote/unpinned
    code execution, insecure transport, inline plaintext secrets) via
    ``McpConfigEngine``;
  * optionally **introspects** a server (opt-in — this *launches* it) to pull its
    tool descriptions and instructions and scan them for prompt injection.

Secret discipline: any value that could be a secret — an env value, a header
value, a credential-bearing launch argument, or a credential-bearing URL query
parameter — is read in memory only, to decide whether an inline literal secret
is present. It is NEVER written to a materialized file, a finding message, the
cache, or the history DB. Only NAMES (variable, header, flag, query-param) ever
leave this module.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from skillguard.model import Finding, SkillInfo

# ─── Config locations ────────────────────────────────────────────────────────


def global_config_path() -> Path:
    return Path.home() / ".claude.json"


def secondary_config_path() -> Path:
    return Path.home() / ".claude" / "mcp.json"


def plugins_root() -> Path:
    return Path.home() / ".claude" / "plugins"


# Hosts that are exfiltration sinks, not legitimate MCP endpoints.
SUSPICIOUS_HOSTS = (
    "webhook.site",
    "requestbin.com",
    "requestbin.net",
    "pipedream.net",
    "interact.sh",
    "burpcollaborator.net",
    "ngrok.io",
    "ngrok.com",
    "ngrok.app",
)

# Package runners that fetch and execute third-party code at launch.
_RUNNERS = ("npx", "pnpm", "bunx", "yarn", "uvx", "uv", "pipx", "dlx", "deno")


# ─── Server descriptor ───────────────────────────────────────────────────────


@dataclass
class McpServer:
    """A discovered MCP server config. ``env``/``headers``/``raw`` hold the
    original (possibly secret) values and stay in memory only — see the module
    docstring's secret discipline. Use ``env_names`` / redacted accessors when
    emitting anything that persists."""

    name: str
    source: str  # config file this came from
    scope: str  # global | project | plugin
    transport: str  # stdio | http | sse | unknown
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)  # in-memory only
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)  # in-memory only
    plugin: str | None = None
    raw: dict = field(default_factory=dict)  # in-memory only

    @property
    def env_names(self) -> list[str]:
        return sorted(self.env.keys())

    @property
    def launch_line(self) -> str:
        return " ".join([self.command, *[str(a) for a in self.args]]).strip()

    @property
    def match_tokens(self) -> list[str]:
        """Candidate identifiers Claude Code might use as the ``mcp__<token>__``
        tool-name prefix for this server, for the hook to map calls back here.
        Imperfect by design (Claude's exact sanitization isn't reproduced); the
        hook longest-prefix-matches and defaults to a non-blocking policy."""
        names = {self.name, self.name.replace("-", "_"), self.name.replace("_", "-")}
        if self.plugin:
            for n in list(names):
                names.add(f"plugin_{self.plugin}_{n}")
                names.add(f"plugin_{self.plugin.replace('-', '_')}_{n}")
        return sorted(t for t in names if t)


# ─── Discovery ───────────────────────────────────────────────────────────────


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _server_from_config(
    name: str, cfg: Any, source: Path, scope: str, plugin: str | None = None
) -> McpServer:
    cfg = cfg if isinstance(cfg, dict) else {}
    ttype = str(cfg.get("type") or cfg.get("transport") or "").lower()
    command = str(cfg.get("command") or "")
    url = str(cfg.get("url") or "")

    if ttype == "sse":
        transport = "sse"
    elif ttype in ("http", "streamable-http", "streamablehttp", "https"):
        transport = "http"
    elif ttype == "stdio":
        transport = "stdio"
    elif command:
        transport = "stdio"
    elif url:
        transport = "sse" if "sse" in url.lower() else "http"
    else:
        transport = "unknown"

    args = cfg.get("args") or []
    if not isinstance(args, list):
        args = [str(args)]
    env = cfg.get("env") if isinstance(cfg.get("env"), dict) else {}
    headers = cfg.get("headers") if isinstance(cfg.get("headers"), dict) else {}

    return McpServer(
        name=name,
        source=str(source),
        scope=scope,
        transport=transport,
        command=command,
        args=[str(a) for a in args],
        env=dict(env),
        url=url,
        headers=dict(headers),
        plugin=plugin,
        raw=dict(cfg),
    )


def _servers_from_mapping(
    mapping: Any, source: Path, scope: str, plugin: str | None = None
) -> list[McpServer]:
    if not isinstance(mapping, dict):
        return []
    return [_server_from_config(name, cfg, source, scope, plugin) for name, cfg in mapping.items()]


def discover_mcps(
    scope: str = "all",
    project_dir: Path | None = None,
    single: str | None = None,
    include_plugins: bool = True,
) -> list[McpServer]:
    """Find every MCP server Claude Code would load, deduplicated by (scope,name).

    ``scope`` mirrors the skill scanner: ``global`` (user-level configs),
    ``local``/``project`` (this project's servers), or ``all``.
    """
    project_dir = Path(project_dir) if project_dir else Path.cwd()
    want_global = scope in ("global", "all")
    want_project = scope in ("local", "project", "all")
    servers: list[McpServer] = []

    # 1. ~/.claude.json — top-level (global) + per-project mcpServers
    gc = _read_json(global_config_path())
    if gc is not None:
        if want_global:
            servers += _servers_from_mapping(gc.get("mcpServers"), global_config_path(), "global")
        if want_project:
            raw_projects = gc.get("projects")
            projects = raw_projects if isinstance(raw_projects, dict) else {}
            for key in {str(project_dir), str(project_dir.resolve())}:
                proj = projects.get(key)
                if isinstance(proj, dict):
                    servers += _servers_from_mapping(
                        proj.get("mcpServers"), global_config_path(), "project"
                    )

    # 2. ~/.claude/mcp.json (global)
    if want_global:
        sc = _read_json(secondary_config_path())
        if sc is not None:
            servers += _servers_from_mapping(
                sc.get("mcpServers"), secondary_config_path(), "global"
            )

    # 3. project-local .mcp.json
    if want_project:
        proj_mcp = project_dir / ".mcp.json"
        pj = _read_json(proj_mcp)
        if pj is not None:
            servers += _servers_from_mapping(pj.get("mcpServers"), proj_mcp, "project")

    # 4. plugin-provided servers
    if include_plugins and want_global:
        servers += _discover_plugin_mcps()

    # Deduplicate by (scope, name); later definitions win.
    deduped: dict[tuple[str, str], McpServer] = {}
    for s in servers:
        deduped[(s.scope, s.name)] = s
    result = list(deduped.values())

    if single:
        result = [s for s in result if s.name == single]
    result.sort(key=lambda s: (s.scope, s.name))
    return result


# Directories never worth walking for MCP configs — pruning them keeps
# discovery fast on real plugin trees (which can contain huge node_modules).
_PRUNE_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".cache",
    ".next",
    "target",
}


def _discover_plugin_mcps(root: Path | None = None, cap: int = 4000) -> list[McpServer]:
    """Find plugin-declared MCP servers in ``.mcp.json`` / ``plugin.json`` files.

    Uses a pruned, bounded walk (not ``rglob``) so a plugin tree with vendored
    dependencies can't make discovery crawl. ``cap`` bounds files inspected.
    """
    root = root or plugins_root()
    if not root.is_dir():
        return []
    servers: list[McpServer] = []
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS]
        for fn in filenames:
            if fn != "plugin.json" and not fn.endswith(".mcp.json"):
                continue
            if seen >= cap:
                return servers
            seen += 1
            cfg_path = Path(dirpath) / fn
            data = _read_json(cfg_path)
            if data is None:
                continue
            if fn == "plugin.json":
                mapping = data.get("mcpServers")
            else:
                mapping = data.get("mcpServers", data)
            if not isinstance(mapping, dict):
                continue
            plugin = _plugin_name_for(cfg_path, root)
            servers += _servers_from_mapping(mapping, cfg_path, "plugin", plugin)
    return servers


def _plugin_name_for(cfg_path: Path, root: Path) -> str:
    """Best-effort plugin identifier from a config path under the plugins root."""
    try:
        rel = cfg_path.resolve().relative_to(root.resolve())
        parts = rel.parts
        # e.g. cache/<plugin>/.mcp.json  or  marketplaces/<mp>/<plugin>/.mcp.json
        if len(parts) >= 2:
            return parts[-2]
        return parts[0]
    except (ValueError, OSError):
        return cfg_path.parent.name


# ─── Redaction & secret detection ────────────────────────────────────────────

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


def redact_value(value: str) -> str:
    """Materialization-safe rendering of an env/header value: keep ``${REF}``
    style references (informative, not secret); replace any literal with a
    marker so a real secret can never reach disk."""
    s = str(value)
    if s == "" or _is_env_ref(s) or _has_interpolation(s):
        return s
    return "<redacted-literal>"


def looks_secretish(value: str) -> bool:
    """Heuristic: does this literal look like a credential? Conservative — paths,
    URLs, and sentences are excluded so we don't cry wolf on benign config."""
    s = str(value).strip()
    if not s or _is_env_ref(s) or _has_interpolation(s):
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
    return bool(v) and not _is_env_ref(v) and not _has_interpolation(v)


def redact_arg(arg: str) -> str:
    """Materialization-safe rendering of one launch argument: hide a bare
    credential token or a ``--flag=SECRET`` literal; keep everything else (args
    are the scan surface, and a non-secret arg like ``curl … | sh`` must stay
    visible to the regex engines)."""
    s = str(arg)
    if looks_secretish(s):
        return "<redacted-literal>"
    m = _INLINE_KV_SECRET.match(s)
    if m and not _is_env_ref(m.group(2)) and not _has_interpolation(m.group(2)):
        return m.group(1) + "<redacted-literal>"
    return s


def redact_url_secrets(url: str) -> str:
    """Redact credential-bearing query parameters in a URL, keeping ``${REF}``s."""

    def sub(m: re.Match) -> str:
        val = m.group(3)
        if _is_env_ref(val) or _has_interpolation(val):
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
            if (
                nxt
                and not _is_env_ref(nxt)
                and not _has_interpolation(nxt)
                and not nxt.startswith("-")
            ):
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


# ─── Materialization ─────────────────────────────────────────────────────────


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or "_unnamed"


def materialize_surface(mcp: McpServer, base_dir: Path) -> SkillInfo:
    """Write the server's redacted, scannable surface under
    ``base_dir/<safe-name>/surface/`` and return a SkillInfo (kind="mcp") the
    engine pipeline can scan like any skill. Inspectable after the fact: the
    files are exactly what was scanned."""
    sdir = base_dir / safe_name(mcp.name)
    surface = sdir / "surface"
    surface.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []

    cfg_file = surface / "mcp-config.json"
    cfg_file.write_text(json.dumps(redacted_config(mcp), indent=2, sort_keys=True))
    files.append(cfg_file)

    if mcp.transport == "stdio" and mcp.launch_line:
        cmd_file = surface / "command.txt"
        cmd_file.write_text(redacted_launch_line(mcp) + "\n")
        files.append(cmd_file)

    if mcp.url:
        ep = surface / "endpoint.txt"
        header_names = "\n".join(f"header: {h}" for h in sorted(mcp.headers))
        ep.write_text(f"{redact_url_secrets(mcp.url)}\n{header_names}\n")
        files.append(ep)

    if mcp.env_names:
        env_file = surface / "env.txt"
        env_file.write_text("\n".join(mcp.env_names) + "\n")
        files.append(env_file)

    source_mtime = 0.0
    try:
        source_mtime = os.path.getmtime(mcp.source)
    except OSError:
        pass

    return SkillInfo(
        name=mcp.name,
        path=surface,
        scope=mcp.scope,
        files=files,
        kind="mcp",
        mtime_override=source_mtime,
        extra={"mcp": mcp},
    )


# ─── Structural analysis (the "mcp" engine) ──────────────────────────────────


def analyze_mcp_config(mcp: McpServer) -> list[Finding]:
    """MCP-specific structural findings the text engines can't see: supply-chain
    execution, insecure transport, and inline plaintext secrets. Severities are
    calibrated so routine ``npx``/``uvx`` servers don't drown real red flags —
    third-party runtimes are ``low``/``info`` awareness; ``curl|sh``, inline
    ``eval``, exfil endpoints, and plaintext secrets are ``high``/``critical``."""
    out: list[Finding] = []
    cfg_ref = "mcp-config.json"

    def add(sev: str, cat: str, msg: str, file: str = cfg_ref) -> None:
        out.append(Finding(engine="mcp", severity=sev, category=cat, message=msg, file=file))

    launch = mcp.launch_line
    low = launch.lower()

    # --- Endpoint / transport (http, sse) ---
    if mcp.url:
        parsed = urlparse(mcp.url if "://" in mcp.url else f"//{mcp.url}")
        host = (parsed.hostname or "").lower()
        if any(
            host == h or host.endswith("." + h) or h in mcp.url.lower() for h in SUSPICIOUS_HOSTS
        ):
            add(
                "critical",
                "mcp_suspicious_endpoint",
                f"MCP endpoint points at a known exfiltration host: {host or mcp.url}",
                "endpoint.txt",
            )
        if parsed.scheme == "http":
            add(
                "medium",
                "mcp_insecure_transport",
                f"MCP endpoint uses unencrypted http:// ({host}); traffic and any "
                f"auth header are sent in clear text.",
                "endpoint.txt",
            )
        if host and re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
            add(
                "low",
                "mcp_raw_ip_endpoint",
                f"MCP endpoint is a raw IP address ({host}), not a named host.",
                "endpoint.txt",
            )

    # --- stdio launch command ---
    if launch:
        if re.search(r"\b(curl|wget)\b[^\n|]*\|\s*(ba)?sh", low):
            add(
                "high",
                "mcp_remote_exec",
                "MCP launch command pipes a network download straight into a shell.",
                "command.txt",
            )
        if re.search(r"\b(node|deno|bun)\b[^\n]*\s-e\b", low) or re.search(
            r"\bpython[23]?\b[^\n]*\s-c\b", low
        ):
            add(
                "high",
                "mcp_inline_exec",
                "MCP launches inline code via an -e/-c flag; the code runs at every start.",
                "command.txt",
            )
        if re.search(r"base64\s+(--?d(ecode)?)\b", low):
            add(
                "high",
                "mcp_obfuscated_launch",
                "MCP launch command base64-decodes content before running it.",
                "command.txt",
            )

        runner = _runner_in(low)
        if runner:
            git_src = re.search(r"(git\+https?://\S+|github:\S+|--from\s+git\+\S+)", launch, re.I)
            if git_src:
                add(
                    "medium",
                    "mcp_remote_code_source",
                    f"MCP runs code fetched from a git source via {runner}; the upstream "
                    f"repo can change what executes at any time.",
                    "command.txt",
                )
            else:
                pkg, ver = _runner_package(launch, runner)
                if pkg and (ver is None or ver == "latest"):
                    add(
                        "low",
                        "mcp_unpinned_dependency",
                        f"MCP runs third-party package '{pkg}' unpinned (@{ver or 'none'}) via "
                        f"{runner}; a compromised or typosquatted upstream would execute at launch. "
                        f"Pin an exact version.",
                        "command.txt",
                    )
                elif pkg:
                    add(
                        "info",
                        "mcp_third_party_runtime",
                        f"MCP runs third-party package '{pkg}@{ver}' via {runner} (pinned).",
                        "command.txt",
                    )
        if re.search(r"\bdocker\s+run\b", low):
            image = _docker_image(launch)
            add(
                "low",
                "mcp_container_runtime",
                f"MCP runs a container image{f' ({image})' if image else ''}; it pulls and "
                f"executes whatever that tag resolves to.",
                "command.txt",
            )

    # --- Inline plaintext secrets (NEVER echo the value) ---
    for ename, evalue in mcp.env.items():
        if looks_secretish(evalue):
            add(
                "high",
                "mcp_inline_secret",
                f"Env var '{ename}' has an inline literal value in the MCP config (looks like a "
                f"plaintext credential). Reference the environment with ${{{ename}}} instead.",
            )
    for hname, hvalue in mcp.headers.items():
        if _header_has_inline_secret(hname, hvalue):
            add(
                "high",
                "mcp_inline_secret",
                f"Header '{hname}' carries an inline literal credential in the MCP config. "
                f"Reference an env var (e.g. ${{TOKEN}}) instead of hard-coding it.",
                "endpoint.txt",
            )
    i = 0
    while i < len(mcp.args):
        s = str(mcp.args[i])
        kv = _INLINE_KV_SECRET.match(s)
        if looks_secretish(s):
            add(
                "high",
                "mcp_inline_secret",
                f"Launch argument #{i} looks like a plaintext credential. Pass it via an "
                f"environment variable reference instead of hard-coding it.",
                "command.txt",
            )
        elif kv and not _is_env_ref(kv.group(2)) and not _has_interpolation(kv.group(2)):
            add(
                "high",
                "mcp_inline_secret",
                f"Launch flag '{kv.group(1).rstrip('=')}' carries an inline literal credential. "
                f"Reference an env var instead.",
                "command.txt",
            )
        elif _CRED_FLAG.match(s) and i + 1 < len(mcp.args):
            nxt = str(mcp.args[i + 1])
            if (
                nxt
                and not _is_env_ref(nxt)
                and not _has_interpolation(nxt)
                and not nxt.startswith("-")
            ):
                add(
                    "high",
                    "mcp_inline_secret",
                    f"Launch flag '{s}' is followed by an inline literal credential. "
                    f"Reference an env var instead.",
                    "command.txt",
                )
                i += 2
                continue
        i += 1
    if mcp.url:
        for m in _URL_QS_SECRET.finditer(mcp.url):
            if not _is_env_ref(m.group(3)) and not _has_interpolation(m.group(3)):
                add(
                    "high",
                    "mcp_inline_secret",
                    f"MCP endpoint URL carries an inline credential in query parameter "
                    f"'{m.group(2)}'. Reference an env var instead.",
                    "endpoint.txt",
                )
                break

    # --- Informational: what this server can read ---
    if mcp.env_names:
        add(
            "info",
            "mcp_env_exposure",
            f"This MCP server is granted {len(mcp.env_names)} environment secret(s): "
            f"{', '.join(mcp.env_names)}. It can read these at runtime.",
        )

    if mcp.transport == "unknown" and not launch and not mcp.url:
        add(
            "info",
            "mcp_unparsed",
            "MCP server config has neither a command nor a url; nothing to scan statically.",
        )

    return out


def _runner_in(low_launch: str) -> str | None:
    toks = low_launch.split()
    for i, t in enumerate(toks):
        base = os.path.basename(t)
        if base in _RUNNERS:
            # `uv tool run` / `uv run` / `pnpm dlx` / `yarn dlx` count as runners
            if base in ("uv", "pnpm", "yarn", "deno"):
                nxt = toks[i + 1] if i + 1 < len(toks) else ""
                if base == "uv" and nxt in ("tool", "run"):
                    return "uv"
                if base in ("pnpm", "yarn") and nxt == "dlx":
                    return base
                if base == "deno" and nxt in ("run",):
                    return "deno"
                continue
            return base
    return None


def _runner_package(launch: str, runner: str) -> tuple[str | None, str | None]:
    """Extract (package, version) from a runner invocation. Skips flags and the
    runner subcommand. Returns version None when unpinned."""
    toks = launch.split()
    # advance past the runner token and known sub-tokens / flags
    i = 0
    while i < len(toks) and os.path.basename(toks[i]).lower() != runner:
        i += 1
    i += 1
    skip_words = {"dlx", "run", "tool", "--from", "exec"}
    pkg = None
    while i < len(toks):
        t = toks[i]
        if t in skip_words:
            i += 1
            # --from takes the package as its argument
            continue
        if t.startswith("-"):
            i += 1
            continue
        pkg = t
        break
    if not pkg:
        return None, None
    # strip scoped-package leading @, then split version
    if pkg.startswith("@"):
        at = pkg.find("@", 1)
        if at == -1:
            return pkg, None
        return pkg[:at], pkg[at + 1 :]
    if "@" in pkg:
        name, ver = pkg.rsplit("@", 1)
        return name, ver
    return pkg, None


def _docker_image(launch: str) -> str:
    toks = launch.split()
    for i, t in enumerate(toks):
        if t == "run":
            for cand in toks[i + 1 :]:
                if cand.startswith("-"):
                    continue
                if cand in ("-e", "--env", "-v", "--volume", "-i", "--rm", "-t"):
                    continue
                return cand
    return ""


class McpConfigEngine:
    """Engine-interface wrapper around ``analyze_mcp_config`` so structural MCP
    findings flow through the same pipeline, caching, and triage as every other
    engine. Returns nothing for skill targets, so it is harmless if always on."""

    name = "mcp"
    available = True

    def scan(self, target: SkillInfo) -> list[Finding]:
        mcp = target.extra.get("mcp") if getattr(target, "extra", None) else None
        if getattr(target, "kind", "skill") != "mcp" or mcp is None:
            return []
        return analyze_mcp_config(mcp)


# ─── Opt-in live introspection (executes the server) ─────────────────────────


def introspect(mcp: McpServer, timeout: float = 20.0) -> dict:
    """Launch/connect to the server and pull its model-facing text (server
    ``instructions`` + every tool's name/description/param descriptions).

    WARNING: for stdio servers this EXECUTES the server. Callers gate it behind
    an explicit opt-in. Always returns a dict; failures populate ``error`` and
    leave ``instructions``/``tools`` empty so scanning degrades to static.
    """
    try:
        if mcp.transport == "stdio" and mcp.command:
            return _introspect_stdio(mcp, timeout)
        if mcp.transport in ("http", "sse") and mcp.url:
            return _introspect_http(mcp, timeout)
        return {
            "ok": False,
            "instructions": "",
            "tools": [],
            "error": f"no introspection for transport {mcp.transport!r}",
        }
    except Exception as e:  # never let introspection crash a scan
        return {"ok": False, "instructions": "", "tools": [], "error": str(e)}


def _jsonrpc(method: str, _id: int | None = None, **params: Any) -> str:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if _id is not None:
        msg["id"] = _id
    if params:
        msg["params"] = params
    return json.dumps(msg)


_INIT_PARAMS = {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "skillguard", "version": "scan"},
}


def _introspect_stdio(mcp: McpServer, timeout: float) -> dict:
    requests = (
        "\n".join(
            [
                _jsonrpc("initialize", 1, **_INIT_PARAMS),
                _jsonrpc("notifications/initialized"),
                _jsonrpc("tools/list", 2),
            ]
        )
        + "\n"
    )

    proc = subprocess.Popen(
        [mcp.command, *mcp.args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, **{k: str(v) for k, v in mcp.env.items()}},
    )
    try:
        out, _err = proc.communicate(input=requests, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            out, _err = proc.communicate(timeout=5)
        except Exception:
            out = ""
    return _parse_introspection(out)


def _introspect_http(mcp: McpServer, timeout: float) -> dict:
    import urllib.request

    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    # Pass through configured headers, resolving ${ENV} references locally.
    for hk, hv in mcp.headers.items():
        headers[hk] = _resolve_env_refs(hv)
    body = (_jsonrpc("initialize", 1, **_INIT_PARAMS) + "\n").encode()
    req = urllib.request.Request(mcp.url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    # Best-effort: many remote servers require OAuth and will 401 before this.
    return _parse_introspection(raw)


def _resolve_env_refs(value: str) -> str:
    def sub(m: re.Match) -> str:
        return os.environ.get(m.group(1) or m.group(2) or "", m.group(0))

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", sub, str(value))


def _parse_introspection(stream: str) -> dict:
    """Pull initialize.instructions + tools/list from newline- or SSE-framed
    JSON-RPC output."""
    instructions, tools, ok = "", [], False
    for line in stream.splitlines():
        line = line.strip()
        if line.startswith("data:"):  # SSE framing
            line = line[5:].strip()
        if not line or not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        result = msg.get("result")
        if not isinstance(result, dict):
            continue
        if "serverInfo" in result or "instructions" in result or "protocolVersion" in result:
            ok = True
            if isinstance(result.get("instructions"), str):
                instructions = result["instructions"]
        if isinstance(result.get("tools"), list):
            ok = True
            for t in result["tools"]:
                if not isinstance(t, dict):
                    continue
                params = []
                schema = t.get("inputSchema") or {}
                props = schema.get("properties") if isinstance(schema, dict) else None
                if isinstance(props, dict):
                    for pname, pdef in props.items():
                        desc = pdef.get("description", "") if isinstance(pdef, dict) else ""
                        params.append({"name": pname, "description": desc})
                tools.append(
                    {
                        "name": t.get("name", ""),
                        "description": t.get("description", ""),
                        "params": params,
                    }
                )
    return {
        "ok": ok,
        "instructions": instructions,
        "tools": tools,
        "error": "" if ok else "no MCP response parsed",
    }


def write_introspection_surface(target: SkillInfo, intro: dict) -> list[Path]:
    """Materialize introspected model-facing text next to the static surface and
    register it on the target so the content engines scan it. Returns new files."""
    surface = target.path
    new_files: list[Path] = []

    if intro.get("instructions"):
        f = surface / "server-instructions.md"
        f.write_text(intro["instructions"])
        new_files.append(f)

    tools = intro.get("tools") or []
    if tools:
        lines = ["# MCP tool descriptions (model-facing surface)\n"]
        for t in tools:
            lines.append(f"## {t.get('name', '')}\n")
            lines.append((t.get("description") or "") + "\n")
            for p in t.get("params", []):
                lines.append(f"- param `{p.get('name', '')}`: {p.get('description', '')}")
            lines.append("")
        f = surface / "tools.md"
        f.write_text("\n".join(lines))
        new_files.append(f)

    target.files.extend(new_files)
    return new_files
