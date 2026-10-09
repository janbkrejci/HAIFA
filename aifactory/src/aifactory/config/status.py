"""Uncommitted changes to the shared configuration, relative to ``base``.

The shared configuration is ``.factory/`` (without ``local.yaml``, worktrees and the
trace DB) and the skills of the repo in ``.claude/skills/`` and ``.agents/skills/``.

Runs read the configuration from the ``base`` commit, so anything changed in
the working tree is ignored by them; these changes are reported as warnings.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from aifactory.config.source import FACTORY_DIR, git

SHARED_FILES = (
    ".factory/config.yaml",
    ".factory/agents.yaml",
    ".factory/roles.yaml",
    ".factory/manifest.yaml",
)
SHARED_DIRS = (
    ".factory/prompts/",
    ".factory/workflows/",
    ".factory/extensions/",
    ".claude/skills/",
    ".agents/skills/",
)
CONFIG_PATHSPECS = (FACTORY_DIR, ".claude/skills", ".agents/skills")

ChangeStatus = Literal["modified", "added", "deleted", "untracked"]
_STATUS: dict[str, ChangeStatus] = {"M": "modified", "A": "added", "D": "deleted"}


def is_shared_config_path(rel: str) -> bool:
    """True for committed configuration (never ``local.yaml``, worktrees or the trace DB)."""
    return rel in SHARED_FILES or rel.startswith(SHARED_DIRS)


@dataclass(frozen=True)
class ConfigChange:
    path: str
    status: ChangeStatus

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "status": self.status}


_NULL_SHA = frozenset("0")


def _raw_entries(out: str) -> list[tuple[str, str, str, str, str]]:
    """``git diff-index --raw -z`` as (src mode, dst mode, src sha, dst sha + status, path)."""
    fields = out.split("\0")
    entries = []
    for header, path in zip(fields[0::2], fields[1::2], strict=False):
        parts = header.lstrip(":").split()
        if len(parts) != 5 or not path:
            continue
        entries.append((parts[0], parts[1], parts[2], parts[3] + " " + parts[4], path))
    return entries


def config_changes(root: Path, sha: str) -> list[ConfigChange]:
    """Shared config files whose working-tree state differs from commit ``sha``."""
    return [
        c
        for c in working_tree_changes(root, sha, CONFIG_PATHSPECS)
        if is_shared_config_path(c.path)
    ]


def working_tree_changes(root: Path, sha: str, pathspecs: Sequence[str]) -> list[ConfigChange]:
    """Files under `pathspecs` whose working-tree state differs from commit ``sha``.

    Only plumbing that never writes the index: ``git diff`` would refresh it (and take
    ``index.lock``) even with ``GIT_OPTIONAL_LOCKS=0``. Entries whose index stat data
    is stale come back from ``diff-index`` as possibly modified; their content is
    hashed (``hash-object``, nothing written) and compared with the commit.
    """
    found: dict[str, ChangeStatus] = {}
    stale: dict[str, str] = {}
    out = git(root, "diff-index", "--raw", "-z", "--no-renames", sha, "--", *pathspecs)
    for src_mode, dst_mode, src_sha, dst, path in _raw_entries(out):
        dst_sha, code = dst.split(" ", 1)
        status = _STATUS.get(code[:1], "modified")
        if (
            status == "modified"
            and src_mode == dst_mode
            and frozenset(dst_sha) == _NULL_SHA
            and (root / path).is_file()
        ):
            stale[path] = src_sha
            continue
        found[path] = status
    if stale:
        paths = list(stale)
        hashes = git(root, "hash-object", "--", *paths).split()
        for path, current in zip(paths, hashes, strict=False):
            if current != stale[path]:
                found[path] = "modified"
    out = git(root, "ls-files", "-z", "--others", "--exclude-standard", "--", *pathspecs)
    for path in (p for p in out.split("\0") if p):
        found.setdefault(path, "untracked")
    return [ConfigChange(path=path, status=status) for path, status in sorted(found.items())]


def change_warnings(changes: list[ConfigChange], base: str, sha: str) -> list[str]:
    """One stable, human-readable warning per change."""
    return [
        f"{c.path} is {c.status} in the working tree but not committed to {base} "
        f"({sha[:7]}); runs use the committed version"
        for c in changes
    ]
