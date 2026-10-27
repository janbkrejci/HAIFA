"""Best-effort machine resources and explicit factory-owned cleanup."""

from __future__ import annotations

import ctypes
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from aifactory import review
from aifactory.web.registry import RepoEntry
from aifactory.workflow import adaptive

DISK_MIN_FREE = 10 * 1024**3
MEMORY_MIN_FREE = 1024**3
MIN_FREE_RATIO = 0.10


def _memory() -> tuple[int | None, int | None]:
    """Return available and total physical bytes, or unknown values."""
    try:
        if sys.platform == "win32":

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_uint32),
                    ("load", ctypes.c_uint32),
                    *[
                        (name, ctypes.c_uint64)
                        for name in (
                            "total",
                            "available",
                            "page_total",
                            "page_available",
                            "virtual_total",
                            "virtual_available",
                            "extended_available",
                        )
                    ],
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.available), int(status.total)
        elif sys.platform.startswith("linux"):
            fields = dict(re.findall(r"^(\w+):\s+(\d+)", Path("/proc/meminfo").read_text(), re.M))
            return int(fields["MemAvailable"]) * 1024, int(fields["MemTotal"]) * 1024
        elif sys.platform == "darwin":
            total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=5))
            stats = subprocess.check_output(["vm_stat"], text=True, timeout=5)
            match = re.search(r"page size of (\d+) bytes", stats)
            if match is None:
                return None, total
            page_size = int(match[1])
            pages = dict(re.findall(r"^(Pages [\w ]+):\s+(\d+)", stats, re.M))
            available = sum(
                int(pages[key]) for key in ("Pages free", "Pages inactive", "Pages speculative")
            )
            return available * page_size, total
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        pass
    return None, None


def _status(free: int | None, total: int | None, minimum: int) -> str:
    return (
        "warning"
        if free is not None
        and (free < minimum or (total is not None and total > 0 and free / total < MIN_FREE_RATIO))
        else "ok"
    )


def _volumes(home: Path, repos: Sequence[RepoEntry]) -> list[dict[str, Any]]:
    volumes: dict[str, dict[str, Any]] = {}
    for path in [home, Path(tempfile.gettempdir()), *(Path(repo.path) for repo in repos)]:
        path = path.resolve()
        existing = path
        # A registered repository or a fresh home can be absent; inspect its volume.
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        try:
            key = str(existing.stat().st_dev)
        except OSError:
            key = existing.anchor
        if key not in volumes:
            try:
                usage = shutil.disk_usage(existing)
                free, total = usage.free, usage.total
            except OSError:
                free, total = None, None
            volumes[key] = {
                "id": key,
                "paths": [],
                "free": free,
                "total": total,
                "status": _status(free, total, DISK_MIN_FREE),
            }
        if str(path) not in volumes[key]["paths"]:
            volumes[key]["paths"].append(str(path))
    return list(volumes.values())


def system_info(home: Path, repos: Sequence[RepoEntry]) -> dict[str, Any]:
    """Describe unique volumes and physical memory; sizes are bytes."""
    volumes = _volumes(home, repos)
    free, total = _memory()
    memory = {"free": free, "total": total, "status": _status(free, total, MEMORY_MIN_FREE)}
    return {
        "volumes": volumes,
        "memory": memory,
        "status": "warning"
        if any(item["status"] == "warning" for item in [*volumes, memory])
        else "ok",
    }


def cleanup(home: Path, repos: Sequence[RepoEntry]) -> dict[str, Any]:
    """Reuse the CLI's safe cleanup, isolating failures between repositories."""
    before = {v["id"]: v["free"] for v in _volumes(home, repos)}
    warnings: list[str] = []
    advice: list[str] = []
    results: list[dict[str, Any]] = []
    try:
        advice = [str(path) for path in adaptive.cleanup_orphans()]
    except Exception as exc:
        warnings.append(f"advice cleanup: {exc}")
    for repo in repos:
        try:
            result = review.clean_worktrees(Path(repo.path))
            results.append({"repo": repo.path, **result.to_json()})
            warnings.extend(f"{repo.path}: {warning}" for warning in result.warnings)
        except Exception as exc:
            warnings.append(f"{repo.path}: {exc}")
    after = _volumes(home, repos)
    deltas = [
        v["free"] - before[v["id"]]
        for v in after
        if v["free"] is not None and before.get(v["id"]) is not None
    ]
    return {
        "advice_directories": advice,
        "repos": results,
        "freed_bytes": sum(deltas) if len(deltas) == len(before) else None,
        "warnings": warnings,
    }
