"""Session-wide speedups for the whole suite; no test behaviour changes.

- On macOS `/usr/bin/git` is an xcrun shim (~40 ms per call); the same git is put
  first on PATH directly. Subprocesses (CLI runs, validation workers) inherit it.
- A global git config that keeps the operator's settings but turns off automatic
  git maintenance/gc after commits, merges and pushes (Windows: no CRLF on checkout).
- Windows: child Pythons (fake gh, az, harnesses) write UTF-8 like the real programs, and
  Git for Windows' bin/ (sh, bash) is on PATH as under `just`.
- Windows: pytest platform metadata uses Python's environment/WinAPI fallback instead
  of optional WMI queries, which can stall or exhaust COM resources in xdist workers.
- The app and engine modules are imported once, not inside the first test.
- `-n auto` respects PYTEST_XDIST_AUTO_NUM_WORKERS; otherwise starts 1.5x as many
  workers as logical CPUs, capped at eight on Windows to limit subprocess pressure.
- Every test gets `HAIFA_HOME` pointing at a temporary directory (the dashboard writes
  the logs of its run processes there) and fails when the real HAIFA home changed. Logs
  of other processes (a dashboard the operator runs meanwhile) are ignored: the launcher
  puts the server's pid into every log name.
"""

from __future__ import annotations

import importlib
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NoReturn

import pytest

import repo_templates
from aifactory import home as haifa_home_module
from tiers import BROWSER_FILES, SLOW_FILES

# Keep git from spawning background housekeeping after commits, merges and pushes.
_GIT_QUIET_CONFIG = """\
[maintenance]
\tauto = false
[gc]
\tauto = 0
[receive]
\tautogc = false
"""
# Git for Windows sets core.autocrlf=true system-wide: checkouts would get CRLF while the
# tests (as on POSIX) expect the bytes of the blob. `input` checks out what was committed
# and still turns the CRLF that Python writes on Windows into LF on commit.
_GIT_WINDOWS_CONFIG = "[core]\n\tautocrlf = input\n" if sys.platform == "win32" else ""


def _quiet_git_config(directory: Path) -> Path:
    """A global git config that keeps the operator's settings and adds _GIT_QUIET_CONFIG.

    It goes through GIT_CONFIG_GLOBAL rather than GIT_CONFIG_COUNT because git clears
    the latter for the receiving side of a local push, which would still run `gc --auto`.
    """
    included = os.environ.get("GIT_CONFIG_GLOBAL")
    if included:
        paths = [Path(included)]
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        paths = [Path(xdg) / "git" / "config", Path.home() / ".gitconfig"]
    includes = "".join(f"[include]\n\tpath = {path.as_posix()}\n" for path in paths)
    config = directory / "gitconfig"
    config.write_text(
        includes + _GIT_QUIET_CONFIG + _GIT_WINDOWS_CONFIG, encoding="utf-8", newline="\n"
    )
    return config


def _direct_git() -> str | None:
    """The real git behind the macOS xcrun shim `/usr/bin/git`, or None."""
    if sys.platform != "darwin":
        return None
    found = shutil.which("git")
    if found is None or os.path.realpath(found) != "/usr/bin/git":
        return None
    try:
        probe = subprocess.run(
            ["xcrun", "--find", "git"],
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )
    except OSError:
        return None
    real = probe.stdout.strip()
    if probe.returncode != 0 or not real or not os.access(real, os.X_OK):
        return None
    if os.path.realpath(real) == "/usr/bin/git":
        return None
    return real


def _git_bash_bin() -> str | None:
    """Windows: Git for Windows' bin/ (sh, bash) when sh is not on PATH yet, else None.

    `just` runs the suite with it on PATH (justfile); a bare `pytest` gets the same, since
    sandbox justfiles and install.sh need sh and bash.
    """
    found = shutil.which("sh")
    if found is not None:
        return None
    git = shutil.which("git")
    if git is None:
        return None
    bin_dir = Path(git).resolve().parent.parent / "bin"  # <Git>/cmd/git.exe
    return str(bin_dir) if (bin_dir / "sh.exe").is_file() else None


def _warm_imports() -> None:
    """Import the app and the engine once per session (only imports, no registration)."""
    for module in (
        "aifactory.cli",
        "aifactory.run",
        "aifactory.workflow",
        "aifactory.engine.data_types",
        "aifactory.engine.agents",
        "aifactory.engine.runner",
    ):
        importlib.import_module(module)


