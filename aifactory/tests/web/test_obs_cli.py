"""`factory obs`: the multi-repo dashboard, registry, port order and errors (server patched)."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

import pytest
import yaml
from multi_repo import init_repo, onboard, write

from aifactory import __version__, check
from aifactory.cli import main
from aifactory.home import HOME_ENV
from aifactory.web import server as web_server
from cli_json import run_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "check"))

from factory_check_repo import FakeMachine  # noqa: E402

Calls = list[dict[str, Any]]


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home"
    monkeypatch.setenv(HOME_ENV, str(path))
    return path


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    urls: list[str] = []

    def fake_open(url: str, *args: object, **kwargs: object) -> bool:
        urls.append(url)
        return True

    monkeypatch.setattr("webbrowser.open", fake_open)
    return urls


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch, home: Path, opened: list[str]) -> Calls:
    # Default-host tests must not inherit the operator's dashboard bind address.
    # The environment override test sets its own value after fixture setup.
    monkeypatch.delenv(web_server.HOST_ENV, raising=False)
    calls: Calls = []

    def fake_serve(
        app: object, port: int, *, open_browser: bool, host: str, open_path: str = ""
    ) -> None:
        calls.append(
            {
                "app": app,
                "port": port,
                "open_browser": open_browser,
                "host": host,
                "open_path": open_path,
            }
        )

    def no_probe(port: int, host: str = "", timeout: float = 1.0) -> bool:
        raise AssertionError("the probe runs only when the port is taken")

    monkeypatch.setattr(web_server, "serve", fake_serve)
    monkeypatch.setattr(web_server, "check_port", lambda port, wait=0.0, host="": None)
    monkeypatch.setattr(web_server, "probe_dashboard", no_probe)
    return calls


def _registry(home: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((home / "dashboard.yaml").read_text(encoding="utf-8"))
    return data


def test_obs_without_repo_outside_git(
    tmp_path: Path,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    served: Calls,
) -> None:
    outside = tmp_path / "plain"
    outside.mkdir()
    monkeypatch.chdir(outside)
    rc, env = run_json(capsys, ["obs", "--no-open", "--json"])
    assert rc == 0
    assert env["data"] == {
        "url": "http://127.0.0.1:4700/",
        "host": "127.0.0.1",
        "port": 4700,
        "repo": None,
        "version": __version__,
        "repo_id": None,
        "home": str(home),
        "reused": False,
    }
    assert len(served) == 1
    call = served[0]
    assert (call["port"], call["open_browser"], call["host"]) == (4700, False, "127.0.0.1")
    assert call["open_path"] == ""
    assert call["app"].state.registry.home == home
    assert not (home / "dashboard.yaml").exists()


def test_obs_repo_registers_and_opens_it(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str], served: Calls
) -> None:
    root = init_repo(tmp_path / "My Repo")
    (root / "sub").mkdir()
    rc, env = run_json(capsys, ["obs", "--repo", str(root / "sub"), "--json"])
    assert rc == 0
    data = env["data"]
    assert data["repo_id"] == "my-repo"
    assert data["repo"] == str(root)
    assert data["reused"] is False
    assert served[-1]["open_path"] == "#/r/my-repo/factory"  # no factory: the Factory tab
    assert served[-1]["open_browser"] is True
    entries = _registry(home)["repos"]
    assert [(e["id"], e["path"]) for e in entries] == [("my-repo", str(root))]
    # idempotent: the same id, still one entry
    rc, env = run_json(capsys, ["obs", "--repo", str(root), "--no-open", "--json"])
    assert rc == 0 and env["data"]["repo_id"] == "my-repo"
    assert len(_registry(home)["repos"]) == 1


def test_obs_repo_relative_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    served: Calls,
) -> None:
    root = init_repo(tmp_path / "rel")
    monkeypatch.chdir(root)
    rc, env = run_json(capsys, ["obs", "--repo", ".", "--no-open", "--json"])
    assert rc == 0 and env["data"]["repo_id"] == "rel"


@pytest.mark.parametrize(
    ("make", "code"),
    [
        (lambda p: p.mkdir() or p, "not_git"),
        (lambda p: p, "path_not_found"),
        (lambda p: init_repo(p, commit=False), "no_commits"),
    ],
)
def test_obs_repo_refused(
    tmp_path: Path,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    served: Calls,
    make: Any,
    code: str,
) -> None:
    path = make(tmp_path / "x")
    rc, env = run_json(capsys, ["obs", "--repo", str(path), "--json"])
    assert rc == 2
    assert env["error"]["code"] == code
    assert served == []
    assert not (home / "dashboard.yaml").exists()
    assert main(["obs", "--repo", str(path)]) == 2
    assert f"factory obs: {code}: " in capsys.readouterr().err


def test_obs_port_order(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str], served: Calls
) -> None:
    rc, env = run_json(capsys, ["obs", "--no-open", "--json"])
    assert rc == 0 and env["data"]["port"] == 4700
    write(home, "dashboard.yaml", "version: 1\nport: 4811\nrepos: []\n")
    rc, env = run_json(capsys, ["obs", "--no-open", "--json"])
    assert rc == 0 and env["data"]["port"] == 4811
    assert env["data"]["url"] == "http://127.0.0.1:4811/"
    rc, env = run_json(capsys, ["obs", "--port", "4999", "--json"])
    assert rc == 0 and env["data"]["port"] == 4999
    assert served[-1]["port"] == 4999 and served[-1]["open_browser"] is True


def test_obs_host_from_option_and_env(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, served: Calls
) -> None:
    monkeypatch.setenv(web_server.HOST_ENV, "0.0.0.0")
    rc, env = run_json(capsys, ["obs", "--no-open", "--json"])
    assert rc == 0
    # every address: the URL to open on this machine stays loopback
    assert env["data"]["host"] == "0.0.0.0"
    assert env["data"]["url"] == "http://127.0.0.1:4700/"
    assert served[-1]["host"] == "0.0.0.0"
    rc, env = run_json(capsys, ["obs", "--no-open", "--json", "--host", "127.0.0.1"])
    assert rc == 0 and env["data"]["host"] == "127.0.0.1"
    assert served[-1]["host"] == "127.0.0.1"


def test_allowed_hosts_open_only_off_loopback() -> None:
    assert web_server.allowed_hosts("127.0.0.1") == ["127.0.0.1", "localhost"]
    assert web_server.allowed_hosts("0.0.0.0") == ["*"]
    assert web_server.dashboard_url(4700, "192.168.1.5") == "http://192.168.1.5:4700/"


def test_obs_text_output(tmp_path: Path, capsys: pytest.CaptureFixture[str], served: Calls) -> None:
    root = init_repo(tmp_path / "repo")
    assert main(["obs", "--repo", str(root), "--port", "4702"]) == 0
    assert "HAIFA dashboard: http://127.0.0.1:4702/#/r/repo/factory" in capsys.readouterr().out
    assert served[0]["open_browser"] is True


def test_obs_opens_the_backlog_of_a_ready_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], served: Calls
) -> None:
    from aifactory.web.registry import Registry
    from aifactory.web.repos import repo_status

    root = init_repo(tmp_path / "ready")
    onboard(root)
    rc, env = run_json(capsys, ["obs", "--repo", str(root), "--json"])
    assert rc == 0
    state, _warnings = Registry(Path(env["data"]["home"])).snapshot()
    (entry,) = state.repos
    assert repo_status(entry)["status"] == "ok"
    assert served[-1]["open_path"] == "#/r/ready/backlog"


def _port_taken(monkeypatch: pytest.MonkeyPatch, *, ours: bool) -> list[int]:
    probes: list[int] = []

    def taken(port: int, wait: float = 0.0, host: str = "") -> None:
        raise web_server.PortInUseError(port, host)

    def never(*args: object, **kwargs: object) -> None:
        raise AssertionError("serve must not run")

    def probe(port: int, host: str = "", timeout: float = 1.0) -> bool:
        probes.append(port)
        return ours

    monkeypatch.setattr(web_server, "check_port", taken)
    monkeypatch.setattr(web_server, "serve", never)
    monkeypatch.setattr(web_server, "probe_dashboard", probe)
    return probes


def test_obs_reuses_a_running_dashboard(
    tmp_path: Path,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    opened: list[str],
) -> None:
    root = init_repo(tmp_path / "repo")
    probes = _port_taken(monkeypatch, ours=True)
    rc, env = run_json(capsys, ["obs", "--repo", str(root), "--json"])
    assert rc == 0
    assert env["data"]["reused"] is True and env["data"]["repo_id"] == "repo"
    assert probes == [4700]
    assert opened == ["http://127.0.0.1:4700/#/r/repo/factory"]
    assert [e["id"] for e in _registry(home)["repos"]] == ["repo"]
    rc, env = run_json(capsys, ["obs", "--repo", str(root), "--no-open", "--json"])
    assert rc == 0 and env["data"]["reused"] is True
    assert len(opened) == 1
    assert main(["obs", "--no-open"]) == 0
    assert "HAIFA dashboard už běží: http://127.0.0.1:4700/" in capsys.readouterr().out


def test_obs_port_in_use_by_another_service(
    tmp_path: Path,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    opened: list[str],
) -> None:
    probes = _port_taken(monkeypatch, ours=False)
    rc, env = run_json(capsys, ["obs", "--json"])
    assert rc == 2
    assert env["error"]["code"] == "port_in_use"
    assert probes == [4700] and opened == []


def test_obs_restart_does_not_probe(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    probes = _port_taken(monkeypatch, ours=True)
    monkeypatch.setenv(web_server.RESTART_ENV, "1")
    rc, env = run_json(capsys, ["obs", "--json"])
    assert rc == 2 and env["error"]["code"] == "port_in_use"
    assert probes == []


@pytest.mark.parametrize("port", ["0", "70000"])
def test_obs_bad_port(capsys: pytest.CaptureFixture[str], served: Calls, port: str) -> None:
    rc, env = run_json(capsys, ["obs", "--port", port, "--json"])
    assert rc == 2
    assert env["error"]["code"] == "invalid_value"
    assert served == []


def test_old_local_port_is_ignored_everywhere(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    served: Calls,
) -> None:
    # Port compatibility must not depend on the operator's platform or installed tools.
    machine = FakeMachine()
    monkeypatch.setattr(check, "default_machine", lambda: machine)
    root = init_repo(tmp_path / "repo")
    write(root, ".factory/prompts/builder/system.md", "You build.\n")
    write(root, ".factory/prompts/builder/user.md", "Build it.\n")
    write(root, "justfile", "test:\n    echo ok\n")
    onboard(root)
    write(root, ".factory/local.yaml", "port: 4811\n")
    rc, env = run_json(capsys, ["obs", "--repo", str(root), "--no-open", "--json"])
    assert rc == 0
    assert env["data"]["port"] == 4700
    assert any(w.startswith("local_port_ignored") for w in env["warnings"])
    assert main(["obs", "--repo", str(root), "--no-open"]) == 0
    assert "warning: local_port_ignored" in capsys.readouterr().err

    monkeypatch.chdir(root)
    rc, env = run_json(capsys, ["config", "show", "--json"])
    assert rc == 0
    assert "port" not in env["data"]["local"]
    assert any(w.startswith("local_port_ignored") for w in env["warnings"])
    rc, env = run_json(capsys, ["check", "--offline", "--json"])
    assert rc == 0 and env["ok"] is True, env
    codes = [f["code"] for f in env["data"]["findings"]]
    assert "local_port_ignored" in codes and "local_config_invalid" not in codes


class _Busy:
    """A launcher whose two runs go on after the server ends."""

    def running(self) -> list[object]:
        return [object(), object()]


@pytest.fixture
def busy_serve(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    def fake_serve(
        app: Any, port: int, *, open_browser: bool, host: str, open_path: str = ""
    ) -> None:
        app.state.launcher = _Busy()

    monkeypatch.setattr(web_server, "serve", fake_serve)
    monkeypatch.setattr(web_server, "check_port", lambda port, wait=0.0, host="": None)


def test_obs_reports_runs_that_go_on(capsys: pytest.CaptureFixture[str], busy_serve: None) -> None:
    assert main(["obs", "--port", "4703", "--no-open"]) == 0
    out = capsys.readouterr().out
    assert "Běhy spuštěné z dashboardu, které pokračují: 2" in out
    assert "factory task stop" in out


def test_obs_json_reports_runs_on_stderr(
    capsys: pytest.CaptureFixture[str], busy_serve: None
) -> None:
    assert main(["obs", "--no-open", "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["ok"] is True
    assert "pokračují: 2" in captured.err


def test_obs_reports_no_runs(capsys: pytest.CaptureFixture[str], served: Calls) -> None:
    assert main(["obs", "--port", "4704", "--no-open"]) == 0
    out = capsys.readouterr().out
    assert "pokračují: 0" in out
    assert "factory task stop" not in out


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


@pytest.mark.parametrize(
    ("body", "ours"),
    [
        ({"ok": True, "data": {"app": "haifa-dashboard", "version": "1"}}, True),
        ({"ok": True, "data": {"app": "other"}}, False),
        ({"ok": False, "data": {"app": "haifa-dashboard"}}, False),
        ([1, 2], False),
        (None, False),
    ],
)
def test_probe_dashboard(monkeypatch: pytest.MonkeyPatch, body: Any, ours: bool) -> None:
    urls: list[str] = []

    def fake_urlopen(url: str, timeout: float = 0.0) -> _Response:
        urls.append(url)
        raw = b"<html>not json</html>" if body is None else json.dumps(body).encode()
        return _Response(raw)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert web_server.probe_dashboard(4700) is ours
    assert urls == ["http://127.0.0.1:4700/api/health"]


def test_probe_dashboard_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(url: str, timeout: float = 0.0) -> _Response:
        raise OSError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", refused)
    assert web_server.probe_dashboard(4700) is False
