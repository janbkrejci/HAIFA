"""Shared last-HAIFA/GIRO migration protocol; no data is written through a marker."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from aifactory import __version__, oscompat
from aifactory.upgrade import UpgradeError

MARKER = "giro-migration.json"


def check_home(home: Path, *, writing: bool = False) -> None:
    if (home / MARKER).exists():
        # Shared with the GIRO build: only its coordinator may open a prepared
        # target. A later GIRO start accepts a completed, matching transaction.
        if __version__.startswith("1."):
            try:
                data = json.loads((home / MARKER).read_text("utf-8"))
                retained = json.loads((Path(data["backup"]) / "plan.json").read_text("utf-8"))
                source = Path(data["source"])
                pointer = (
                    json.loads((source / MARKER).read_text("utf-8")) if source.exists() else data
                )
                if (
                    data["format"] == 1
                    and all(
                        pointer[key] == data[key] for key in ("id", "source", "target", "state")
                    )
                    and Path(data["target"]).resolve() == home.resolve()
                    and retained["id"] == data["id"]
                    and retained["source"] == data["source"]
                    and retained["target"] == data["target"]
                    and (
                        data["state"] == retained["state"] == "committed"
                        or (
                            not writing
                            and data["state"] == retained["state"] == "prepared"
                            and os.environ.get("GIRO_MIGRATION_ID") == data["id"]
                        )
                    )
                ):
                    return
            except (OSError, ValueError, KeyError, TypeError):
                pass
        raise UpgradeError(
            "migration_pending",
            f"{home / MARKER}: GIRO migration is prepared or committed. "
            "Wait for the migration coordinator, or stop all writers and restore the "
            "verified backup recorded in this manifest before starting HAIFA.",
        )


@contextmanager
def migration_lock(home: Path) -> Iterator[None]:
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
