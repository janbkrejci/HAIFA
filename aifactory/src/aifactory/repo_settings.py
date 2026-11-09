"""Repository-local operating choices in HAIFA_HOME, independent of the dashboard.

Consumers must propagate SettingsError and must never reuse an earlier enabled value.
Automatic starts must be accepted inside automatic_start(), under the update lock.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from aifactory import oscompat
from aifactory.config.source import GitError, git
from aifactory.harness import settings as harness_settings
from aifactory.home import haifa_home


class SettingsError(Exception):
    """An observable error; no legacy or cached settings may replace it."""

    def __init__(self, code: str, message: str, path: Path) -> None:
        super().__init__(message)
        self.code = code
        self.path = path


class RepoSettings(BaseModel):
    """Version 1; null harness inherits the computer's local default."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    version: Literal[1] = 1
    auto_merge: bool = False
    auto_continue: bool = False
    harness: Literal["claude", "codex", "pi"] | None = None


def repository_identity(repo: Path) -> str:
    """Canonical common Git directory: worktrees share it, independent clones do not.

    Deliberately uncached: moving/replacing a clone must not retain an old identity.
    """
    try:
        common = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    except GitError as exc:
        raise SettingsError("invalid_config", str(exc), repo) from exc
    return os.path.normcase(str(Path(common).resolve()))


class RepositorySettings:
    """Fresh validated reads and serialized, atomic partial updates.

    Instances contain no settings cache. The lock file is permanent (never unlink it).
    Do not nest operations holding this lock, including from automatic_start().
    """

    def __init__(self, repo: Path, home: Path | None = None) -> None:
        self.identity = repository_identity(repo)
        self.key = hashlib.sha256(self.identity.encode("utf-8")).hexdigest()
        self.directory = (haifa_home() if home is None else home) / "repositories"
        self.path = self.directory / f"{self.key}.json"
        self.lock_path = self.directory / f"{self.key}.lock"

    def read(self) -> RepoSettings:
        """Missing means defaults; this operation creates no files or directories."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return RepoSettings()
        except UnicodeError as exc:
            raise SettingsError("repo_settings_invalid", str(exc), self.path) from exc
        except OSError as exc:
            raise SettingsError("repo_settings_io", str(exc), self.path) from exc
        try:
            raw = json.loads(text)
            if not isinstance(raw, dict) or type(raw.get("version")) is not int:
                raise ValueError("record must be an object with an integer version")
            if raw["version"] != 1:
                raise SettingsError(
                    "repo_settings_version", f"unsupported version {raw['version']}", self.path
                )
            if set(raw) != {"version", "auto_merge", "auto_continue", "harness"}:
                raise ValueError("record must contain all version 1 fields")
            return RepoSettings.model_validate(raw)
        except (ValueError, UnicodeError) as exc:
            raise SettingsError("repo_settings_invalid", str(exc), self.path) from exc

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                oscompat.lock(fd, blocking=True)
                try:
                    yield
                finally:
                    oscompat.unlock(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise SettingsError("repo_settings_io", str(exc), self.path) from exc

    def _write(self, settings: RepoSettings) -> None:
        fd, temporary = tempfile.mkstemp(prefix=f".{self.key}-", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(settings.model_dump_json(indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def update(self, changes: Mapping[str, object]) -> RepoSettings:
        """Patch only supplied fields, re-reading under the cross-process lock."""
        with self._updating(changes) as settings:
            return settings

    def update_and_show(self, changes: Mapping[str, object]) -> dict[str, Any]:
        """Resolve the resulting payload before saving, under the update lock.

        Inherited settings errors prevent the save; an explicit repository harness
        never requires reading the computer default. No fallible read follows a save.
        """
        with self._updating(changes) as settings:
            return self.show(settings)

    @contextlib.contextmanager
    def _updating(self, changes: Mapping[str, object]) -> Iterator[RepoSettings]:
        if not changes or set(changes) - {"auto_merge", "auto_continue", "harness"}:
            raise SettingsError("invalid_value", "supply only operating settings", self.path)
        with self._locked():
            current = self.read()
            try:
                settings = RepoSettings.model_validate({**current.model_dump(), **changes})
            except ValidationError as exc:
                raise SettingsError("invalid_value", str(exc), self.path) from exc
            yield settings
            self._write(settings)

    def show(self, settings: RepoSettings | None = None) -> dict[str, Any]:
        """Common CLI/dashboard payload; resolution uses this instance's HAIFA_HOME."""
        value = self.read() if settings is None else settings
        effective_harness: str | None = value.harness
        if effective_harness is None:
            try:
                machine = harness_settings.read(self.directory.parent)
            except (OSError, ValueError) as exc:
                raise SettingsError("repo_settings_invalid", str(exc), self.path) from exc
            effective_harness = machine.default_harness if machine else None
        merge_policy = self.merge_policy(value)
        if settings is None and not self.path.exists():
            merge_policy["source"] = "default"
        return {
            "identity": self.identity,
            "path": str(self.path),
            "settings": value.model_dump(),
            "effective_harness": effective_harness,
            "auto_merge_policy": merge_policy,
        }

    def merge_policy(self, settings: RepoSettings | None = None) -> dict[str, Any]:
        """Effective automatic merge value and its local source; never consult backlog."""
        value = self.read() if settings is None else settings
        return {
            "value": value.auto_merge,
            "source": "repository" if settings is not None or self.path.exists() else "default",
            "path": str(self.path),
        }

    @contextlib.contextmanager
    def automatic_start(self) -> Iterator[bool]:
        """T02 barrier: accept/reserve/spawn inside this scope only when True.

        The caller must not defer acceptance until after releasing the lock. A false
        result or SettingsError forbids a start. Accepted runs may outlive the scope.
        Manual starts do not use this barrier. Enabling the flag never starts work.
        """
        with self._locked():
            yield self.read().auto_continue

    @contextlib.contextmanager
    def automatic_merge(self) -> Iterator[bool]:
        """Serialize the final policy check and hosting merge submission with updates.

        Never hold this lock while waiting for CI. Once the hosting request is sent,
        switching off cannot withdraw it; update waits for the submission to return.
        """
        with self._locked():
            yield self.read().auto_merge
