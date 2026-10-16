"""``factory try``: create the sample repository and register it in the dashboard.

The sample (``demo/repo/`` in the package) is a small standard-library Python library with
tests and a backlog of three tasks of growing size. ``create_demo`` copies it into a new
folder (default ``$HAIFA_HOME/demo``), runs ``git init`` with base ``main``, writes
``.factory/config.yaml`` with ``git_provider: local`` (no GitHub, no ``gh``) and the
``.gitignore`` lines factory needs, commits it all in one commit and registers the repository
in the dashboard registry.

A folder that exists and is not empty is left as it is: nothing is written, the path is
returned (``created`` false) and a git repository there is registered.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aifactory.config.settings import CONFIG_FILE
from aifactory.library.install import GITIGNORE_LINES, project_settings, render_config
from aifactory.library.store import LibraryStoreError
from aifactory.providers import git

TEMPLATE_DIR = Path(__file__).resolve().parent / "repo"
DEMO_DIR = "demo"
BASE = "main"
COMMIT_MESSAGE = "HAIFA sample repository"
_SKIP = frozenset({"__pycache__", ".DS_Store"})
_GITIGNORE = ("__pycache__/", "*.pyc", *GITIGNORE_LINES)


@dataclass(frozen=True)
class DemoResult:
    path: Path
    created: bool
    registered: bool
    repo_id: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "created": self.created,
            "registered": self.registered,
            "repo_id": self.repo_id,
            "base": BASE,
            "provider": "local",
        }


def default_dir(home: Path | None = None) -> Path:
    """Where ``factory try`` creates the sample without a folder argument."""
    from aifactory.home import haifa_home

    return (home if home is not None else haifa_home()) / DEMO_DIR


def _copy_template(target: Path) -> None:
    for source in sorted(TEMPLATE_DIR.rglob("*")):
        rel = source.relative_to(TEMPLATE_DIR)
        if any(part in _SKIP for part in rel.parts) or source.suffix == ".pyc":
            continue
        dest = target / rel
        if source.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)


def _identity_missing(root: Path) -> bool:
    return not all(git.git_ok(root, "config", key) for key in ("user.name", "user.email"))


def _write_repo(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if _identity_missing(target):
        raise LibraryStoreError(
            "git_identity_missing",
            "git has no user.name or user.email; set them with git config --global "
            "user.name/user.email and run factory try again",
        )
    _copy_template(target)
    settings = project_settings(base=BASE, provider="local")
    config = target / CONFIG_FILE
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_bytes(render_config(settings))
    (target / ".gitignore").write_text(
        "".join(f"{line}\n" for line in _GITIGNORE), encoding="utf-8", newline="\n"
    )
    git.git(target, "init", "--quiet")
    git.git(target, "symbolic-ref", "HEAD", f"refs/heads/{BASE}")
    git.git(target, "add", "--all")
    git.git(target, "commit", "--quiet", "--no-verify", "-m", COMMIT_MESSAGE)


def _undo(target: Path, existed: bool) -> None:
    """Remove what a failed ``_write_repo`` left, so ``factory try`` can run again."""
    if not existed:
        shutil.rmtree(target, ignore_errors=True)
        return
    for child in target.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def _register(path: Path, home: Path | None) -> tuple[str | None, list[str]]:
    from aifactory.home import haifa_home
    from aifactory.web.backlog import UsageError
    from aifactory.web.registry import Registry, RepoError
    from aifactory.web.repos import register_repo

    registry = Registry(home if home is not None else haifa_home())
    try:
        entry, _created, warnings = register_repo(registry, str(path))
    except RepoError as exc:
        return None, [f"not registered in the dashboard: {exc.code}: {exc.message}"]
    except UsageError as exc:
        return None, [f"not registered in the dashboard: {exc.message}"]
    return entry.id, list(warnings)


def create_demo(directory: Path | None = None, *, home: Path | None = None) -> DemoResult:
    """Create the sample repository in ``directory``; see the module docstring."""
    target = (directory if directory is not None else default_dir(home)).expanduser().absolute()
    if target.exists() and not target.is_dir():
        raise LibraryStoreError("invalid_value", f"{target} exists and is not a folder")
    created = not target.exists() or not any(target.iterdir())
    if created:
        existed = target.exists()
        try:
            _write_repo(target)
        except (LibraryStoreError, RuntimeError, OSError) as exc:
            _undo(target, existed)
            if isinstance(exc, LibraryStoreError):
                raise
            raise LibraryStoreError("commit_failed", str(exc)) from exc
    elif not (target / ".git").exists():
        return DemoResult(
            target,
            created=False,
            registered=False,
            warnings=[f"{target} exists and is not a git repository; nothing was changed"],
        )
    repo_id, warnings = _register(target, home)
    return DemoResult(
        target, created=created, registered=repo_id is not None, repo_id=repo_id, warnings=warnings
    )
