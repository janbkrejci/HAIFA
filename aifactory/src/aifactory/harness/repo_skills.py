"""The repo's skills mirror: ``.agents/skills/`` as an exact copy of ``.claude/skills/``.

A skill of the repo has its source in ``.claude/skills/<name>/`` (claude reads it)
and a copy in ``.agents/skills/<name>/`` (codex and pi read it). There are no
symlinks. ``factory skills sync`` writes the copy in the working tree and
``factory check`` compares both trees in the base commit, because runs see the
base. The unit is a top-level entry under ``skills/``: a skill directory, or a
top-level file standing for itself.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from aifactory.config.source import git_try

SOURCE = ".claude/skills"
MIRROR = ".agents/skills"


@dataclass(frozen=True)
class SkillsDiff:
    """Skill names that differ between the source and the mirror, sorted."""

    missing: tuple[str, ...]  # in SOURCE, not in MIRROR
    changed: tuple[str, ...]  # in both, different files, bytes or exec bit
    extra: tuple[str, ...]  # in MIRROR only

    @property
    def clean(self) -> bool:
        return not (self.missing or self.changed or self.extra)


@dataclass(frozen=True)
class SyncResult:
    """What ``sync`` did, by skill name."""

    added: tuple[str, ...]
    updated: tuple[str, ...]
    removed: tuple[str, ...]


def group_by_skill(files: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """``{"<skill>/<rel>": key}`` -> ``{"<skill>": {"<rel>": key}}``.

    A top-level file is its own entry with ``rel`` "".
    """
    grouped: dict[str, dict[str, str]] = {}
    for path, key in files.items():
        name, _, rel = path.partition("/")
        grouped.setdefault(name, {})[rel] = key
    return grouped


def diff_snapshots(source: Mapping[str, str], mirror: Mapping[str, str]) -> SkillsDiff:
    """Compare two snapshots ``{path relative to the skills dir: key}``."""
    src = group_by_skill(source)
    dst = group_by_skill(mirror)
    return SkillsDiff(
        missing=tuple(sorted(set(src) - set(dst))),
        changed=tuple(sorted(name for name in set(src) & set(dst) if src[name] != dst[name])),
        extra=tuple(sorted(set(dst) - set(src))),
    )


def _file_key(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest + (":x" if os.access(path, os.X_OK) else "")


def worktree_snapshot(root: Path, rel_dir: str) -> dict[str, str]:
    """Files under ``root/rel_dir``: ``{relative path: sha256 [+ ":x" if executable]}``.

    Symlinks are followed and read as files. A missing directory gives ``{}``.
    """
    base = root / rel_dir
    if not base.is_dir():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(base.rglob("*")):
        if path.is_file():
            snapshot[path.relative_to(base).as_posix()] = _file_key(path)
    return snapshot


def commit_snapshot(root: Path, commit: str, rel_dir: str) -> dict[str, str]:
    """Files under ``rel_dir`` in ``commit``: ``{relative path: "<mode> <oid>"}``.

    Read-only (``git ls-tree``). No such tree gives ``{}``.
    """
    out = git_try(root, "ls-tree", "-r", "-z", commit, "--", rel_dir)
    if not out:
        return {}
    prefix = rel_dir.rstrip("/") + "/"
    snapshot: dict[str, str] = {}
    for record in out.split("\0"):
        meta, tab, path = record.partition("\t")
        if not tab or not path.startswith(prefix):
            continue
        parts = meta.split()
        if len(parts) != 3 or parts[1] != "blob":
            continue
        mode, _, oid = parts
        snapshot[path[len(prefix) :]] = f"{mode} {oid}"
    return snapshot


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def sync(root: Path) -> SyncResult:
    """Make ``root/MIRROR`` an exact copy of ``root/SOURCE``.

    New and changed skills are copied whole (modes and the exec bit carry over,
    symlinks are copied as files), skills gone from the source are removed.
    Nothing else in ``.agents/`` is touched. I/O errors propagate as ``OSError``.
    """
    source = root / SOURCE
    mirror = root / MIRROR
    diff = diff_snapshots(worktree_snapshot(root, SOURCE), worktree_snapshot(root, MIRROR))
    for name in (*diff.missing, *diff.changed):
        src, dst = source / name, mirror / name
        _remove(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, symlinks=False, copy_function=shutil.copy2)
        else:
            shutil.copy2(src, dst)
    for name in diff.extra:
        _remove(mirror / name)
    # A directory holding only empty directories has no files, so the snapshot
    # never reports it; drop leftovers once the source is gone.
    if not source.is_dir() and mirror.is_dir() and not worktree_snapshot(root, MIRROR):
        shutil.rmtree(mirror)
        agents = mirror.parent
        if agents.is_dir() and not any(agents.iterdir()):
            agents.rmdir()
    return SyncResult(added=diff.missing, updated=diff.changed, removed=diff.extra)


def prompt_index(repo: Path, names: Sequence[str]) -> str:
    """Index only the agent's assigned skills, using validated repo metadata."""
    if not names:
        return ""
    from aifactory.backlog.frontmatter import parse_frontmatter
    from aifactory.library.load import load_repo_item

    rows = [
        "\n\n## Available skills\n",
        "Read a skill's SKILL.md when its description matches the task.\n",
    ]
    for name in dict.fromkeys(names):
        item = load_repo_item(repo, "skill", name)
        skill = item.file("SKILL.md")
        assert skill is not None  # load_repo_item validates this file and its header
        header, _ = parse_frontmatter(skill.data.decode("utf-8"))
        description = " ".join(str(header["description"]).split())
        rows.append(f"- {name}: {description} (file: {SOURCE}/{name}/SKILL.md)\n")
    return "".join(rows)
