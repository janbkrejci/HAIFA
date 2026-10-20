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
  workers as logical CPUs on POSIX, one per CPU (at most eight) on Windows.
- Approve and auto-merge read CI checks without waiting for them (`review.ci` limits 0).
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
    """Respect the override; Windows avoids oversubscribing CPUs and child processes.

    On four Windows CPUs the web suite took 339 s with six workers and 348 s
    with four. Four saves about 200 MB of worker memory for 3% more wall time.
    POSIX keeps 1.5x CPUs for tests waiting on git and CLI subprocesses.
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
    cpus = os.cpu_count() or 2
    return min(cpus, 8) if sys.platform == "win32" else max(2, cpus * 3 // 2)


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


@pytest.fixture(autouse=True)
def _no_ci_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Approve reads a hosting's CI checks as they are (``review.ci``); no test waits 90 s."""
    from aifactory.review import ci

    monkeypatch.setattr(ci, "AUTO_MERGE_CHECKS_TIMEOUT", 0.0)
    monkeypatch.setattr(ci, "AUTO_MERGE_CHECKS_APPEAR", 0.0)


@pytest.fixture(autouse=True)
def _no_pi_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test asks the operator's pi which packages register which providers."""
    from aifactory.engine import agent_pi

    monkeypatch.setattr(agent_pi, "_package_extensions", lambda: {})


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
    _real_haifa_snapshot: Snapshot,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Path]:
    home = tmp_path_factory.mktemp("haifa-home")
    monkeypatch.setenv(haifa_home_module.HOME_ENV, str(home))
    yield home
    after = _snapshot(_real_haifa_home)
    assert after == _real_haifa_snapshot, f"the real HAIFA home {_real_haifa_home} changed"


@pytest.fixture(scope="session")
def _real_haifa_snapshot(_real_haifa_home: Path) -> Snapshot:
    """One baseline per worker; every test still checks for writes at teardown.

    The real home must stay unchanged throughout the session. Scanning it again
    before every test doubles the I/O and would accept a previous test's leak as
    the next test's baseline.
    """
    return _snapshot(_real_haifa_home)
