"""The dashboard registry ``dashboard.yaml`` in the HAIFA home (``web/registry.py``)."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from multi_repo import symlink

from aifactory.web.registry import (
    ID_RE,
    Registry,
    RepoError,
    same_repo,
    slugify,
    unique_id,
)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def test_file_modes_and_content(tmp_path: Path) -> None:
    home = tmp_path / "h" / "haifa"
    registry = Registry(home)
    entry, created = registry.add(_dir(tmp_path / "repos" / "web"))
    assert created and entry.id == "web"
    if sys.platform != "win32":  # Windows has no POSIX modes
        assert _mode(home) == 0o700
        assert _mode(home / "dashboard.yaml") == 0o600
    data = yaml.safe_load((home / "dashboard.yaml").read_text(encoding="utf-8"))
    assert data["version"] == 1 and data["port"] == 4700
    assert list(data["repos"][0]) == ["id", "name", "path", "added_at"]
    assert data["repos"][0]["path"] == str(tmp_path.resolve() / "repos" / "web")
    assert not list(home.glob(".dashboard.yaml.*"))  # no temporary file left


_ADD_SCRIPT = """
import sys
from pathlib import Path
from aifactory.web.registry import Registry
registry = Registry(Path(sys.argv[1]))
for n in range(10):
    path = Path(sys.argv[2]) / f"{sys.argv[3]}{n}"
    path.mkdir(parents=True)
    registry.add(path)
"""


def test_concurrent_writes_of_two_processes(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repos = tmp_path / "repos"
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _ADD_SCRIPT, str(home), str(repos), prefix],
            env={**os.environ, "HAIFA_HOME": str(home)},
        )
        for prefix in ("a", "b")
    ]
    assert [p.wait(timeout=60) for p in procs] == [0, 0]
    state, warnings = Registry(home).snapshot()
    assert warnings == []
    assert len(state.repos) == 20
    assert len({e.id for e in state.repos}) == 20
    assert {Path(e.path).name for e in state.repos} == {
        f"{p}{n}" for p in ("a", "b") for n in range(10)
    }


def test_duplicate_through_symlink(tmp_path: Path) -> None:
    real = _dir(tmp_path / "real" / "proj")
    link = tmp_path / "link"
    symlink(link, real)
    registry = Registry(tmp_path / "home")
    first, created = registry.add(real)
    again, created_again = registry.add(link)
    assert created and not created_again
    assert again == first
    assert len(registry.snapshot()[0].repos) == 1
    assert same_repo(link, real)


def test_same_repo_by_inode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = _dir(tmp_path / "proj")
    link = tmp_path / "link"
    symlink(link, real)
    monkeypatch.setattr(os.path, "realpath", lambda p: str(p))  # e.g. case-insensitive names
    assert same_repo(real, link)
    assert not same_repo(real, tmp_path / "missing")


def test_id_collision_and_stable_ids(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "home")
    ids = [registry.add(_dir(tmp_path / x / "web"))[0].id for x in ("a", "b", "c")]
    assert ids == ["web", "web-2", "web-3"]
    assert registry.add(_dir(tmp_path / "inspect"))[0].id == "inspect-2"
    odd = registry.add(_dir(tmp_path / ("Můj Repo!!" * 5)))[0].id
    assert ID_RE.match(odd) and odd.startswith("m-j-repo")
    assert registry.remove("web") is not None
    added = registry.add(_dir(tmp_path / "d" / "web"))[0]
    assert added.id == "web"  # a free id; the others keep theirs
    state = registry.snapshot()[0]
    assert {e.id: Path(e.path).parent.name for e in state.repos if "web" in e.id} == {
        "web-2": "b",
        "web-3": "c",
        "web": "d",
    }


def test_slug_rules() -> None:
    assert slugify("My_Project.v2") == "my-project-v2"
    assert slugify("!!!") == "repo"
    assert len(slugify("x" * 50)) == 32
    long_id = unique_id("y" * 32, {"y" * 32})
    assert long_id == "y" * 30 + "-2" and ID_RE.match(long_id)
    assert unique_id("inspect", set()) == "inspect-2"


def test_unknown_keys_are_kept(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = _dir(tmp_path / "old")
    (home / "dashboard.yaml").write_text(
        "version: 1\nport: 4700\nextra: {a: 1}\nrepos:\n"
        f"  - {{id: old, name: old, path: {repo}, added_at: '2026-01-01T00:00:00+00:00',"
        " color: red}\n",
        encoding="utf-8",
        newline="\n",
    )
    registry = Registry(home)
    registry.add(_dir(tmp_path / "new"))
    registry.set_port(4801)
    data = yaml.safe_load((home / "dashboard.yaml").read_text(encoding="utf-8"))
    assert data["extra"] == {"a": 1}
    assert data["repos"][0]["color"] == "red"
    assert data["port"] == 4801
    assert [r["id"] for r in data["repos"]] == ["old", "new"]


def test_corrupt_file_keeps_last_valid_state(tmp_path: Path) -> None:
    home = tmp_path / "home"
    registry = Registry(home)
    registry.add(_dir(tmp_path / "web"))
    valid, warnings = registry.snapshot()
    assert warnings == [] and len(valid.repos) == 1
    path = home / "dashboard.yaml"
    path.write_text("repos: [\n", encoding="utf-8", newline="\n")
    broken = path.read_bytes()
    state, warnings = registry.snapshot()
    assert state == valid
    assert len(warnings) == 1 and "last valid registry" in warnings[0]
    assert registry.snapshot()[1] == warnings  # repeated while broken
    with pytest.raises(RepoError) as caught:
        registry.add(_dir(tmp_path / "other"))
    assert caught.value.code == "registry_invalid"
    with pytest.raises(RepoError):
        registry.set_port(4800)
    assert path.read_bytes() == broken
    fresh, fresh_warnings = Registry(home).snapshot()
    assert fresh.repos == () and fresh.port == 4700 and len(fresh_warnings) == 1


@pytest.mark.parametrize(
    "text",
    [
        "- a\n",
        "port: true\n",
        "port: 70000\n",
        "repos: {}\n",
        "repos: [{id: Bad, name: x, path: /x, added_at: t}]\n",
        "repos: [{id: a, name: x, path: rel, added_at: t}]\n",
        "repos: [{id: a, name: x, path: /x, added_at: t},\n"
        "  {id: a, name: y, path: /y, added_at: t}]\n",
    ],
)
def test_invalid_contents(tmp_path: Path, text: str) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "dashboard.yaml").write_text(text, encoding="utf-8", newline="\n")
    state, warnings = Registry(home).snapshot()
    assert state.repos == () and len(warnings) == 1


def test_reload_on_external_change(tmp_path: Path) -> None:
    home = tmp_path / "home"
    registry = Registry(home)
    other = Registry(home)
    assert registry.snapshot()[0].repos == ()
    other.add(_dir(tmp_path / "web"))
    assert [e.id for e in registry.snapshot()[0].repos] == ["web"]
    (home / "dashboard.yaml").write_text(
        "version: 1\nport: 4900\nrepos: []\n", encoding="utf-8", newline="\n"
    )
    state = registry.snapshot()[0]
    assert state.port == 4900 and state.repos == ()


def test_remove_unknown_writes_nothing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    registry = Registry(home)
    assert registry.remove("nope") is None
    assert not (home / "dashboard.yaml").exists()
