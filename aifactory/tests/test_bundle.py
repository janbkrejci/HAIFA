"""Distribution bundle (``just bundle``): zip contents, checksums, version, the installers."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest
from bundle.build import build_bundle, constraints

from aifactory import __version__
from fake_exe import make_executable


def _system_path() -> str:
    # A source installation's giro must not be mistaken for the fake uv's tool.
    return os.pathsep.join(
        part
        for part in os.environ["PATH"].split(os.pathsep)
        if not any((Path(part) / name).is_file() for name in ("giro", "giro.exe"))
    )


PROJECT = Path(__file__).resolve().parents[1]
EXPECTED = {
    f"aifactory-{__version__}-py3-none-any.whl",
    "constraints.txt",
    "install.sh",
    "install.bat",
    "install.ps1",
    "uninstall.sh",
    "uninstall.bat",
    "uninstall.ps1",
    "INSTALL.md",
    "THIRD_PARTY_NOTICES",
    "SHA256SUMS",
}
FAKE_UV = (
    '#!/bin/sh\nprintf "%s\\n" "$*" >> "$UV_LOG"\n'
    'if [ "$1 $2" = "tool list" ]; then echo "aifactory v0.1.0"; fi\n'
    'if [ "$1 $2 $3" = "tool dir --bin" ] && [ -n "${FACTORY_BIN:-}" ]; then '
    'echo "$FACTORY_BIN"; fi\n'
)
# A fake factory for install.sh: logs its arguments; the library is missing unless
# $FAKE_LIBRARY is "ok"; `library seed` exits with $FAKE_SEED_EXIT (default 0).
FAKE_FACTORY = (
    '#!/bin/sh\nprintf "%s\\n" "$*" >> "$FACTORY_LOG"\n'
    'if [ "$1 $2" = "library status" ]; then\n'
    '  if [ "${FAKE_LIBRARY:-}" = "ok" ]; then echo \'{"ok": true, "data": {}}\'; exit 0; fi\n'
    '  echo \'{"ok": false, "error": {"code": "library_missing", "message": "no"}}\'; exit 2\n'
    "fi\n"
    'if [ "$1 $2" = "library seed" ]; then exit "${FAKE_SEED_EXIT:-0}"; fi\n'
)


@pytest.fixture(scope="module")
def bundle_zip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_bundle(tmp_path_factory.mktemp("dist"))


@pytest.fixture
def unpacked(bundle_zip: Path, tmp_path: Path) -> Path:
    with zipfile.ZipFile(bundle_zip) as zf:
        zf.extractall(tmp_path)
    root = tmp_path / f"giro-{__version__}"
    for script in ("install.sh", "uninstall.sh"):
        (root / script).chmod(0o755)
    return root


def test_zip_name_has_package_version(bundle_zip: Path) -> None:
    assert bundle_zip.name == f"giro-{__version__}.zip"


def test_zip_holds_only_the_bundle_files(bundle_zip: Path) -> None:
    with zipfile.ZipFile(bundle_zip) as zf:
        names = zf.namelist()
        modes = [
            zf.getinfo(f"giro-{__version__}/{script}").external_attr >> 16
            for script in ("install.sh", "uninstall.sh")
        ]
    assert sorted(names) == sorted(f"giro-{__version__}/{n}" for n in EXPECTED)
    assert all(mode & 0o111 for mode in modes)


def test_checksums_cover_every_other_file(unpacked: Path) -> None:
    lines = (unpacked / "SHA256SUMS").read_text("utf-8").splitlines()
    sums: dict[str, str] = {}
    for line in lines:
        digest, name = line.split("  ", 1)
        sums[name] = digest
    assert set(sums) == EXPECTED - {"SHA256SUMS"}
    for name, digest in sums.items():
        assert hashlib.sha256((unpacked / name).read_bytes()).hexdigest() == digest, name


def test_wheel_in_bundle_is_clean(unpacked: Path) -> None:
    with zipfile.ZipFile(unpacked / f"aifactory-{__version__}-py3-none-any.whl") as wheel:
        names = wheel.namelist()
    assert "aifactory/web/static/index.html" in names
    for name in names:
        assert "__pycache__" not in name and not name.endswith((".pyc", ".env")), name


def test_constraints_pin_runtime_dependencies_from_lock(unpacked: Path) -> None:
    lock = tomllib.loads((PROJECT / "uv.lock").read_text("utf-8"))
    locked = {p["name"]: p.get("version") for p in lock["package"]}
    text = (unpacked / "constraints.txt").read_text("utf-8")
    assert text == constraints(PROJECT / "uv.lock")
    pins = dict(line.split("==") for line in text.splitlines())
    for name in (
        "pydantic",
        "python-dotenv",
        "pyyaml",
        "rich",
        "ruamel-yaml",
        "starlette",
        "uvicorn",
    ):
        assert pins[name] == locked[name]
    for name, ver in pins.items():
        assert locked[name] == ver
    for dev_only in ("pytest", "mypy", "ruff", "hatchling", "playwright", "aifactory"):
        assert dev_only not in pins


def test_install_docs_are_versioned(unpacked: Path) -> None:
    doc = (unpacked / "INSTALL.md").read_text("utf-8")
    assert f"giro-{__version__}.zip" in doc
    for needle in ("./install.sh", "install.bat", "giro check", "giro upgrade"):
        assert needle in doc
    assert "@VERSION@" not in doc


@pytest.mark.parametrize("script", ["install.sh", "uninstall.sh"])
def test_shell_scripts_parse(unpacked: Path, script: str) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    subprocess.run([bash, "-n", str(unpacked / script)], check=True)


def _install_sh(path: str) -> list[str]:
    """The command running ``install.sh``: Windows runs no shebang script, so through bash."""
    if sys.platform == "win32":
        bash = shutil.which("bash")
        assert bash is not None
        return [bash, path]
    return [path]


def _fake_uv_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(FAKE_UV, encoding="utf-8", newline="\n")
    make_executable(uv)
    return bin_dir


def _fake_factory_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "tools"
    bin_dir.mkdir()
    factory = bin_dir / "giro"
    factory.write_text(FAKE_FACTORY, encoding="utf-8", newline="\n")
    make_executable(factory)
    return bin_dir


@pytest.mark.parametrize(("library", "seed_exit"), [("missing", 0), ("ok", 0), ("ok", 1)])
def test_install_sh_clones_a_missing_library_and_refreshes_it(
    unpacked: Path, tmp_path: Path, library: str, seed_exit: int
) -> None:
    log = tmp_path / "factory.log"
    env = {
        **os.environ,
        "PATH": f"{_fake_uv_bin(tmp_path)}{os.pathsep}{_system_path()}",
        "UV_LOG": str(tmp_path / "uv.log"),
        "FACTORY_BIN": str(_fake_factory_bin(tmp_path)),
        "FACTORY_LOG": str(log),
        "FAKE_LIBRARY": library,
        "FAKE_SEED_EXIT": str(seed_exit),
    }
    proc = subprocess.run(
        _install_sh("./install.sh"),
        cwd=unpacked,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = log.read_text("utf-8").splitlines()
    if library == "missing":
        assert calls == [
            "library status --json",
            "library clone --seed-fallback",
            "library seed",
        ]
    else:
        assert calls == ["library status --json", "library seed"]
    assert f"Refreshing the library to GIRO {__version__}" in proc.stdout
    refused = "the library was not refreshed; run: giro library seed"
    assert (refused in proc.stderr) == bool(seed_exit)
    assert "installed" in proc.stdout  # a failed refresh does not stop the install


def test_install_sh_runs_uv_tool_install(unpacked: Path, tmp_path: Path) -> None:
    log = tmp_path / "uv.log"
    env = {
        **os.environ,
        "PATH": f"{_fake_uv_bin(tmp_path)}{os.pathsep}{_system_path()}",
        "UV_LOG": str(log),
    }
    env.pop("FACTORY_BIN", None)
    proc = subprocess.run(
        _install_sh("./install.sh"),
        cwd=unpacked,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    wheel = f"aifactory-{__version__}-py3-none-any.whl"
    assert log.read_text("utf-8") == (
        f"tool dir --bin\ntool install --force {wheel} --constraints constraints.txt\n"
        "tool dir --bin\n"
    )
    assert "giro check" in proc.stdout
    assert "giro library clone --seed-fallback" in proc.stderr


def test_install_sh_runs_from_another_directory(unpacked: Path, tmp_path: Path) -> None:
    log = tmp_path / "uv.log"
    env = {
        **os.environ,
        "PATH": f"{_fake_uv_bin(tmp_path)}{os.pathsep}{_system_path()}",
        "UV_LOG": str(log),
    }
    subprocess.run(
        _install_sh(str(unpacked / "install.sh")),
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )
    assert "tool install --force " in log.read_text("utf-8")


def test_install_sh_rejects_bad_checksum(unpacked: Path, tmp_path: Path) -> None:
    (unpacked / "constraints.txt").write_text("evil==1\n", encoding="utf-8", newline="\n")
    log = tmp_path / "uv.log"
    env = {
        **os.environ,
        "PATH": f"{_fake_uv_bin(tmp_path)}{os.pathsep}{_system_path()}",
        "UV_LOG": str(log),
    }
    proc = subprocess.run(_install_sh("./install.sh"), cwd=unpacked, env=env, capture_output=True)
    assert proc.returncode != 0
    assert not log.exists()


def test_install_sh_without_uv_explains_and_fails(unpacked: Path, tmp_path: Path) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = subprocess.run(
        [bash, str(unpacked / "install.sh")],
        cwd=unpacked,
        env={"PATH": str(empty)},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode != 0
    assert "uv is not on PATH" in proc.stderr
    assert "astral.sh/uv" in proc.stderr


# -- Windows: install.bat and install.ps1 --

WIN_TOOLS = ("git", "uv", "gh", "node", "npm", "claude", "codex", "winget")
# A fake tool: appends "<name> <args>" to $FAKE_LOG; git knows the identity, uv the bin
# directory, factory the library state (`library seed` exits with $FAKE_SEED_EXIT); winget
# and npm "install" a tool by copying it from $FAKE_STASH into the bin directory.
FAKE_TOOL = """#!/usr/bin/env python3
import json, os, shutil, sys
name, args = {name!r}, sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
    log.write(" ".join([name, *args]) + "\\n")
