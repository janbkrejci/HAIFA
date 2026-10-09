"""Choosing a folder: ``/api/fs/dirs`` under home and the native dialog of ``/api/fs/pick``.

The dialogs are fake ``osascript`` and ``zenity`` scripts on a private ``PATH``; nothing
opens a real window, calls a model or the network.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from multi_repo import multi_client, symlink
from starlette.testclient import TestClient

from aifactory.skill import envelope_problems
from aifactory.skill.codes import ERROR_CODES
from aifactory.web import fs
from aifactory.web.fs import FolderPicker
from fake_exe import make_executable

SAME_ORIGIN = {"Origin": "http://127.0.0.1:4700", "Sec-Fetch-Site": "same-origin"}


def _check(response: Any, status: int) -> Any:
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def _fake(bin_dir: Path, name: str, body: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / name
    path.write_text("#!/bin/sh\nPATH=/usr/bin:/bin\n" + body, encoding="utf-8", newline="\n")
    make_executable(path)


def _env(bin_dir: Path, **extra: str) -> dict[str, str]:
    # Only the fakes: a real osascript, zenity or kdialog must never be found.
    return {"PATH": str(bin_dir), "HOME": str(bin_dir.parent), **extra}


@pytest.fixture
def user_home(tmp_path: Path) -> Path:
    home = tmp_path / "user"
    home.mkdir()
    return home.resolve()


def _client(tmp_path: Path, user_home: Path, picker: FolderPicker | None = None) -> TestClient:
    if picker is None:
        picker = FolderPicker(platform="darwin", env=_env(tmp_path / "empty-bin"))
    return multi_client(tmp_path / "haifa", tmp_path, user_home=user_home, picker=picker)


# ── /api/fs/dirs ──────────────────────────────────────────────────────────────────


def test_dirs_lists_home_by_default(tmp_path: Path, user_home: Path) -> None:
    (user_home / "repo" / ".git").mkdir(parents=True)
    (user_home / "onboarded" / ".git").mkdir(parents=True)
    (user_home / "onboarded" / ".factory").mkdir()
    (user_home / "plain").mkdir()
    (user_home / ".hidden").mkdir()
    (user_home / "file.txt").write_text("x", encoding="utf-8", newline="\n")
    client = _client(tmp_path, user_home)
    data = _check(client.get("/api/fs/dirs"), 200)["data"]
    assert data["path"] == str(user_home)
    assert data["parent"] is None
    assert data["truncated"] is False
    assert data["entries"] == [
        {
            "name": "onboarded",
            "path": str(user_home / "onboarded"),
            "is_git": True,
            "has_factory": True,
        },
        {"name": "plain", "path": str(user_home / "plain"), "is_git": False, "has_factory": False},
        {"name": "repo", "path": str(user_home / "repo"), "is_git": True, "has_factory": False},
    ]


def test_dirs_subfolder_has_parent(tmp_path: Path, user_home: Path) -> None:
    (user_home / "a" / "b").mkdir(parents=True)
    client = _client(tmp_path, user_home)
    data = _check(client.get("/api/fs/dirs", params={"path": str(user_home / "a")}), 200)["data"]
    assert data["parent"] == str(user_home)
    assert [e["name"] for e in data["entries"]] == ["b"]


def test_dirs_limit(tmp_path: Path, user_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fs, "MAX_ENTRIES", 5)
    for i in range(8):
        (user_home / f"d{i}").mkdir()
    client = _client(tmp_path, user_home)
    data = _check(client.get("/api/fs/dirs"), 200)["data"]
    assert [e["name"] for e in data["entries"]] == [f"d{i}" for i in range(5)]
    assert data["truncated"] is True


def test_dirs_limit_is_500(tmp_path: Path, user_home: Path) -> None:
    for i in range(501):
        (user_home / f"d{i:03}").mkdir()
    client = _client(tmp_path, user_home)
    data = _check(client.get("/api/fs/dirs"), 200)["data"]
    assert len(data["entries"]) == 500
    assert data["truncated"] is True


def test_dirs_outside_home(tmp_path: Path, user_home: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    client = _client(tmp_path, user_home)
    for path in (str(outside), str(user_home / ".."), os.path.abspath(os.sep)):  # / or C:\
        body = _check(client.get("/api/fs/dirs", params={"path": path}), 403)
        assert body["error"]["code"] == "outside_home"


def test_dirs_symlink_out_of_home(tmp_path: Path, user_home: Path) -> None:
    outside = tmp_path / "outside"
    (outside / "secret").mkdir(parents=True)
    symlink(user_home / "escape", outside)
    (user_home / "inner").mkdir()
    symlink(user_home / "alias", user_home / "inner")
    client = _client(tmp_path, user_home)
    body = _check(client.get("/api/fs/dirs", params={"path": str(user_home / "escape")}), 403)
    assert body["error"]["code"] == "outside_home"
    names = [e["name"] for e in _check(client.get("/api/fs/dirs"), 200)["data"]["entries"]]
    assert names == ["alias", "inner"]


def test_dirs_bad_paths(tmp_path: Path, user_home: Path) -> None:
    (user_home / "f.txt").write_text("x", encoding="utf-8", newline="\n")
    client = _client(tmp_path, user_home)
    cases = [
        (str(user_home / "missing"), 404, "path_not_found"),
        (str(user_home / "f.txt"), 422, "not_a_directory"),
        ("relative/path", 422, "invalid_value"),
    ]
    for path, status, code in cases:
        body = _check(client.get("/api/fs/dirs", params={"path": path}), status)
        assert body["error"]["code"] == code


# ── /api/fs/pick ──────────────────────────────────────────────────────────────────


def test_pick_osascript_chooses(tmp_path: Path, user_home: Path) -> None:
    bin_dir = tmp_path / "bin"
    args = tmp_path / "args.txt"
    _fake(
        bin_dir,
        "osascript",
        f'printf "%s\\n" "$@" > {args.as_posix()}\necho "/Users/ada/code/repo/"\n',
    )
    picker = FolderPicker(platform="darwin", env=_env(bin_dir))
    client = _client(tmp_path, user_home, picker)
    assert _check(client.get("/api/fs/pick"), 200)["data"] == {"available": True}
    assert not args.exists()  # GET opens nothing
    body = _check(client.post("/api/fs/pick", headers=SAME_ORIGIN), 200)
    assert body["data"] == {"path": "/Users/ada/code/repo"}
    assert args.read_text(encoding="utf-8").splitlines()[0] == "-e"


def test_pick_osascript_cancel(tmp_path: Path, user_home: Path) -> None:
    bin_dir = tmp_path / "bin"
    _fake(bin_dir, "osascript", 'echo "execution error: User canceled. (-128)" >&2\nexit 1\n')
    client = _client(tmp_path, user_home, FolderPicker(platform="darwin", env=_env(bin_dir)))
    assert _check(client.post("/api/fs/pick"), 200)["data"] == {"cancelled": True}


def test_pick_osascript_failure(tmp_path: Path, user_home: Path) -> None:
    bin_dir = tmp_path / "bin"
    _fake(bin_dir, "osascript", 'echo "boom" >&2\nexit 1\n')
    client = _client(tmp_path, user_home, FolderPicker(platform="darwin", env=_env(bin_dir)))
    assert _check(client.post("/api/fs/pick"), 502)["error"]["code"] == "picker_failed"


def test_pick_zenity_chooses_and_cancels(tmp_path: Path, user_home: Path) -> None:
    bin_dir = tmp_path / "bin"
    _fake(bin_dir, "zenity", 'echo "/home/ada/repo"\n')
    env = _env(bin_dir, DISPLAY=":0")
    client = _client(tmp_path, user_home, FolderPicker(platform="linux", env=env))
    assert _check(client.get("/api/fs/pick"), 200)["data"] == {"available": True}
    assert _check(client.post("/api/fs/pick"), 200)["data"] == {"path": "/home/ada/repo"}
    _fake(bin_dir, "zenity", "exit 1\n")
    assert _check(client.post("/api/fs/pick"), 200)["data"] == {"cancelled": True}


def test_pick_kdialog_fallback(tmp_path: Path, user_home: Path) -> None:
    bin_dir = tmp_path / "bin"
    _fake(bin_dir, "kdialog", 'echo "/home/ada/k"\n')
    env = _env(bin_dir, WAYLAND_DISPLAY="wayland-0")
    client = _client(tmp_path, user_home, FolderPicker(platform="linux", env=env))
    assert _check(client.post("/api/fs/pick"), 200)["data"] == {"path": "/home/ada/k"}


def test_pick_unavailable(tmp_path: Path, user_home: Path) -> None:
    bin_dir = tmp_path / "bin"
    _fake(bin_dir, "zenity", f"touch {(tmp_path / 'opened').as_posix()}\necho /x\n")
    _fake(bin_dir, "osascript", f"touch {(tmp_path / 'opened').as_posix()}\necho /x\n")
    pickers = [
        FolderPicker(platform="linux", env=_env(bin_dir)),  # no DISPLAY
        FolderPicker(platform="linux", env=_env(bin_dir, DISPLAY=":0", SSH_CONNECTION="1 2 3")),
        FolderPicker(platform="darwin", env=_env(bin_dir, SSH_TTY="/dev/ttys001")),
        FolderPicker(platform="darwin", env=_env(tmp_path / "empty-bin")),  # no osascript
        FolderPicker(platform="win32", env=_env(bin_dir)),
    ]
    for picker in pickers:
        client = _client(tmp_path, user_home, picker)
        assert _check(client.get("/api/fs/pick"), 200)["data"] == {"available": False}
        body = _check(client.post("/api/fs/pick"), 503)
        assert body["error"]["code"] == "picker_unavailable"
    assert not (tmp_path / "opened").exists()


def test_pick_timeout(tmp_path: Path, user_home: Path) -> None:
    bin_dir = tmp_path / "bin"
    if sys.platform == "win32":
        # Git's sh runs `sleep` outside the process tree taskkill /T stops, and that `sleep`
        # keeps the output pipe open for 30 s: the fake is a Python script there
        bin_dir.mkdir(parents=True)
        script = bin_dir / "osascript"
        late = "#!/usr/bin/env python3\nimport time\ntime.sleep(30)\nprint('/late')\n"
        script.write_text(late, encoding="utf-8", newline="\n")
        make_executable(script)
    else:
        _fake(bin_dir, "osascript", "sleep 30\necho /late\n")
    picker = FolderPicker(platform="darwin", env=_env(bin_dir), timeout=0.5)
    client = _client(tmp_path, user_home, picker)
    started = time.monotonic()
    assert _check(client.post("/api/fs/pick"), 504)["error"]["code"] == "picker_timeout"
    assert time.monotonic() - started < 10
    assert fs.PICK_TIMEOUT == 300


def test_pick_one_at_a_time(tmp_path: Path, user_home: Path) -> None:
    bin_dir = tmp_path / "bin"
    opened, release = tmp_path / "opened", tmp_path / "release"
    _fake(
        bin_dir,
        "osascript",
        f"touch {opened.as_posix()}\n"
        f"while [ ! -f {release.as_posix()} ]; do sleep 0.05; done\necho /Users/ada/one\n",
    )
    client = _client(tmp_path, user_home, FolderPicker(platform="darwin", env=_env(bin_dir)))
    first: dict[str, Any] = {}

    def open_first() -> None:
        first["response"] = client.post("/api/fs/pick")

    thread = threading.Thread(target=open_first)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not opened.exists():
            assert time.monotonic() < deadline
            time.sleep(0.02)
        body = _check(client.post("/api/fs/pick"), 409)
        assert body["error"]["code"] == "picker_busy"
    finally:
        release.touch()
        thread.join(timeout=10)
    assert _check(first["response"], 200)["data"] == {"path": "/Users/ada/one"}
    os.remove(release)
    opened.unlink()
    _fake(bin_dir, "osascript", "echo /Users/ada/two\n")
    assert _check(client.post("/api/fs/pick"), 200)["data"] == {"path": "/Users/ada/two"}


def test_pick_post_passes_write_guard(tmp_path: Path, user_home: Path) -> None:
    bin_dir = tmp_path / "bin"
    _fake(bin_dir, "osascript", f"touch {(tmp_path / 'opened').as_posix()}\necho /x\n")
    client = _client(tmp_path, user_home, FolderPicker(platform="darwin", env=_env(bin_dir)))
    response = client.post("/api/fs/pick", headers={"Origin": "http://evil.example"})
    assert _check(response, 403)["error"]["code"] == "cross_origin"
    assert not (tmp_path / "opened").exists()


def test_codes_registered() -> None:
    for code in (
        "outside_home",
        "permission_denied",
        "picker_unavailable",
        "picker_busy",
        "picker_timeout",
        "picker_failed",
    ):
        assert code in ERROR_CODES
