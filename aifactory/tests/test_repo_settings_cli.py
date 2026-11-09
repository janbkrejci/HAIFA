"""CLI uses the same service without a dashboard registration or Git writes."""

from pathlib import Path

import pytest

from aifactory.repo_settings import RepositorySettings
from aifactory.run.gitops import git
from cli_json import run_json


def test_show_set_and_persist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    home = tmp_path / "home"
    monkeypatch.setenv("HAIFA_HOME", str(home))
    args = ["--repo", str(repo), "--json"]
    rc, result = run_json(capsys, ["config", "local", "show", *args])
    assert rc == 0
    assert not home.exists()
    assert result["data"]["settings"]["auto_continue"] is False
    rc, result = run_json(
        capsys,
        [
            "config",
            "local",
            "set",
            "--auto-merge",
            "on",
            "--auto-continue",
            "on",
            "--harness",
            "codex",
            *args,
        ],
    )
    assert rc == 0
    assert result["data"] == RepositorySettings(repo).show()
    rc, result = run_json(capsys, ["config", "local", "set", "--auto-continue", "off", *args])
    assert rc == 0
    assert result["data"]["settings"]["auto_merge"] is True
    assert result["data"]["settings"]["auto_continue"] is False
    rc, result = run_json(capsys, ["config", "local", "set", "--harness", "inherit", *args])
    assert rc == 0 and result["data"]["effective_harness"] is None
    rc, result = run_json(capsys, ["config", "local", "show", *args])
    assert rc == 0 and result["data"] == RepositorySettings(repo).show()
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == ""
    assert not (home / "dashboard.yaml").exists()


def test_errors_are_enveloped_and_do_not_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    git(tmp_path, "init")
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "home"))
    args = ["--repo", str(tmp_path), "--json"]
    rc, result = run_json(capsys, ["config", "local", "set", *args])
    assert rc == 2 and result["error"]["code"] == "invalid_value"
    service = RepositorySettings(tmp_path)
    service.update({"auto_merge": False})
    service.path.write_text('{"version": 99}', encoding="utf-8")
    for command in (["show"], ["set", "--auto-merge", "on"]):
        rc, result = run_json(capsys, ["config", "local", *command, *args])
        assert rc == 2 and result["error"]["code"] == "repo_settings_version"
        assert result["error"]["path"] == str(service.path)
    assert service.path.read_text(encoding="utf-8") == '{"version": 99}'

    service.path.unlink()

    def fail(*args: object) -> None:
        raise OSError("cannot save")

    monkeypatch.setattr("aifactory.repo_settings.os.replace", fail)
    rc, result = run_json(capsys, ["config", "local", "set", "--auto-merge", "on", *args])
    assert rc == 2 and result["error"]["code"] == "repo_settings_io"
    assert not service.path.exists()


@pytest.mark.parametrize("select_harness", [False, True])
def test_explicit_harness_ignores_broken_machine_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    select_harness: bool,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    home = tmp_path / "home"
    monkeypatch.setenv("HAIFA_HOME", str(home))
    service = RepositorySettings(repo)
    service.update({"auto_continue": True, "harness": None if select_harness else "codex"})
    (home / "harnesses.json").write_text("broken", encoding="utf-8")
    options = ["--harness", "codex"] if select_harness else ["--auto-continue", "off"]
    args = ["--repo", str(repo), "--json"]

    rc, result = run_json(capsys, ["config", "local", "set", *options, *args])

    assert rc == 0
    persisted = RepositorySettings(repo).read()
    assert persisted.harness == "codex"
    assert persisted.auto_continue is select_harness
    assert result["data"] == RepositorySettings(repo).show()
    rc, shown = run_json(capsys, ["config", "local", "show", *args])
    assert rc == 0 and shown["data"] == result["data"]
    assert (home / "harnesses.json").read_text(encoding="utf-8") == "broken"
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == ""


@pytest.mark.parametrize("initial", ["missing", "inherited", "explicit"])
def test_inheriting_broken_machine_settings_fails_before_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    initial: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    home = tmp_path / "home"
    monkeypatch.setenv("HAIFA_HOME", str(home))
    service = RepositorySettings(repo)
    home.mkdir()
    (home / "harnesses.json").write_text("broken", encoding="utf-8")
    if initial != "missing":
        service.update(
            {"auto_continue": True, "harness": "codex" if initial == "explicit" else None}
        )
    previous = service.path.read_bytes() if service.path.exists() else None
    options = ["--harness", "inherit"] if initial == "explicit" else ["--auto-continue", "off"]

    rc, result = run_json(
        capsys, ["config", "local", "set", *options, "--repo", str(repo), "--json"]
    )

    assert rc == 2 and result["error"]["code"] == "repo_settings_invalid"
    assert (service.path.read_bytes() if service.path.exists() else None) == previous
