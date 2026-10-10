"""Recognize a legacy sssf installation in a repository; nothing is removed."""

from __future__ import annotations

from pathlib import Path

_SKILLS = (".claude/skills/sssf", ".agents/skills/sssf", ".codex/skills/sssf")


def installation_paths(root: Path) -> list[str]:
    """Recognize sssf directories without interpreting or migrating their configuration."""
    paths = []
    adws = root / "adws"
    if (adws / "adw_sssf_config").exists() or (adws / "adw_modules").exists():
        paths.append("adws")
    paths.extend(rel for rel in _SKILLS if (root / rel).exists() or (root / rel).is_symlink())
    return paths