# Test tiers: tests/tiers.py lists the slow and browser files.


def _unavailable_wmi(*args: str) -> NoReturn:
    """Let platform use its built-in fallback without invoking Windows COM."""
    raise OSError("WMI disabled in pytest; use platform's environment/WinAPI fallback")


def pytest_configure(config: pytest.Config) -> None:
    # xdist calls platform.platform() in sessionstart, before session fixtures.
    # CPython 3.12+ optionally queries WMI for metadata; older Pythons need no patch.
    # Limit this to the pytest process and restore the optional backend on cleanup.
    if sys.platform == "win32" and hasattr(platform, "_wmi_query"):
        patch = pytest.MonkeyPatch()
        patch.setattr(platform, "_wmi_query", _unavailable_wmi)
        config.add_cleanup(patch.undo)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        rel = item.path.relative_to(config.rootpath).as_posix()
        if rel in SLOW_FILES:
            item.add_marker(pytest.mark.slow)
        if rel in BROWSER_FILES:
            item.add_marker(pytest.mark.browser)


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    """Respect the xdist override; otherwise use 1.5x CPUs (Windows: at most eight).

    The tests mostly wait for git and CLI subprocesses (and their I/O), so a few more
    workers than CPUs finish sooner (measured: 6 workers on 4 logical CPUs 133 s, 4
    workers 160 s).
    """
    override = os.environ.get("PYTEST_XDIST_AUTO_NUM_WORKERS")
    if override:
        try:
            workers = int(override)
        except ValueError as exc:
            raise pytest.UsageError(
                "PYTEST_XDIST_AUTO_NUM_WORKERS must be a nonnegative integer"
            ) from exc
        if workers < 0:
            raise pytest.UsageError("PYTEST_XDIST_AUTO_NUM_WORKERS must be a nonnegative integer")
        return workers
    workers = max(2, (os.cpu_count() or 2) * 3 // 2)
    return min(workers, 8) if sys.platform == "win32" else workers


@pytest.fixture(scope="session", autouse=True)
def _fast_test_env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    with pytest.MonkeyPatch.context() as mp:
        real_git = _direct_git()
        if real_git is not None:
            bin_dir = tmp_path_factory.mktemp("gitbin")
            (bin_dir / "git").symlink_to(real_git)
            mp.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
        mp.setenv("GIT_CONFIG_GLOBAL", str(_quiet_git_config(tmp_path_factory.mktemp("gitcfg"))))
        if sys.platform == "win32":
            mp.setenv("PYTHONUTF8", "1")
            git_bin = _git_bash_bin()
            if git_bin is not None:
                mp.setenv("PATH", f"{git_bin}{os.pathsep}{os.environ.get('PATH', '')}")
        repo_templates.enable(tmp_path_factory.mktemp("repo-templates"))
        _warm_imports()
        yield


Snapshot = dict[str, tuple[int, int]]


@pytest.fixture(scope="session")
def _real_haifa_home() -> Path:
    """The operator's HAIFA home, taken before any test changes the environment."""
    return haifa_home_module.haifa_home()


def _snapshot(root: Path) -> Snapshot:
    """(size, mtime) of the files under `root` this process could have written."""
    if not root.is_dir():
        return {}
    mine = f"-{os.getpid()}-"
    result: Snapshot = {}
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            path = Path(dirpath) / name
            rel = path.relative_to(root)
            # logs and test_slots are shared with every factory run on the machine:
            # other processes add log files and slot-queue tickets while tests run
            if rel.parts[0] in ("logs", "test_slots") and mine not in name:
                continue
            try:
                stat = path.lstat()
            except OSError:
                continue
            result[str(rel)] = (stat.st_size, stat.st_mtime_ns)
    return result


@pytest.fixture(autouse=True)
def _haifa_home(
    _real_haifa_home: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Path]:
    home = tmp_path_factory.mktemp("haifa-home")
    monkeypatch.setenv(haifa_home_module.HOME_ENV, str(home))
    before = _snapshot(_real_haifa_home)
    yield home
    after = _snapshot(_real_haifa_home)
    assert after == before, f"the real HAIFA home {_real_haifa_home} changed"
