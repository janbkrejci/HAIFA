"""Recoverable dashboard handoff for the last HAIFA, using the existing updater.

The preserved tool Python runs this module after the dashboard exits. Installation,
checksum validation and version checks remain in upgrade.run_upgrade. The retained
private backup is also the recovery journal if the machine loses power.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from aifactory import oscompat
from aifactory.config.settings import load_local_checked
from aifactory.library.remote import version_key
from aifactory.migration_guard import (
    MARKER,
    check_home,
    migration_lock,
    require_quiet,
    write_manifest,
)
from aifactory.run.gitops import common_dir
from aifactory.upgrade import UpgradeError, fetch_bundle, run_upgrade
from aifactory.web.registry import Registry
from aifactory.web.server import dashboard_url, restart_command

ERROR_FILE = "giro-transition-error.json"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sqlite_database(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as stream:
        return stream.read(16) == b"SQLite format 3\x00"


def _copy(source: Path, target: Path) -> None:
    """Copy inactive data, backing up SQLite through its API, never just its WAL file."""
    if source.is_symlink():
        raise UpgradeError("migration_unsafe", f"Resolve the external data symlink first: {source}")
    if source.is_dir():
        target.mkdir(mode=0o700, parents=True)
        for item in source.iterdir():
            if item.name == MARKER:
                continue
            if (
                item.is_file()
                and not item.is_symlink()
                and item.name.endswith(("-wal", "-shm"))
                and _sqlite_database(item.with_name(item.name[:-4]))
            ):
                # Only sidecars belonging to a SQLite database are incorporated
                # by backup(). Ordinary files/directories retain these names.
                continue
            _copy(item, target / item.name)
        shutil.copystat(source, target)
    elif source.is_file():
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        sqlite = _sqlite_database(source)
        if source.suffix in {".db", ".sqlite", ".sqlite3"} and not sqlite:
            raise UpgradeError("migration_unsafe", f"Invalid SQLite database: {source}")
        if sqlite:
            with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
                with closing(sqlite3.connect(target)) as saved:
                    original.backup(saved)
                    if saved.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                        raise UpgradeError("migration_unsafe", f"Corrupt SQLite database: {source}")
            shutil.copystat(source, target)
        else:
            shutil.copy2(source, target)
            if _digest(source) != _digest(target):
                raise UpgradeError("migration_unsafe", f"Backup verification failed: {source}")
    else:
        raise UpgradeError("migration_unsafe", f"Cannot back up data: {source}")
    if sys.platform == "win32":
        # copy2/copytree do not preserve Windows DACLs. Freeze the source's
        # effective inherited rules on the copy so its new parent cannot widen them.
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$ErrorActionPreference='Stop'; "
                "$acl=Get-Acl -LiteralPath $env:GIRO_ACL_SOURCE; "
                "$acl.SetAccessRuleProtection($true,$true); "
                "Set-Acl -LiteralPath $env:GIRO_ACL_TARGET -AclObject $acl; "
                "$actual=Get-Acl -LiteralPath $env:GIRO_ACL_TARGET; "
                "if ($actual.Sddl -ne $acl.Sddl) { throw 'Backup ACL verification failed' }",
            ],
            env={**os.environ, "GIRO_ACL_SOURCE": str(source), "GIRO_ACL_TARGET": str(target)},
            capture_output=True,
            text=True,
            check=True,
        )


def _data_paths(home: Path) -> tuple[list[Path], int]:
    if (
        os.environ.get("HAIFA_DATABASE_URL")
        or os.environ.get("GIRO_DATABASE_URL")
        or (home / "database.yaml").exists()
    ):
        raise UpgradeError(
            "migration_unsafe",
            "Shared database requires a coordinated offline backup before migration.",
        )
    state, warnings = Registry(home).snapshot()
    if warnings:
        raise UpgradeError("migration_unsafe", "; ".join(warnings))
    paths = [home]
    external = os.environ.get("HAIFA_LIBRARY")
    if external:
        library = Path(external).expanduser()
        if not library.is_dir():
            raise UpgradeError("migration_unsafe", f"External library is unavailable: {library}")
        paths.append(library.resolve())
    for repo in state.repos:
        root = Path(repo.path)
        if not root.is_dir():
            raise UpgradeError("migration_unsafe", f"Registered repository is unavailable: {root}")
        local, _warnings = load_local_checked(root)
        if local.database_url:
            raise UpgradeError(
                "migration_unsafe", f"Cannot establish offline database state: {root}"
            )
        trace = Path(local.trace_db).expanduser()
        trace = trace if trace.is_absolute() else root / trace
        git = common_dir(root)
        if git is None:
            raise UpgradeError("migration_unsafe", f"Cannot find repository journal: {root}")
        paths.extend(p for p in (root / ".factory", trace, git / "haifa") if p.exists())
    # Store nested paths only once, without changing their absolute identities.
    unique: list[Path] = []
    for path in sorted(set(p.resolve() for p in paths), key=lambda p: len(p.parts)):
        if not any(path.is_relative_to(parent) for parent in unique):
            unique.append(path)
    return unique, state.port


def prepare(home: Path, bundle: str, current: str, target: str) -> Path:
    """Validate both releases before handing off. No installation in the dashboard process."""
    home = home.resolve()
    with migration_lock(home):
        check_home(home)
        require_quiet(home)
        paths, port = _data_paths(home)
        destination = home if os.environ.get("HAIFA_HOME") else home.with_name("giro")
        if destination != home and destination.exists():
            raise UpgradeError("migration_unsafe", f"GIRO home already exists: {destination}")
        if sys.prefix == sys.base_prefix:
            raise UpgradeError(
                "migration_unsafe", "Transition requires the distributed uv tool installation."
            )
        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup = home.with_name(f"{home.name}.pre-giro-{timestamp}-{uuid.uuid4().hex}")
        backup.mkdir(mode=0o700)
        # Keep even failed preparation backups, and never reuse/overwrite an earlier one.
        giro = fetch_bundle(bundle, backup)
        old_url = (
            f"https://github.com/janbkrejci/HAIFA/releases/download/v{current}/haifa-{current}.zip"
        )
        haifa = fetch_bundle(old_url, backup)
        checked = run_upgrade(
            str(giro), current=current, expected_version=target, dry_run=True, bundle_brand="giro"
        )
        if checked.min_factory_version and version_key(target) < version_key(
            checked.min_factory_version
        ):
            raise UpgradeError(
                "migration_unsafe", "GIRO release is below the library's minimum version."
            )
        run_upgrade(str(haifa), current="0.0.0", expected_version=current, dry_run=True)
        # Preserve a runnable Python + installed modules; uv may replace the original
        # environment. This is the existing updater's supervisor, not another installer.
        tool = backup / "tool"
        shutil.copytree(sys.prefix, tool, symlinks=True)
        python = tool / Path(sys.executable).relative_to(sys.prefix)
        command = restart_command()
        host = os.environ.get("HAIFA_DASH_HOST") or "127.0.0.1"
        for index, arg in enumerate(command):
            if arg == "--host":
                host = command[index + 1]
            elif arg.startswith("--host="):
                host = arg.split("=", 1)[1]
            elif arg == "--port":
                port = int(command[index + 1])
            elif arg.startswith("--port="):
                port = int(arg.split("=", 1)[1])
        manifest: dict[str, Any] = {
            "format": 1,
            "id": uuid.uuid4().hex,
            "state": "prepared",
            "source": str(home),
            "target": str(destination),
            "backup": str(backup),
            "original_version": current,
            "target_version": target,
            "haifa_bundle": str(haifa),
            "giro_bundle": str(giro),
            "bundle_hashes": {str(p): _digest(p) for p in (haifa, giro)},
            "paths": [str(p) for p in paths],
            "pid": os.getpid(),
            "launcher": os.getppid(),
            "restart": command,
            "port": port,
            "host": host,
            "tool_source": sys.prefix,
            "repositories": [repo.to_json() for repo in Registry(home).snapshot()[0].repos],
            "tool_hashes": {
                str(p.relative_to(tool)): _digest(p) for p in tool.rglob("*") if p.is_file()
            },
        }
        plan = backup / "plan.json"
        plan.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        plan.chmod(0o600)
        write_manifest(home, manifest)
        try:
            fd = os.open(backup / "worker.log", os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as log:
                subprocess.Popen(
                    [str(python), "-m", "aifactory.transition", str(plan)],
                    env={**os.environ, "PYTHONPATH": ""},
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    close_fds=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    if sys.platform == "win32"
                    else 0,
                    start_new_session=sys.platform != "win32",
                )
        except Exception:
            (home / MARKER).unlink()
            raise
        return plan


def _health(plan: dict[str, Any], app: str, version: str, home: Path) -> bool:
    url = dashboard_url(plan["port"], plan["host"])
    try:
        with urllib.request.urlopen(url + "api/health", timeout=2) as response:  # noqa: S310
            data = json.load(response)["data"]
        if not (
            data["app"] == app
            and data["version"] == version
            and Path(data["home"]).resolve() == home
        ):
            return False
        with urllib.request.urlopen(url + "api/repos", timeout=2) as response:  # noqa: S310
            repos = json.load(response)["data"]["repos"]

        def identity(items: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
            return sorted((r["id"], r["path"], r["name"]) for r in items)

        return identity(repos) == identity(plan["repositories"])
    except Exception:
        return False


def execute(plan_file: Path) -> None:
    """Handoff worker: preserve data, install once with run_upgrade, validate or restore."""
    plan = json.loads(plan_file.read_text("utf-8"))
    source, target, backup = (Path(plan[key]) for key in ("source", "target", "backup"))
    child: subprocess.Popen[Any] | None = None
    copied: list[tuple[Path, Path]] = []
    installed = False
    created_target = False
    env = {**os.environ, "HAIFA_OBS_RESTART": "1", "GIRO_OBS_RESTART": "1"}
    deadline = time.monotonic() + 120
    while oscompat.alive(plan["pid"]):
        if time.monotonic() > deadline:
            # Parent still serves HAIFA. Do not install into a live environment.
            (source / MARKER).unlink()
            (source / ERROR_FILE).write_text(
                json.dumps({"error": "Dashboard did not exit; transition cancelled."})
            )
            return
        time.sleep(0.1)
    try:
        # Only a uv tool launcher can hold its executable. The invoking shell is
        # normally long-lived and must never be waited for (or terminated).
        if sys.platform == "win32":
            image = oscompat.image_path(plan["launcher"])
            if image and Path(image).stem.lower() in {"factory", "giro"}:
                while oscompat.alive(plan["launcher"]):
                    if time.monotonic() > deadline:
                        raise UpgradeError(
                            "migration_unsafe", "Launcher did not exit; backup retained."
                        )
                    time.sleep(0.1)
        for name, digest in plan["bundle_hashes"].items():
            if _digest(Path(name)) != digest:
                raise UpgradeError("checksum_mismatch", f"Retained bundle changed: {name}")
        for index, name in enumerate(plan["paths"]):
            original, saved = Path(name), backup / "data" / str(index)
            _copy(original, saved)
            copied.append((original, saved))
        plan["data_hashes"] = {
            str(p.relative_to(backup)): _digest(p)
            for _, saved in copied
            for p in ([saved] if saved.is_file() else saved.rglob("*"))
            if p.is_file()
        }
        plan_file.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        if target != source:
            if target.exists():
                raise UpgradeError(
                    "migration_unsafe", f"GIRO home appeared during preparation: {target}"
                )
            stage = backup / "staging"
            _copy(source, stage)
            stage.chmod(0o700)
            if (stage / "env").exists():
                (stage / "env").chmod(0o600)
            os.replace(stage, target)
            created_target = True
        # Both env spellings identify the same home in every subprocess. The new
        # process must explicitly accept this prepared transaction (T02 protocol).
        env.update(HAIFA_HOME=str(target), GIRO_HOME=str(target), GIRO_MIGRATION_ID=plan["id"])
        write_manifest(target, plan)
        (target / ERROR_FILE).unlink(missing_ok=True)
        installed = True  # uv failures may have partially replaced the environment
        run_upgrade(
            plan["giro_bundle"],
            current=plan["original_version"],
            expected_version=plan["target_version"],
            environ=env,
            handoff=False,
            refresh=False,
            bundle_brand="giro",
        )
        child = subprocess.Popen(plan["restart"], env=env)
        deadline = time.monotonic() + 60
        while not _health(plan, "giro-dashboard", plan["target_version"], target):
            if child.poll() is not None or time.monotonic() > deadline:
                raise UpgradeError("restart_failed", "GIRO health/version/home validation failed.")
            time.sleep(0.2)
        plan["state"] = "committed"
        write_manifest(target, plan)
        write_manifest(source, plan)
        plan_file.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    except Exception as exc:
        # Only terminate the child this transaction started, never an existing task.
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=30)
        if created_target and target.exists():
            shutil.move(target, backup / "failed-giro-home")
        # Keep the failed post-install state too before restoring the complete set.
        if installed:
            for name, digest in plan["data_hashes"].items():
                if _digest(backup / name) != digest:
                    raise UpgradeError(
                        "rollback_failed",
                        f"Backup changed: {name}; stop writers and inspect {plan_file}",
                    ) from exc
            for index, (original, saved) in enumerate(copied):
                failed = backup / "failed-data" / str(index)
                failed.parent.mkdir(parents=True, exist_ok=True)
                # External libraries/repos can live on another volume. move()
                # retains their failed state with copy-and-delete after EXDEV.
                shutil.move(original, failed)
                _copy(saved, original)
            try:
                run_upgrade(
                    plan["haifa_bundle"],
                    current="0.0.0",
                    expected_version=plan["original_version"],
                    environ=os.environ,
                    handoff=False,
                    refresh=False,
                )
            except Exception:
                # uv itself can be unavailable or fail again during recovery. Its
                # original environment was preserved before any replacement.
                tool = Path(plan["tool_source"])
                for name, digest in plan["tool_hashes"].items():
                    if _digest(backup / "tool" / name) != digest:
                        raise UpgradeError(
                            "rollback_failed", f"Preserved tool changed: {name}"
                        ) from exc
                if tool.exists():
                    shutil.move(tool, backup / "failed-tool")
                shutil.copytree(backup / "tool", tool, symlinks=True)
        (source / MARKER).unlink(missing_ok=True)
        (source / ERROR_FILE).write_text(
            json.dumps({"error": f"{type(exc).__name__}: {exc}"}), encoding="utf-8"
        )
        restored = subprocess.Popen(
            plan["restart"], env={**env, "HAIFA_HOME": str(source), "GIRO_HOME": str(source)}
        )
        deadline = time.monotonic() + 60
        while not _health(plan, "haifa-dashboard", plan["original_version"], source):
            if restored.poll() is not None or time.monotonic() > deadline:
                write_manifest(source, plan)
                raise UpgradeError(
                    "rollback_failed",
                    f"HAIFA restart failed; retained recovery journal: {plan_file}",
                ) from exc
            time.sleep(0.2)


if __name__ == "__main__":
    execute(Path(sys.argv[1]))
