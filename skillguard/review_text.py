from __future__ import annotations


def finding_explanation(finding: dict, *, target_kind: str) -> list[str]:
    message = str(finding.get("message") or "").lower()
    category = str(finding.get("category") or "").lower()
    engine = str(finding.get("engine") or "").lower()

    if "webhook.site" in message or category == "data_exfil":
        return [
            "Why: this pattern may send data out to a collection endpoint.",
            "Safest: review the surrounding file. If it is only documentation, mark it false positive.",
        ]
    if "curl piped to shell" in message or category == "shell_pipe":
        return [
            "Why: this downloads code and runs it immediately.",
            "Safest: verify the source and pin/check the installer before allowing it.",
        ]
    if "systemd" in message or category == "persistence":
        return [
            "Why: this can install or enable a background service.",
            "Safest: allow only if this setup behavior is expected for the tool.",
        ]
    if "plaintext credential" in message or (engine == "mcp" and category == "credential"):
        noun = "MCP server" if target_kind == "mcp" else "target"
        return [
            f"Why: this {noun} secret may be written directly in config.",
            "Safest: move the value to an environment variable reference and re-scan.",
        ]
    if "prompt injection" in message or category == "prompt_injection":
        return [
            "Why: this text may try to change the agent's instructions.",
            "Safest: mark false positive only when it is clearly an example in trusted docs.",
        ]
    return [
        "Why: this matched a security pattern and needs human review.",
        "Safest: inspect the file and mark false positive only after you understand the context.",
    ]


def action_help() -> str:
    return (
        "Actions: [m] mark-fp means reviewed benign  "
        "[a] ack means allow despite risk  "
        "[s] show details  [enter] next  [q] quit"
    )
