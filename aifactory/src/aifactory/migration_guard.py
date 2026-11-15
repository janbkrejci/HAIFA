"""Shared last-HAIFA/GIRO migration protocol; no data is written through a marker."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from aifactory import __version__, oscompat
from aifactory.upgrade import UpgradeError

MARKER = "giro-migration.json"


def _absolute_path(value: Any) -> Path:
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise ValueError("Expected an absolute migration path")
    return Path(value).resolve()


def _hashes(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or any(
        not isinstance(key, str)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        for key, digest in value.items()
    ):
        raise ValueError("Invalid recovery checksum records")
    return value


def _validate_manifest(data: Any, *, complete: bool) -> dict[str, Any]:
    """Check the shared offline/T04 recovery schema before a marker permits access."""
    if not isinstance(data, dict) or type(data.get("format")) is not int or data["format"] != 1:
        raise ValueError("Unsupported migration manifest")
    if not isinstance(data.get("id"), str) or not data["id"]:
        raise ValueError("Missing migration identity")
    if data.get("state") not in ("prepared", "committed"):
        raise ValueError("Invalid migration phase")
    for key in ("original_version", "target_version"):
        if not isinstance(data.get(key), str) or not re.fullmatch(r"\d+\.\d+\.\d+", data[key]):
            raise ValueError("Missing migration version")
    source = _absolute_path(data["source"])
    _absolute_path(data["target"])
    backup = _absolute_path(data["backup"])
    paths = data["paths"]
    if not isinstance(paths, list) or not paths:
        raise ValueError("Missing recovery paths")
    originals = [_absolute_path(path) for path in paths]
    if source not in originals or len(set(originals)) != len(originals):
        raise ValueError("Inconsistent recovery paths")
    bundles = _hashes(data["bundle_hashes"])
    for name in ("haifa_bundle", "giro_bundle"):
        if name == "haifa_bundle" or name in data:
            bundle = _absolute_path(data[name])
            if (
                data[name] not in bundles
                or not bundle.is_relative_to(backup)
                or not bundle.is_file()
            ):
                raise ValueError("Missing retained software")
    # T04 additionally retains its runnable tool environment for uv failure recovery.
    if any(key in data for key in ("giro_bundle", "tool_source", "tool_hashes")):
        _absolute_path(data["giro_bundle"])
        _absolute_path(data["tool_source"])
        tools = _hashes(data["tool_hashes"])
        if not tools:
            raise ValueError("Missing retained tool records")
        for name in tools:
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or not (backup / "tool" / path).is_file():
                raise ValueError("Invalid retained tool record")
    if complete:
        records = _hashes(data["data_hashes"])
        files: set[str] = set()
        for index in range(len(paths)):
            saved = backup / "data" / str(index)
            if not saved.exists():
                raise ValueError("Missing retained data")
            files.update(
                str(path.relative_to(backup))
                for path in ([saved] if saved.is_file() else saved.rglob("*"))
                if path.is_file()
            )
        if set(records) != files:
            raise ValueError("Incomplete retained data records")
    return data


def check_home(home: Path, *, writing: bool = False, expected_source: Path | None = None) -> None:
    if not (home / MARKER).exists() and expected_source is None:
        return
    # Only the coordinator may read a prepared target. Every writer requires a
    # completed transaction with complete recovery records and matching copies.
    if __version__.startswith("1."):
        try:
            data = _validate_manifest(json.loads((home / MARKER).read_text("utf-8")), complete=True)
            retained = _validate_manifest(
                json.loads((Path(data["backup"]) / "plan.json").read_text("utf-8")), complete=True
            )
            source = Path(data["source"])
            pointer = _validate_manifest(
                json.loads((source / MARKER).read_text("utf-8")),
                complete=data["state"] == "committed",
            )
            pointer_matches = pointer == data or (
                data["state"] == "prepared"
                and pointer == {key: item for key, item in data.items() if key != "data_hashes"}
            )
            if (
                retained == data
                and pointer_matches
                and Path(data["target"]).resolve() == home.resolve()
                and (expected_source is None or source.resolve() == expected_source.resolve())
                and (
                    data["state"] == "committed"
                    or (not writing and os.environ.get("GIRO_MIGRATION_ID") == data["id"])
                )
            ):
                return
        except (OSError, ValueError, KeyError, TypeError):
            pass
    raise UpgradeError(
        "migration_pending",
        f"{home / MARKER}: incomplete, inconsistent or pending GIRO migration. "
        "Wait for the migration coordinator, or stop all writers and restore the "
        "verified backup recorded in this manifest before starting HAIFA.",
    )


@contextmanager
def migration_lock(home: Path) -> Iterator[None]:
    home = home.resolve()
    home.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(home.with_name(home.name + ".giro-migration.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            oscompat.lock(fd, blocking=False)
        except OSError as exc:
            raise UpgradeError(
                "update_busy", "Another migration is preparing; wait and retry."
            ) from exc
        yield
    finally:
        os.close(fd)


@contextmanager
def process_lease(home: Path) -> Iterator[None]:
    """Register a cooperating CLI/dashboard until exit; serialized against preparation."""
    home = home.resolve()
    directory = home.with_name(home.name + ".giro-processes")
    try:
        with migration_lock(home):
            check_home(home)
            directory.mkdir(mode=0o700, exist_ok=True)
            path = directory / f"{os.getpid()}-{uuid.uuid4().hex}"
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            try:
                oscompat.lock(fd, blocking=False)
            except OSError:
                os.close(fd)
                raise
    except OSError as exc:
        raise UpgradeError(
            "migration_unavailable", f"Cannot protect HAIFA home {home}: {exc}"
        ) from exc
    try:
        yield
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)


def require_quiet(home: Path) -> None:
    """Called under migration_lock. Stale leases are harmless; unknown state fails closed."""
    home = home.resolve()
    directory = home.with_name(home.name + ".giro-processes")
    for path in directory.glob("*"):
        if path.name.split("-", 1)[0] == str(os.getpid()):
            continue
        fd = os.open(path, os.O_RDWR)
        try:
            try:
                oscompat.lock(fd, blocking=False)
            except OSError as exc:
                raise UpgradeError(
                    "runs_active",
                    "Another HAIFA process is active. Stop it and retry the transition.",
                ) from exc
        finally:
            os.close(fd)


def write_manifest(home: Path, manifest: dict[str, object]) -> None:
    path = home / MARKER
    temporary = home / f".{MARKER}.{uuid.uuid4().hex}"
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
    os.replace(temporary, path)
