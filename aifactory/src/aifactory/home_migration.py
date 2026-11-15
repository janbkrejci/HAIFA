"""Explicit offline migration using the same retained-data protocol as the HAIFA handoff."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
import uuid
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from aifactory import __version__
from aifactory.environment import child_environment, value
from aifactory.home import load_env_file
from aifactory.migration_guard import (
    MARKER,
    check_home,
    migration_lock,
    require_quiet,
    write_manifest,
)
from aifactory.transition import _copy as _copy
from aifactory.transition import _data_paths, _digest
from aifactory.upgrade import UpgradeError, run_upgrade


def migrate(source: Path, target: Path, haifa_bundle: Path) -> dict[str, Any]:
    """Retain source + verified software + offline data; publish only a complete target.

    Failures retain the journal, never merge into an existing directory. A prepared
    marker deliberately requires recovery after interruption rather than guessing.
    """
    source, target = source.resolve(), target.resolve()
    with ExitStack() as locks:
        for home in sorted({source, target}):
            locks.enter_context(migration_lock(home))
        if (target / MARKER).exists():
            check_home(target, writing=True)
            completed: dict[str, Any] = json.loads((target / MARKER).read_text("utf-8"))
            if Path(completed["source"]).resolve() == source:
                return completed
        check_home(source)
        require_quiet(source)
        require_quiet(target)
        if not source.is_dir() or (source != target and target.exists()):
            raise UpgradeError(
                "migration_collision", f"Inspect and back up {source} and {target} first."
            )
        env = child_environment(HOME=str(source))
        load_env_file(env)
        paths, _port = _data_paths(source, environ=env)
        bundle_digest = _digest(haifa_bundle)
        checked = run_upgrade(str(haifa_bundle), current="0.0.0", dry_run=True, environ=env)
        if not checked.target_version.startswith("0.1."):
            raise UpgradeError(
                "migration_unsafe", "Retain the verified last HAIFA 0.1 bundle for rollback."
            )
        identity = uuid.uuid4().hex
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup = source.with_name(f"{source.name}.pre-giro-{stamp}-{identity}")
        backup.mkdir(mode=0o700)
        software = backup / haifa_bundle.name
        shutil.copy2(haifa_bundle, software)
        if _digest(software) != bundle_digest:
            raise UpgradeError("checksum_mismatch", "Rollback bundle changed during preparation")
        manifest: dict[str, Any] = {
            "format": 1,
            "id": identity,
            "state": "prepared",
            "source": str(source),
            "target": str(target),
            "backup": str(backup),
            "original_version": checked.target_version,
            "target_version": __version__,
            "haifa_bundle": str(software),
            "bundle_hashes": {str(software): _digest(software)},
            "paths": [str(path) for path in paths],
        }
        plan = backup / "plan.json"
        plan.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        plan.chmod(0o600)
        for index, path in enumerate(paths):
            _copy(path, backup / "data" / str(index))
        manifest["data_hashes"] = {
            str(path.relative_to(backup)): _digest(path)
            for path in (backup / "data").rglob("*")
            if path.is_file()
        }
        plan.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        # Publishing a prepared marker first makes crashes fail closed in both builds.
        write_manifest(source, manifest)
        if source != target:
            stage = backup / "staging"
            _copy(source, stage)
            if os.name != "nt":
                stage.chmod(0o700)
                if (stage / "env").exists():
                    (stage / "env").chmod(0o600)
            write_manifest(stage, manifest)
            if target.exists():
                raise UpgradeError(
                    "migration_collision", f"Target appeared during migration: {target}"
                )
            os.replace(stage, target)
        if os.name != "nt":
            target.chmod(0o700)
            if (target / "env").exists():
                (target / "env").chmod(0o600)
        manifest["state"] = "committed"
        # Any interruption between these writes remains blocked, with the complete backup.
        write_manifest(target, manifest)
        write_manifest(source, manifest)
        plan.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest


def migration_command(argv: list[str]) -> int:
    from aifactory.cli import _emit_fail, _emit_ok, _Parser, _UsageError

    parser = _Parser(prog="giro migrate", description=__doc__)
    add_arguments(parser)
    try:
        args = parser.parse_args(argv)
    except _UsageError as exc:
        return _emit_fail("usage_error", str(exc), exit_code=2)
    try:
        if not args.confirm:
            raise UpgradeError("migration_required", "Stop all writers and repeat with --confirm.")
        explicit = value("HOME")
        user_home = Path(os.environ.get("HOME") or str(Path.home()))
        parent = Path(os.environ.get("XDG_CONFIG_HOME") or str(user_home / ".config")).expanduser()
        source = Path(explicit).expanduser() if explicit else parent / "haifa"
        target = source if explicit else parent / "giro"
        result = migrate(source, target, args.haifa_bundle)
    except Exception as exc:
        return _emit_fail(
            getattr(exc, "code", "migration_unavailable"),
            str(exc) + " Stop writers; preserve the current state and restore the verified backup "
            "using plan.json. See docs/rebranding/release.md.",
            exit_code=2,
        )
    if args.json:
        return _emit_ok(result)
    print(f"GIRO data ready at {result['target']}; rollback backup: {result['backup']}")
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--confirm", action="store_true", help="confirm all HAIFA writers are stopped"
    )
    parser.add_argument("--haifa-bundle", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
