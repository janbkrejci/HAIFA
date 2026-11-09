"""Fresh repository policy and the acceptance barrier for automatic work."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from aifactory.run.errors import TaskRunError

DISABLED = "auto_continue_disabled"
DISABLED_MESSAGE = (
    "Auto continue je v tomto repozitáři vypnuté; další automatický běh nebyl přijat."
)


def enabled(repo: Path) -> bool:
    from aifactory.repo_settings import RepositorySettings, SettingsError

    try:
        return RepositorySettings(repo).read().auto_continue
    except SettingsError as exc:
        raise TaskRunError(exc.code, str(exc)) from exc


def require_enabled(repo: Path) -> None:
    if not enabled(repo):
        raise TaskRunError(DISABLED, DISABLED_MESSAGE)


@contextmanager
def acceptance(repo: Path, automatic: bool = True) -> Iterator[None]:
    """Hold the update lock only through claim/reclaim/spawn, never execution/wait."""
    from aifactory.repo_settings import RepositorySettings, SettingsError

    if not automatic:
        yield
        return
    try:
        with RepositorySettings(repo).automatic_start() as allowed:
            if not allowed:
                raise TaskRunError(DISABLED, DISABLED_MESSAGE)
            yield
    except SettingsError as exc:
        raise TaskRunError(exc.code, str(exc)) from exc