installs = {{"Git.Git": "git", "astral-sh.uv": "uv", "GitHub.cli": "gh",
    "OpenJS.NodeJS.LTS": "node", "@anthropic-ai/claude-code": "claude", "@openai/codex": "codex"}}
if name in ("winget", "npm") and args[:1] == ["install"]:
    tool = installs[args[args.index("--id") + 1] if "--id" in args else args[-1]]
    shutil.copy(os.path.join(os.environ["FAKE_STASH"], tool + ".exe"), os.environ["FAKE_BIN"])
elif name == "git" and args[:2] == ["config", "--get"]:
    print("Test User" if args[2] == "user.name" else "test@example.com")
elif name == "uv" and args[:2] == ["tool", "list"]:
    print("aifactory v1.0.0\\n- factory\\n- giro")
elif name == "uv" and args[:3] == ["tool", "dir", "--bin"]:
    print(os.environ["FAKE_BIN"])
elif name == "giro" and args == ["--data-home"]:
    print(os.environ.get("GIRO_HOME") or os.environ["HAIFA_HOME"])
elif name == "giro" and args[:2] == ["library", "status"]:
    if os.environ["FAKE_LIBRARY"] == "missing":
        print(json.dumps({{"ok": False, "error": {{"code": "library_missing", "message": "no"}}}}))
        sys.exit(2)
    print(json.dumps({{"ok": True, "data": {{}}}}))
