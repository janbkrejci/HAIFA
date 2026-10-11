"""``factory init``: install factory into a repo.

Writes ``.factory/config.yaml``, the backlog directory and the runtime lines of
``.gitignore``. Agents, workflows, skills and extensions are not copied: a run inherits
them from the library (``aifactory.library.inherit``). Nothing is committed and nothing is
written to the library or ``$HAIFA_HOME``.

A repo whose ``config.yaml`` is committed (HEAD or base) is installed
(``already_installed``); a repo with an sssf installation is refused (``existing_config``).
Existing files are skipped unless ``force`` is set.

``project_settings`` and ``render_config`` are shared with ``library.install_commit``
(``factory init --dry-run`` and ``--commit``), which plans the same files and installs them
into base with one commit.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from aifactory.config.settings import CONFIG_FILE, ProjectSettings
from aifactory.library.store import LibraryStoreError
from aifactory.providers import git

GITIGNORE_LINES = (
    ".factory/data/",
    ".factory/worktrees/",
    ".factory/local.yaml",
    ".factory/trace.db*",
)
SSSF_CONFIG_DIR = "adws/adw_sssf_config"
_READ_ENV = {"GIT_OPTIONAL_LOCKS": "0"}
FileAction = Literal["created", "skipped", "overwritten"]


@dataclass(frozen=True)
class WrittenFile:
    path: str
    action: FileAction

    def to_json(self) -> dict[str, str]:
        return {"path": self.path, "action": self.action}


@dataclass(frozen=True)
class InitResult:
    repo: Path
    base: str
    provider: str
    files: list[WrittenFile]
    gitignore_added: list[str]
    backlog_dir: str
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "repo": str(self.repo),
            "base": self.base,
            "provider": self.provider,
            "backlog_dir": self.backlog_dir,
            "files": [f.to_json() for f in self.files],
            "gitignore": {"path": ".gitignore", "added": self.gitignore_added},
        }


# ── git ───────────────────────────────────────────────────────────────────────


def _git_out(root: Path, *args: str) -> str | None:
    proc = git.run_bytes(root, list(args), env=_READ_ENV)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip() or None


def _repo_root(path: Path) -> Path:
    if not path.is_dir():
        raise LibraryStoreError("not_a_repository", f"{path} is not a git repository")
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise LibraryStoreError("not_a_repository", f"{path} is not a git repository")
    return Path(proc.stdout.strip()).resolve()


def _committed(root: Path, ref: str, rel: str) -> bool:
    if git.rev_parse(root, ref) is None:
        return False
    return git.run_bytes(root, ["cat-file", "-e", f"{ref}:{rel}"], env=_READ_ENV).returncode == 0


def _refuse(root: Path, base: str) -> None:
    refs = ["HEAD"] if base == "HEAD" else ["HEAD", base]
    if any(_committed(root, ref, CONFIG_FILE) for ref in refs):
        raise LibraryStoreError(
            "already_installed", f"{CONFIG_FILE} is committed; factory is installed"
        )
    if (root / SSSF_CONFIG_DIR).is_dir():
        raise LibraryStoreError(
            "existing_config",
            f"the repo has an sssf installation ({SSSF_CONFIG_DIR}/); "
            "HAIFA does not take over sssf",
            data={"found": [SSSF_CONFIG_DIR + "/"]},
        )


# ── content ───────────────────────────────────────────────────────────────────


def _gitignore(root: Path) -> list[str]:
    path = root / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    present = {line.strip() for line in text.splitlines()}
    added = [line for line in GITIGNORE_LINES if line not in present]
    if added:
        if text and not text.endswith("\n"):
            text += "\n"
        path.write_text(
            text + "".join(f"{line}\n" for line in added), encoding="utf-8", newline="\n"
        )
    return added


def project_settings(
    *,
    base: str,
    provider: str,
    azure: Mapping[str, str] | None = None,
    remote: str | None = None,
    docs_root: str | None = None,
) -> ProjectSettings:
    """The settings ``init`` writes; ``invalid_value`` when an option is not allowed."""
    values: dict[str, Any] = {"base": base, "git_provider": provider}
    for key, value in (
        ("remote", remote),
        ("docs_root", docs_root),
        ("azure", dict(azure) if azure is not None else None),
    ):
        if value is not None:
            values[key] = value
    try:
        return ProjectSettings.model_validate(values)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'settings'}: {err['msg']}"
            for err in exc.errors()
        )
        raise LibraryStoreError("invalid_value", f"invalid settings: {problems}") from exc


def render_config(settings: ProjectSettings, *, write_remote: bool = False) -> bytes:
    """``.factory/config.yaml`` as ``init`` writes it."""
    config: dict[str, Any] = {"base": settings.base, "git_provider": settings.git_provider}
    if write_remote:
        config["remote"] = settings.remote
    config["docs_root"] = settings.docs_root
    if settings.azure is not None:
        config["azure"] = settings.azure.model_dump(mode="json")
    body = yaml.safe_dump(config, sort_keys=False, allow_unicode=True, width=4096)
    return ("# factory project settings, written by factory init\n" + body).encode("utf-8")


def init_repo(
    path: Path,
    *,
    base: str | None = None,
    provider: Literal["local", "github", "azure"] = "local",
    azure: Mapping[str, str] | None = None,
    docs_root: str | None = None,
    force: bool = False,
) -> InitResult:
    """Install factory into the git repo at `path`; see the module docstring."""
    root = _repo_root(path)
    if base is None:
        base = _git_out(root, "symbolic-ref", "--quiet", "--short", "HEAD")
        if base is None:
            raise LibraryStoreError("invalid_value", "HEAD is detached; pass --base")
    elif not base.strip():
        raise LibraryStoreError("invalid_value", "--base must not be empty")
    _refuse(root, base)
    settings = project_settings(base=base, provider=provider, azure=azure, docs_root=docs_root)
    files = {
        CONFIG_FILE: render_config(settings),
        f"{settings.backlog_dir.rstrip('/')}/.gitkeep": b"",
    }
    written: list[WrittenFile] = []
    for rel, data in files.items():
        target = root / rel
        if target.exists() and not force:
            written.append(WrittenFile(rel, "skipped"))
            continue
        action: FileAction = "overwritten" if target.exists() else "created"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(WrittenFile(rel, action))
    gitignore_added = _gitignore(root)
    skipped = sum(1 for f in written if f.action == "skipped")
    warnings = [f"{skipped} existing file(s) skipped; use --force to overwrite"] if skipped else []
    return InitResult(
        repo=root,
        base=base,
        provider=provider,
        files=written,
        gitignore_added=gitignore_added,
        backlog_dir=settings.backlog_dir,
        warnings=warnings,
    )
