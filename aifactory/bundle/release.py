"""Stamp a unique CI build version into the wheel before building its bundle."""

from __future__ import annotations

import os
import re
from pathlib import Path

from bundle.build import PROJECT, version


def stamp(run_number: int, repository: str, project: Path = PROJECT) -> str:
    if run_number < 1:
        raise ValueError("CI run number must be positive")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("give the GitHub release repository as owner/name")
    major, minor, _ = version(project).split(".")
    target = f"{major}.{minor}.{run_number}"
    init = project / "src/aifactory/__init__.py"
    init.write_text(
        re.sub(r"^__version__ = .*$", f'__version__ = "{target}"', init.read_text(), flags=re.M),
        encoding="utf-8",
    )
    updates = project / "src/aifactory/web/updates.py"
    updates.write_text(
        re.sub(
            r"^UPDATE_REPOSITORY = .*$",
            f'UPDATE_REPOSITORY = "{repository}"',
            updates.read_text(),
            flags=re.M,
        ),
        encoding="utf-8",
    )
    return target


if __name__ == "__main__":
    print(stamp(int(os.environ["GITHUB_RUN_NUMBER"]), os.environ["GITHUB_REPOSITORY"]))
