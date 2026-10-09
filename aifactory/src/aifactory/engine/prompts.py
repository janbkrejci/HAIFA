"""Prompt rendering: load system/user refs from config, replace {{placeholders}}."""

from __future__ import annotations

from pathlib import Path


def render(template_path: str | Path, variables: dict[str, str]) -> str:
    text = Path(template_path).read_text()
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def save(directory: str | Path, name: str, content: str) -> Path:
    """Save the exact prompt sent, before execution — the audit copy."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


PHASES_DIR = "phases"  # aifactory 2.10: <agent>/prompts/phases/<phase>/ — one copy per phase


def phase_dir(prompts_dir: str | Path, phase_name: str) -> Path:
    """aifactory 2.10: where one phase's prompts live, so a later phase of the same
    agent does not overwrite them."""
    return Path(prompts_dir) / PHASES_DIR / phase_name
