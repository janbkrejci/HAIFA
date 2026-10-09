"""Distribution: version in one place, wheel contents and the ``$HAIFA_HOME/env`` file."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path

import pytest

from aifactory import __version__
from aifactory.home import env_file, load_env_file

PROJECT = Path(__file__).resolve().parents[1]
PACKAGE = PROJECT / "src" / "aifactory"
REPO_NOTICES = PROJECT.parent / "THIRD_PARTY_NOTICES"


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> zipfile.ZipFile:
    from hatchling.build import build_wheel

    out = tmp_path_factory.mktemp("wheel")
    cwd = os.getcwd()
    os.chdir(PROJECT)
    try:
        name = build_wheel(str(out))
    finally:
        os.chdir(cwd)
    return zipfile.ZipFile(out / name)


def _metadata(wheel: zipfile.ZipFile) -> tuple[str, str]:
    [path] = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
    return path, wheel.read(path).decode("utf-8")


def test_version_only_in_init() -> None:
    project = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in project["project"]
    assert project["project"]["dynamic"] == ["version"]
    assert project["tool"]["hatch"]["version"]["path"] == "src/aifactory/__init__.py"


def test_dependencies_have_upper_bounds() -> None:
    project = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    for dep in project["project"]["dependencies"]:
        assert ">=" in dep and ",<" in dep, dep


def test_wheel_contains_every_package_file(wheel: zipfile.ZipFile) -> None:
    names = set(wheel.namelist())
    expected = {
        "aifactory/" + p.relative_to(PACKAGE).as_posix()
        for p in PACKAGE.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    for needle in (
        "aifactory/web/static/index.html",
        "aifactory/engine/defaults/roles.yaml",
        "aifactory/skill/skill.md",
    ):
        assert needle in expected, needle
    workflows = [n for n in expected if n.startswith("aifactory/defaults/workflows/")]
    agents = [n for n in expected if n.startswith("aifactory/seed/agents/")]
    assert any(n.endswith(".yaml") for n in workflows)
    assert any(n.endswith("/agent.yaml") for n in agents)
    assert sorted(expected - names) == []


def test_wheel_version_matches(wheel: zipfile.ZipFile) -> None:
    _, text = _metadata(wheel)
    assert Parser().parsestr(text)["Version"] == __version__


def test_wheel_has_third_party_notices(wheel: zipfile.ZipFile) -> None:
    local = (PROJECT / "THIRD_PARTY_NOTICES").read_bytes()
    assert local == REPO_NOTICES.read_bytes()
    [path] = [n for n in wheel.namelist() if n.endswith("/THIRD_PARTY_NOTICES")]
    assert ".dist-info/licenses/" in path
    assert wheel.read(path) == local
    _, text = _metadata(wheel)
    assert "THIRD_PARTY_NOTICES" in Parser().parsestr(text).get_all("License-File", [])


def _write_env(home: Path, text: str, mode: int = 0o600) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    path = home / "env"
    path.write_text(text, encoding="utf-8", newline="\n")
    os.chmod(path, mode)
    return path


def test_env_file_loads_without_override(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_env(home, '# comment\nNEW_KEY=new\nKEPT=from-file\nexport QUOTED="a b"\n')
    environ = {"HAIFA_HOME": str(home), "KEPT": "from-env"}
    err = io.StringIO()
    loaded = load_env_file(environ, stderr=err)
    assert sorted(loaded) == ["NEW_KEY", "QUOTED"]
    assert environ["NEW_KEY"] == "new"
    assert environ["KEPT"] == "from-env"
    assert environ["QUOTED"] == "a b"
    assert err.getvalue() == ""
    assert env_file(environ) == home / "env"


def test_env_file_missing_is_noop(tmp_path: Path) -> None:
    environ = {"HAIFA_HOME": str(tmp_path / "none")}
    err = io.StringIO()
    assert load_env_file(environ, stderr=err) == []
    assert environ == {"HAIFA_HOME": str(tmp_path / "none")}
    assert err.getvalue() == ""


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no POSIX file modes")
def test_env_file_wrong_mode_warns_and_loads(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_env(home, "OPEN_KEY=1\n", mode=0o644)
    environ = {"HAIFA_HOME": str(home)}
    err = io.StringIO()
    assert load_env_file(environ, stderr=err) == ["OPEN_KEY"]
    assert environ["OPEN_KEY"] == "1"
    assert "env_file_mode" in err.getvalue()
    assert "0644" in err.getvalue()


def test_factory_loads_env_file(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_env(home, "HAIFA_TEST_FROM_FILE=yes\nHAIFA_TEST_KEPT=file\n", mode=0o640)
    env = {**os.environ, "HAIFA_HOME": str(home), "HAIFA_TEST_KEPT": "env"}
    code = (
        "import os, sys\n"
        "from aifactory.cli import main\n"
        "try:\n"
        "    main(['--version'])\n"
        "except SystemExit:\n"
        "    pass\n"
        "print(os.environ['HAIFA_TEST_FROM_FILE'], os.environ['HAIFA_TEST_KEPT'])\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    assert proc.stdout.strip().endswith("yes env")
    # mode 0640 warns; Windows has no POSIX modes and never warns
    assert ("env_file_mode" in proc.stderr) is (sys.platform != "win32")


def test_engine_utils_import_does_not_load_dotenv() -> None:
    code = (
        "import dotenv\n"
        "calls = []\n"
        "dotenv.load_dotenv = lambda *a, **k: calls.append(1)\n"
        "import aifactory.engine.utils\n"
        "assert calls == [], calls\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
    source = (PACKAGE / "engine" / "utils.py").read_text(encoding="utf-8")
    assert "from dotenv" not in source
