"""The hidden test that forces the test -> fix round of R10.

``write_hidden(workdir)`` writes ``<workdir>/hidden/test_hidden_slugify.py``:
outside the sandbox repo and every worktree. ``Context`` points
``HAIFA_VALIDATE_HIDDEN`` at that directory for every ``factory`` command, but
the variable is only a channel into ``validation.worker``: the worker pops it
from ``os.environ`` (agents inherit ``os.environ`` through ``operator_env`` and
so never see it) and ``install``s a wrapper around the engine's code test step
(``aifactory.testing.executor.execute``, which runs the checks of the
tester's plan). The wrapper ``placed`` the test at
``tests/test_hidden_slugify.py`` of the run's worktree for the duration of
those checks only, where the sandbox's own ``just test`` discovers it, and
removes it afterwards. ``exclude`` lists that path in the sandbox's
``info/exclude`` (not ``.gitignore``, which agents read), so a leftover is
never committed. The requirement (nothing sluggable gives ``x-empty``) cannot
be derived from the task and breaks neither ``greet`` nor the visible tests.
Runs before slugify exists skip it.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

HIDDEN_ENV = "HAIFA_VALIDATE_HIDDEN"
HIDDEN_DIR = "hidden"
HIDDEN_FILE = "test_hidden_slugify.py"
HIDDEN_CLASS = "HiddenSlugifyTest"
HIDDEN_EXPECTED = "x-empty"
HIDDEN_TARGET = "tests/" + HIDDEN_FILE  # where `just test` of the sandbox discovers it

HIDDEN_TEST = """\
import unittest

from sandbox import text


@unittest.skipUnless(hasattr(text, "slugify"), "slugify is not there yet")
class HiddenSlugifyTest(unittest.TestCase):
    def test_empty_slug_gets_the_x_prefix(self) -> None:
        # hidden requirement, not derivable from the task: nothing sluggable -> "x-empty"
        self.assertEqual(text.slugify("!!!"), "x-empty")
        self.assertEqual(text.slugify(""), "x-empty")
"""


def write_hidden(workdir: Path) -> Path:
    """Write the hidden test under `workdir`; return its directory (for ``HIDDEN_ENV``)."""
    path = workdir / HIDDEN_DIR
    path.mkdir(parents=True, exist_ok=True)
    (path / HIDDEN_FILE).write_text(HIDDEN_TEST, encoding="utf-8", newline="\n")
    return path


@contextmanager
def placed(root: Path, source: Path) -> Iterator[Path]:
    """Put the hidden test at ``root/tests/`` for the block; restore the prior state after."""
    root = Path(root)
    target = root / HIDDEN_TARGET
    if not target.parent.is_dir():
        yield target
        return
    previous = target.read_bytes() if target.is_file() else None
    target.write_bytes((Path(source) / HIDDEN_FILE).read_bytes())
    try:
        yield target
    finally:
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(previous)
        cache = target.parent / "__pycache__"
        if cache.is_dir():
            for pyc in cache.glob(HIDDEN_FILE.removesuffix(".py") + ".*.pyc"):
                pyc.unlink(missing_ok=True)


def wrap_test(original: Callable[[Any, Any], Any], source: Path) -> Callable[[Any, Any], Any]:
    """The engine's test step, with the hidden test in the run's worktree while it runs."""

    def execute(run: Any, plan: Any) -> Any:
        with placed(Path(run.repo_root), source):
            return original(run, plan)

    execute._haifa_hidden = True  # type: ignore[attr-defined]
    return execute


def install(source: Path) -> None:
    """Wrap ``aifactory.testing.executor.execute`` (once): every code test step runs the
    hidden test."""
    from aifactory.testing import executor

    if getattr(executor.execute, "_haifa_hidden", False):
        return
    executor.execute = wrap_test(executor.execute, source)  # type: ignore[assignment]


def exclude(repo: Path) -> None:
    """List the hidden test's path in the repo's ``info/exclude`` (shared by its worktrees)."""
    common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    ).stdout.strip()
    path = Path(common) if Path(common).is_absolute() else Path(repo) / common
    info = path / "info" / "exclude"
    info.parent.mkdir(parents=True, exist_ok=True)
    line = "/" + HIDDEN_TARGET
    text = info.read_text(encoding="utf-8") if info.is_file() else ""
    if line in text.splitlines():
        return
    if text and not text.endswith("\n"):
        text += "\n"
    info.write_text(text + line + "\n", encoding="utf-8", newline="\n")
