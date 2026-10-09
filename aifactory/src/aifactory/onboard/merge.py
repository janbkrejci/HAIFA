"""Three-way merge of a prompt for the sssf conversion (AR32).

Base is the stock sssf text, ours the repo's text, theirs the library's. ``git merge-file``
runs on temporary files and touches no repository.
"""

from __future__ import annotations

import difflib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from aifactory.providers.git import run_bytes

MergeKind = Literal["stock", "same", "clean", "union", "conflict"]
MARKER_SIZE = 13
_LABELS = ["-L", "repo", "-L", "sssf", "-L", "library"]


@dataclass(frozen=True)
class MergeResult:
    """The merged text; ``quote`` is the repo's change for a ``conflict``."""

    kind: MergeKind
    text: bytes
    quote: str | None = None


def quote_change(base: bytes, ours: bytes, limit: int = 20) -> str:
    """The change from ``base`` (sssf) to ``ours`` (repo) as a short unified diff."""
    lines = list(
        difflib.unified_diff(
            base.decode("utf-8", "replace").splitlines(),
            ours.decode("utf-8", "replace").splitlines(),
            fromfile="sssf",
            tofile="repo",
            n=0,
            lineterm="",
        )
    )
    if len(lines) > limit:
        rest = len(lines) - limit
        lines = [*lines[:limit], f"… ({rest} more lines)"]
    return "\n".join(lines)


def _only_insertions(text: bytes) -> bool:
    """True when every conflict block of a ``--diff3`` output has an empty base section."""
    start, base, middle = (c * MARKER_SIZE for c in (b"<", b"|", b"="))
    blocks = 0
    in_base = False
    base_lines = 0
    for line in text.splitlines():
        if line.startswith(start) and not line.startswith(start + b"<"):
            blocks += 1
        elif line.startswith(base) and not line.startswith(base + b"|"):
            in_base, base_lines = True, 0
        elif line.startswith(middle) and not line.startswith(middle + b"="):
            if in_base and base_lines:
                return False
            in_base = False
        elif in_base:
            base_lines += 1
    return blocks > 0


def _merge_file(tmp: Path, extra: list[str]) -> tuple[int, bytes]:
    args = [
        "merge-file",
        "-p",
        *extra,
        f"--marker-size={MARKER_SIZE}",
        *_LABELS,
        "ours.md",
        "base.md",
        "theirs.md",
    ]
    proc = run_bytes(tmp, args)
    if proc.returncode < 0 or proc.returncode >= 128:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git merge-file failed ({proc.returncode}): {detail}")
    return proc.returncode, proc.stdout


def merge_prompt(base: bytes, ours: bytes, theirs: bytes) -> MergeResult:
    """Merge the repo's change to the stock text into the library text."""
    if ours == base:
        return MergeResult("stock", theirs)
    if ours == theirs:
        return MergeResult("same", ours)
    with tempfile.TemporaryDirectory(prefix="aifactory-merge-") as name:
        tmp = Path(name)
        (tmp / "ours.md").write_bytes(ours)
        (tmp / "base.md").write_bytes(base)
        (tmp / "theirs.md").write_bytes(theirs)
        code, out = _merge_file(tmp, ["--diff3"])
        if code == 0:
            return MergeResult("clean", out)
        if _only_insertions(out):
            _, union = _merge_file(tmp, ["--union"])
            return MergeResult("union", union)
    return MergeResult("conflict", theirs, quote_change(base, ours))


__all__ = ["MergeKind", "MergeResult", "merge_prompt", "quote_change"]
