"""Distribution bundle (``just bundle``): zip contents, checksums, version, ``install.sh``."""

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

PROJECT = Path(__file__).resolve().parents[1]
EXPECTED = {
    f"aifactory-{__version__}-py3-none-any.whl",
    "constraints.txt",
    "install.sh",
    "INSTALL.md",
    "THIRD_PARTY_NOTICES",
    "SHA256SUMS",
}
FAKE_UV = '#!/bin/sh\nprintf "%s\\n" "$*" >> "$UV_LOG"\n'


@pytest.fixture(scope="module")
def bundle_zip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_bundle(tmp_path_factory.mktemp("dist"))


@pytest.fixture
def unpacked(bundle_zip: Path, tmp_path: Path) -> Path:
    with zipfile.ZipFile(bundle_zip) as zf:
        zf.extractall(tmp_path)
    root = tmp_path / f"haifa-{__version__}"
    (root / "install.sh").chmod(0o755)
    return root


def test_zip_name_has_package_version(bundle_zip: Path) -> None:
    assert bundle_zip.name == f"haifa-{__version__}.zip"


def test_zip_holds_only_the_bundle_files(bundle_zip: Path) -> None:
    with zipfile.ZipFile(bundle_zip) as zf:
        names = zf.namelist()
        mode = zf.getinfo(f"haifa-{__version__}/install.sh").external_attr >> 16
    assert sorted(names) == sorted(f"haifa-{__version__}/{n}" for n in EXPECTED)
    assert mode & 0o111


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
    assert f"haifa-{__version__}.zip" in doc
    for needle in ("./install.sh", "factory check", "factory upgrade"):
        assert needle in doc
    assert "@VERSION@" not in doc


def test_install_sh_parses(unpacked: Path) -> None:
    subprocess.run(["bash", "-n", str(unpacked / "install.sh")], check=True)


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


def test_install_sh_runs_uv_tool_install(unpacked: Path, tmp_path: Path) -> None:
    log = tmp_path / "uv.log"
    env = {
        **os.environ,
        "PATH": f"{_fake_uv_bin(tmp_path)}{os.pathsep}{os.environ['PATH']}",
        "UV_LOG": str(log),
    }
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
        f"tool install --force {wheel} --constraints constraints.txt\n"
    )
    assert "factory check" in proc.stdout


def test_install_sh_runs_from_another_directory(unpacked: Path, tmp_path: Path) -> None:
    log = tmp_path / "uv.log"
    env = {
        **os.environ,
        "PATH": f"{_fake_uv_bin(tmp_path)}{os.pathsep}{os.environ['PATH']}",
        "UV_LOG": str(log),
    }
    subprocess.run(
        _install_sh(str(unpacked / "install.sh")),
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
    )
    assert log.read_text("utf-8").startswith("tool install --force ")


def test_install_sh_rejects_bad_checksum(unpacked: Path, tmp_path: Path) -> None:
    (unpacked / "constraints.txt").write_text("evil==1\n", encoding="utf-8", newline="\n")
    log = tmp_path / "uv.log"
    env = {
        **os.environ,
        "PATH": f"{_fake_uv_bin(tmp_path)}{os.pathsep}{os.environ['PATH']}",
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
