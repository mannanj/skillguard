from __future__ import annotations

from pathlib import Path

from skillguard import discovery


def _write_skill(root: Path, name: str, body: str = "# Skill\n") -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n{body}")
    return skill


def test_discover_skills_includes_codex_user_repo_and_plugin_locations(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "repo" / "pkg"
    project.mkdir(parents=True)
    (tmp_path / "repo" / ".git").mkdir()

    monkeypatch.setattr(discovery, "GLOBAL_SKILLS_DIR", home / ".claude" / "skills")
    monkeypatch.setattr(discovery, "CODEX_USER_SKILLS_DIR", home / ".agents" / "skills")
    monkeypatch.setattr(discovery, "CODEX_SYSTEM_SKILLS_DIR", tmp_path / "missing-system")
    monkeypatch.setattr(discovery, "CODEX_ADMIN_SKILLS_DIR", tmp_path / "missing-admin")
    monkeypatch.setattr(discovery, "CODEX_PLUGIN_CACHE_DIR", home / ".codex" / "plugins" / "cache")

    _write_skill(home / ".claude" / "skills", "claude-global")
    _write_skill(home / ".agents" / "skills", "codex-user")
    _write_skill(tmp_path / "repo" / ".agents" / "skills", "codex-repo")
    _write_skill(
        home / ".codex" / "plugins" / "cache" / "personal" / "plugin-a" / "1.0.0" / "skills",
        "codex-plugin",
    )

    skills = discovery.discover_skills("all", project)
    by_name = {s.name: s for s in skills}

    assert by_name["claude-global"].scope == "global"
    assert by_name["codex-user"].scope == "global"
    assert by_name["codex-repo"].scope == "local"
    assert by_name["codex-plugin@plugin-a"].scope == "plugin"


def test_discover_skills_dedupes_same_resolved_path_from_claude_and_codex(tmp_path, monkeypatch):
    home = tmp_path / "home"
    codex_skill = _write_skill(home / ".agents" / "skills", "shared")
    claude_link = home / ".claude" / "skills" / "shared"
    claude_link.parent.mkdir(parents=True)
    claude_link.symlink_to(codex_skill)

    monkeypatch.setattr(discovery, "GLOBAL_SKILLS_DIR", home / ".claude" / "skills")
    monkeypatch.setattr(discovery, "CODEX_USER_SKILLS_DIR", home / ".agents" / "skills")
    monkeypatch.setattr(discovery, "CODEX_SYSTEM_SKILLS_DIR", tmp_path / "missing-system")
    monkeypatch.setattr(discovery, "CODEX_ADMIN_SKILLS_DIR", tmp_path / "missing-admin")
    monkeypatch.setattr(discovery, "CODEX_PLUGIN_CACHE_DIR", tmp_path / "missing-cache")

    skills = discovery.discover_skills("global", tmp_path)

    assert [s.name for s in skills] == ["shared"]
