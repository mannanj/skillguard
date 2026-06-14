# Plan 008: Harden MCP introspection (env minimization, SSRF guard, process lifecycle)

> **Executor instructions**: Step by step; verify each; honor STOP conditions;
> update `plans/README.md`. **Drift check first**:
> `git diff --stat c6e9d42..HEAD -- skillguard/mcp.py` (or `skillguard/mcp/` if
> plan 007 already split it). Re-read the introspection code before editing.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (changing the child env may break servers that read inherited
  vars; gated behind opt-in `--mcp-introspect`)
- **Depends on**: 001 (007 optional but makes this cleaner)
- **Category**: security
- **Planned at**: commit `c6e9d42`, 2026-06-13

## Why this matters

`--mcp-introspect` is the deepest scan mode and the one place SkillGuard
**executes untrusted code** — the servers a user most wants to vet are exactly
the ones they trust least. Three hardening gaps, all verified:

1. **Full parent environment inherited** (`mcp.py:716-720`): the server is
   launched with `env={**os.environ, **mcp.env}`, so an untrusted server sees
   every API key/token in the operator's shell — broader exposure than the server
   gets under Claude Code's own launch.
2. **No SSRF guard on HTTP introspection** (`mcp.py:732-744`): `_introspect_http`
   POSTs to any configured `mcp.url` with no host validation (no block on
   loopback/RFC1918/link-local/`169.254.169.254`), and resolves `${ENV}` secrets
   into the headers it sends there.
3. **Child not reliably reaped** (`mcp.py:709-729`): on the happy path there's no
   `proc.wait()`/`finally`; on timeout the recovery `communicate` is wrapped in a
   bare `except Exception: out = ""`, so a server that resists termination can be
   left orphaned. No `start_new_session`, so forked grandchildren survive.

These are hardening items on a defensible opt-in path, not "the tool is broken" —
but env-minimization and a connect-time host check are nearly free and remove the
worst of the blast radius.

## Current state

- `mcp.py:674` — `introspect()` has a ~20s timeout, dispatches stdio/http.
- `mcp.py:709-729` `_introspect_stdio` — `subprocess.Popen([mcp.command,
  *mcp.args], env={**os.environ, **mcp.env}, stdin/stdout=PIPE, ...)`;
  `communicate(input=..., timeout=...)`; on `TimeoutExpired`: `proc.kill()` then a
  second `communicate(timeout=5)` inside `except Exception: out = ""`. No
  `finally`. Command passed as a **list** (no `shell=True`) — launching the
  configured command is by-design; do NOT treat that as the bug.
- `mcp.py:732-744` `_introspect_http` — `urllib.request.urlopen(req,
  timeout=...)` to `mcp.url`; `_resolve_env_refs` (mcp.py:747-750) expands `${ENV}`
  in headers beforehand.
- `mcp.py:60-67` — `SUSPICIOUS_HOSTS` constant already exists (used by the static
  analyzer as a *finding*; reuse it as a hard block here).
- `cli.py:1285-1297` — the opt-in gate + printed warning.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install | `pip install -e ".[dev]"` | exit 0 |
| Introspect tests | `python -m pytest tests/test_mcp_introspect.py -v` | all pass |
| Full suite | `python -m pytest -q` | all pass |

## Scope

**In scope**: `mcp.py` (or `mcp/introspect.py` post-007); a new `--allow-local`
escape-hatch flag in `cli.py` for the SSRF guard; docs note that introspection is
unsandboxed; tests. **Out of scope**: OS-level sandboxing (bubblewrap/
sandbox-exec) — that's a larger follow-up; note it, don't build it here.

## Steps

### Step 1: Minimize the child environment

Launch with a minimal env: `PATH`, `HOME` (and `SystemRoot` on Windows if
relevant) plus only the server's **declared** `mcp.env` — not all of
`os.environ`. Document the choice in the function docstring.

**Verify**: `test_mcp_introspect.py` green; add a test asserting a non-declared
secret in the parent env does NOT appear in the child's environment (spawn a tiny
fake server that echoes `os.environ`).

### Step 2: Reliable process lifecycle

Wrap the Popen in `try/finally`; in `finally` do `if proc.poll() is None:
proc.kill()` then `proc.wait(timeout=...)`. Launch with `start_new_session=True`
so the child gets its own process group; on cleanup, kill the group
(`os.killpg`) so forked grandchildren can't orphan. Narrow the timeout-recovery
`except Exception` to `subprocess.TimeoutExpired` and record other errors instead
of swallowing them silently.

**Verify**: add a "server that doesn't exit" fixture; assert `introspect`
returns within the timeout AND no child remains (poll the pid/group).

### Step 3: SSRF guard on HTTP introspection

Before `_introspect_http` connects, resolve the host and **refuse**
loopback/RFC1918/link-local/`169.254.169.254` (and anything in `SUSPICIOUS_HOSTS`)
unless a new `--allow-local` flag is set. Return the standard
`{"ok": False, "error": "..."}` shape on refusal.

**Verify**: add tests — an internal-IP URL is refused by default and allowed with
`--allow-local`; a normal public host still connects (mock `urlopen`).

## Done criteria

- [ ] `python -m pytest -q` all pass; new env-isolation, lifecycle, and SSRF
      tests pass.
- [ ] `grep -n "env={\*\*os.environ" skillguard/` (or `skillguard/mcp/`) returns
      nothing — the full-env inheritance is gone.
- [ ] `_introspect_http` refuses internal addresses unless `--allow-local`.
- [ ] `plans/README.md` row for 008 updated.

## STOP conditions

- Minimizing the env breaks a legitimate introspection test that relies on an
  inherited var — decide the minimal var set with the maintainer; don't silently
  re-add `**os.environ`.
- The process-group kill behaves differently on macOS vs Linux CI — gate
  `os.killpg`/`start_new_session` on `os.name == "posix"` and report.

## Maintenance notes

- True sandboxing (container/VM/seccomp) is the real fix for executing untrusted
  servers; this plan reduces blast radius but does not sandbox. Track that as a
  separate roadmap item and keep the printed warning honest.
- If plan 007 landed, all of this is confined to `mcp/introspect.py` — keep it so.