elif name == "giro" and args[:2] == ["library", "seed"]:
    sys.exit(int(os.environ.get("FAKE_SEED_EXIT", "0")))
"""
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 runs on Windows")


def _fake_tool(directory: Path, name: str) -> None:
    path = directory / name
    path.write_text(FAKE_TOOL.format(name=name), encoding="utf-8", newline="\n")
    make_executable(path)


def _windows_env(
    tmp_path: Path, missing: tuple[str, ...] = (), library: str = "ok", seed_exit: int = 0
) -> dict[str, str]:
    """Fakes of every tool and factory in bin/, the `missing` ones only in stash/."""
    bin_dir, stash = tmp_path / "bin", tmp_path / "stash"
    bin_dir.mkdir()
    stash.mkdir()
    for name in (*WIN_TOOLS, "giro"):
        _fake_tool(stash if name in missing else bin_dir, name)
    root = os.environ.get("SystemRoot", r"C:\Windows")
    path = [str(bin_dir), rf"{root}\System32", rf"{root}\System32\WindowsPowerShell\v1.0"]
    return {
        **os.environ,
        "PATH": os.pathsep.join(path),
        "FAKE_LOG": str(tmp_path / "tools.log"),
        "FAKE_BIN": str(bin_dir),
        "FAKE_STASH": str(stash),
        "FAKE_LIBRARY": library,
        "FAKE_SEED_EXIT": str(seed_exit),
    }


def _log(env: dict[str, str]) -> list[str]:
    log = Path(env["FAKE_LOG"])
    return log.read_text("utf-8").splitlines() if log.exists() else []


def _install_ps1(unpacked: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("powershell")
    assert powershell is not None
    script = str(unpacked / "install.ps1")
    return subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
        cwd=unpacked.parent,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _install_commands(log: list[str]) -> list[str]:
    """The log without the dependency and identity probes."""
    return [
        line
        for line in log
        if not line.startswith(("git config --get", "uv tool dir", "uv tool list"))
    ]


def test_windows_installers_are_versioned(unpacked: Path) -> None:
    bat = (unpacked / "install.bat").read_bytes()
    assert bat.count(b"\r\n") == bat.count(b"\n") > 0
    assert b"install.ps1" in bat
    ps1 = (unpacked / "install.ps1").read_bytes()
    assert ps1.isascii()
    text = ps1.decode()
    assert f"'aifactory-{__version__}-py3-none-any.whl'" in text
    assert "@VERSION@" not in text and "@WHEEL@" not in text


@windows_only
@pytest.mark.parametrize("seed_exit", [0, 1])
def test_install_ps1_on_a_ready_machine_installs_factory_and_refreshes_the_library(
    unpacked: Path, tmp_path: Path, seed_exit: int
) -> None:
    env = _windows_env(tmp_path, seed_exit=seed_exit)
    proc = _install_ps1(unpacked, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    wheel = f"aifactory-{__version__}-py3-none-any.whl"
    assert _install_commands(_log(env)) == [
        f"uv tool install --force {wheel} --constraints constraints.txt",
        "uv tool update-shell",
        "giro library status --json",
        "giro library seed",
    ]
    assert "giro check" in proc.stdout
    assert ("the library was not refreshed" in proc.stdout + proc.stderr) == bool(seed_exit)


@windows_only
def test_install_ps1_installs_missing_tools_and_creates_the_library(
    unpacked: Path, tmp_path: Path
) -> None:
    env = _windows_env(tmp_path, missing=("gh", "codex"), library="missing")
    proc = _install_ps1(unpacked, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    log = _install_commands(_log(env))
    assert log[:2] == [
        "winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements",
        "npm install -g @openai/codex",
    ]
    assert log[-3:] == [
        "giro library status --json",
        "giro library clone --seed-fallback",
        "giro library seed",
    ]


@windows_only
def test_install_ps1_without_winget_explains_and_fails(unpacked: Path, tmp_path: Path) -> None:
    env = _windows_env(tmp_path, missing=("git", "winget"))
    proc = _install_ps1(unpacked, env)
    assert proc.returncode != 0
    assert "winget is not available" in proc.stdout
    assert not any(line.startswith("uv tool install") for line in _log(env))


@windows_only
def test_install_ps1_rejects_bad_checksum(unpacked: Path, tmp_path: Path) -> None:
    (unpacked / "constraints.txt").write_text("evil==1\n", encoding="utf-8", newline="\n")
    env = _windows_env(tmp_path, missing=("gh",))
    proc = _install_ps1(unpacked, env)
    assert proc.returncode != 0
    assert "constraints.txt does not match" in proc.stdout
    assert _log(env) == []


@windows_only
def test_install_bat_runs_install_ps1_and_passes_its_exit_code(
    unpacked: Path, tmp_path: Path
) -> None:
    env = _windows_env(tmp_path)
    cmd = shutil.which("cmd", path=env["PATH"])
    assert cmd is not None
    ok = subprocess.run(
        [cmd, "/c", str(unpacked / "install.bat")],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "giro library status --json" in _log(env)
    (unpacked / "constraints.txt").write_text("evil==1\n", encoding="utf-8", newline="\n")
    bad = subprocess.run(
        [cmd, "/c", str(unpacked / "install.bat")],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
    )
    assert bad.returncode == 1


# -- uninstall --


def _haifa_home(tmp_path: Path) -> Path:
    home = tmp_path / "haifa-home"
    (home / "library").mkdir(parents=True)
    (home / "env").write_text("X=1\n", encoding="utf-8")
    return home


@pytest.mark.parametrize(
    ("args", "kept"), [(["--purge"], False), (["--keep-data"], True), ([], True)]
)
def test_uninstall_sh_removes_factory_and_data_on_request(
    unpacked: Path, tmp_path: Path, args: list[str], kept: bool
) -> None:
    home = _haifa_home(tmp_path)
    log = tmp_path / "uv.log"
    env = {
        **os.environ,
        "PATH": f"{_fake_uv_bin(tmp_path)}{os.pathsep}{_system_path()}",
        "UV_LOG": str(log),
        "HAIFA_HOME": str(home),
    }
    proc = subprocess.run(
        [*_install_sh(str(unpacked / "uninstall.sh")), *args],
        cwd=tmp_path,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert log.read_text("utf-8").splitlines() == [
        "tool dir --bin",
        "tool list",
        "tool uninstall aifactory",
    ]
    assert home.exists() is kept


def _uninstall_ps1(
    unpacked: Path, env: dict[str, str], *args: str
) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("powershell")
    assert powershell is not None
    script = str(unpacked / "uninstall.ps1")
    return subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, *args],
        cwd=unpacked.parent,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@windows_only
@pytest.mark.parametrize(("args", "kept"), [(["-Purge"], False), (["-KeepData"], True)])
def test_uninstall_ps1_removes_factory_and_data_on_request(
    unpacked: Path, tmp_path: Path, args: list[str], kept: bool
) -> None:
    home = _haifa_home(tmp_path)
    env = {**_windows_env(tmp_path), "HAIFA_HOME": str(home)}
    proc = _uninstall_ps1(unpacked, env, *args)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _log(env) == [
        "uv tool dir --bin",
        "giro --data-home",
        "uv tool list",
        "uv tool uninstall aifactory",
    ]
    assert home.exists() is kept


@windows_only
def test_uninstall_bat_without_an_answer_keeps_the_data(unpacked: Path, tmp_path: Path) -> None:
    home = _haifa_home(tmp_path)
    env = {**_windows_env(tmp_path), "HAIFA_HOME": str(home)}
    cmd = shutil.which("cmd", path=env["PATH"])
    assert cmd is not None
    proc = subprocess.run(
        [cmd, "/c", str(unpacked / "uninstall.bat")],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "uv tool uninstall aifactory" in _log(env)
    assert home.exists()


def test_install_sh_refuses_an_unrelated_giro_before_installing(
    unpacked: Path, tmp_path: Path
) -> None:
    fake_bin = _fake_uv_bin(tmp_path)
    collision = fake_bin / "giro"
    collision.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    make_executable(collision)
    log = tmp_path / "uv.log"
    proc = subprocess.run(
        _install_sh(str(unpacked / "install.sh")),
        env={**os.environ, "PATH": f"{fake_bin}{os.pathsep}{_system_path()}", "UV_LOG": str(log)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "giro already exists" in proc.stderr
    assert "tool install" not in log.read_text()


def test_uninstall_sh_protects_a_migration_before_removing_software(
    unpacked: Path, tmp_path: Path
) -> None:
    home = _haifa_home(tmp_path)
    (home / "giro-migration.json").write_text('{"state":"prepared"}')
    log = tmp_path / "uv.log"
    env = {
        **os.environ,
        "HAIFA_HOME": str(home),
        "PATH": f"{_fake_uv_bin(tmp_path)}{os.pathsep}{_system_path()}",
        "UV_LOG": str(log),
    }
    proc = subprocess.run(
        [*_install_sh(str(unpacked / "uninstall.sh")), "--purge"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert (home / "env").exists()
    assert "tool uninstall" not in log.read_text()
