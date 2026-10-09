"""Remove an explicitly acknowledged legacy installation when adding a repository."""

from __future__ import annotations

import shutil
import tempfile
import threading
from pathlib import Path

from aifactory.run.gitops import git
from aifactory.web.registry import RepoError

_lock = threading.Lock()
_SKILLS = (".claude/skills/sssf", ".agents/skills/sssf", ".codex/skills/sssf")


def installation_paths(root: Path) -> list[str]:
    """Recognize sssf directories without interpreting or migrating their configuration."""
    paths = []
    adws = root / "adws"
    if (adws / "adw_sssf_config").exists() or (adws / "adw_modules").exists():
        paths.append("adws")
    paths.extend(rel for rel in _SKILLS if (root / rel).exists() or (root / rel).is_symlink())
    return paths


def remove_installation(root: Path) -> str | None:
    """Keep a backup until the deletion commit succeeds; never commit unrelated edits."""
    with _lock:
        paths = installation_paths(root)
        if not paths:
            return None
        try:
            if any(not (root / rel).parent.resolve().is_relative_to(root) for rel in paths):
                raise RepoError("sssf_cleanup_failed", "Instalace sssf vede mimo repozitář.")
            if git(root, "diff", "--cached", "--name-only"):
                raise RepoError(
                    "sssf_cleanup_failed",
                    "Nejdřív commitni nebo odstageuj připravené změny v repozitáři.",
                )
            if git(root, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD":
                raise RepoError("sssf_cleanup_failed", "Repozitář musí být na větvi.")
            tracked = [rel for rel in paths if git(root, "ls-files", "--", rel)]
            with tempfile.TemporaryDirectory(prefix="haifa-sssf-") as directory:
                backup = Path(directory)
                moved: list[str] = []
                try:
                    for rel in paths:
                        destination = backup / rel
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(root / rel), destination)
                        moved.append(rel)
                    if tracked:
                        git(root, "add", "-u", "--", *tracked)
                    args: tuple[str, ...]
                    if not git(root, "diff", "--cached", "--name-only"):
                        # An entirely untracked installation still gets a cleanup record.
                        args = ("--allow-empty", "--only")
                    else:
                        args = ("--only", "--", *tracked)
                    git(
                        root,
                        "commit",
                        "-m",
                        "Remove legacy sssf installation before adding HAIFA",
                        *args,
                    )
                    return git(root, "rev-parse", "HEAD")
                except (OSError, RuntimeError):
                    for rel in reversed(moved):
                        (root / rel).parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(backup / rel), root / rel)
                    if tracked:
                        git(root, "reset", "-q", "HEAD", "--", *tracked)
                    raise
        except (OSError, RuntimeError) as exc:
            raise RepoError("sssf_cleanup_failed", f"Odstranění sssf se nezdařilo: {exc}") from exc
