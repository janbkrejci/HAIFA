"""A minimal git repo for the dashboard tests."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git_repo(path: Path) -> Path:
    """Initialise an empty git repository at ``path`` and return its resolved root."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path.resolve()
