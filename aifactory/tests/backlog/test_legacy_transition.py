"""One shared backlog, independent installations; frozen pre-S11 reader stays compatible."""

from pathlib import Path

import pytest

from aifactory.backlog import Task, add_task, edit_task, follow_up_task, load_backlog
from aifactory.backlog.taskfile import mark_done
from aifactory.repo_settings import RepositorySettings, SettingsError
from aifactory.run.gitops import git
from cli_json import run_json
from legacy_backlog import derived as old_derived
from legacy_backlog import loader as old_loader
from legacy_backlog.model import Task as OldTask

LEGACY = {"auto_merge", "auto_continue", "harness", "model", "thinking"}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".factory").mkdir(parents=True)
    (root / ".factory/config.yaml").write_text("levels: [project, step, task]\ndocs_root: .\n")
    step = root / "backlog/P/S"
    step.mkdir(parents=True)
    (step.parent / "index.md").write_text(
        "---\nid: P\ntitle: Project\nauto_merge: true\nauto_continue: true\n"
        "harness: codex\nmodel: legacy-model\nthinking: high\n---\n"
    )
    (step / "index.md").write_text("---\nid: P-S\ntitle: Step\n---\n")
    (step / "P-S-T01.md").write_text("---\nid: P-S-T01\ntitle: Task\nstatus: todo\n---\n")
    git(root, "init")
    return root


def contents(repo: Path) -> dict[str, bytes]:
    return {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*.md")}


@pytest.mark.parametrize("local", [None, False, True, "import"])
def test_installation_matrix(repo: Path, tmp_path: Path, local: bool | str | None) -> None:
    home = tmp_path / "computer-a"
    service = RepositorySettings(repo, home)
    before = contents(repo)
    if type(local) is bool:
        service.update({"auto_merge": local, "auto_continue": local})
    elif local == "import":
        service.import_legacy()
    enabled = local is True or local == "import"
    assert service.read().auto_merge is enabled
    assert service.read().auto_continue is enabled
    assert contents(repo) == before
    # A fresh service instance models a restart and always reads persisted values.
    assert RepositorySettings(repo, home).read() == service.read()
    other = RepositorySettings(repo, tmp_path / "computer-b")
    assert other.read().auto_merge is False
    assert other.read().auto_continue is False
    assert not other.directory.exists()
    # A changed shared backlog (as after git pull) cannot replace local choices.
    path = repo / "backlog/P/index.md"
    path.write_text(path.read_text().replace(": true", ": false").replace("codex", "claude"))
    assert service.read().auto_merge is enabled
    assert service.read().auto_continue is enabled
    if local is not None:
        saved = service.path.read_bytes()
        service.import_legacy()
        assert service.path.read_bytes() == saved


def test_preview_is_read_only_and_reports_every_level(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = RepositorySettings(repo, tmp_path / "home")
    before = contents(repo)

    def forbidden(*args: object) -> None:
        pytest.fail("preview must not synchronize the database mirror")

    monkeypatch.setattr("aifactory.database.backlog.synchronize", forbidden)
    preview = service.legacy_preview()
    assert {n["level"] for n in preview["nodes"]} == {"project", "step", "task"}
    task = preview["nodes"][-1]
    assert task["values"]["auto_merge"]["value"] is True
    assert task["values"]["auto_merge"]["origin"]["id"] == "P"
    assert task["binding"] == {"harness": "codex", "model": "legacy-model", "thinking": "high"}
    assert not service.directory.exists()
    assert contents(repo) == before


def test_conflicts_require_decisions_and_preserve_existing(repo: Path, tmp_path: Path) -> None:
    path = repo / "backlog/P/S/index.md"
    path.write_text(path.read_text().replace("title: Step", "title: Step\nauto_merge: false"))
    service = RepositorySettings(repo, tmp_path / "home")
    assert service.legacy_preview()["proposals"]["auto_merge"]["conflict"] is True
    with pytest.raises(SettingsError, match="choose auto_merge"):
        service.import_legacy()
    assert not service.path.exists()
    result = service.import_legacy({"auto_merge": False})
    assert result["settings"]["auto_merge"] is False
    saved = service.path.read_bytes()
    assert service.import_legacy({"auto_merge": True})["settings"]["auto_merge"] is False
    assert service.path.read_bytes() == saved
    assert (
        service.import_legacy({"auto_merge": True}, overwrite=True)["settings"]["auto_merge"]
        is True
    )


def test_import_failure_is_atomic(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = RepositorySettings(repo, tmp_path / "home")
    service.update({"auto_merge": False})
    before = service.path.read_bytes()

    def fail(*args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("aifactory.repo_settings.os.replace", fail)
    with pytest.raises(SettingsError, match="disk full"):
        service.import_legacy(overwrite=True)
    assert service.path.read_bytes() == before
    assert sorted(p.name for p in service.directory.iterdir()) == sorted(
        [service.path.name, service.lock_path.name]
    )


def test_new_backlog_without_operating_keys(repo: Path, tmp_path: Path) -> None:
    (repo / "backlog/P/index.md").write_text("---\nid: P\ntitle: Project\n---\n")
    service = RepositorySettings(repo, tmp_path / "home")
    assert not load_backlog(repo).issues
    created = add_task(repo, "P-S", "New task")
    assert not (LEGACY & created.task.own.keys())
    imported = service.import_legacy()["settings"]
    assert imported["auto_merge"] is False and imported["auto_continue"] is False
    assert imported["harness"] is None


def test_old_reader_preserves_operating_values_after_edits_and_completion(repo: Path) -> None:
    path = repo / "backlog/P/S/P-S-T01.md"
    path.write_text(
        path.read_text().replace(
            "status: todo", "status: todo\nauto_merge: false\nauto_continue: false"
        )
    )
    before = old_loader.load_backlog(repo)
    old_task = before.by_id["P-S-T01"]
    assert isinstance(old_task, OldTask)
    original = old_derived.effective(old_task)
    edit_task(repo, "P-S-T01", title="Edited")
    path = repo / "backlog/P/S/P-S-T01.md"
    # approve and sync use this same text operation; legacy header bytes survive it.
    path.write_text(mark_done(path.read_text(), "- 2026-11-09 · test"))
    follow_up_task(repo, "P-S-T01", "Continue")
    add_task(repo, "P-S", "Another")
    after = old_loader.load_backlog(repo)
    assert after.issues == []
    old_task = after.by_id["P-S-T01"]
    assert isinstance(old_task, OldTask)
    assert {k: old_derived.effective(old_task)[k] for k in LEGACY} == {
        k: original[k] for k in LEGACY
    }
    assert old_task.status == "done"
    assert len(list(old_loader.iter_tasks(after))) == 3
    for task in load_backlog(repo).by_id.values():
        if isinstance(task, Task) and task.id != "P-S-T01":
            assert not LEGACY & task.own.keys()


def test_cli_preview_and_explicit_import(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "home"))
    args = ["--repo", str(repo), "--json"]
    code, preview = run_json(capsys, ["config", "local", "legacy", *args])
    assert code == 0 and preview["data"]["proposals"]["auto_merge"]["value"] is True
    assert not (tmp_path / "home").exists()
    code, result = run_json(capsys, ["config", "local", "import", *args])
    assert code == 0 and result["data"]["settings"]["auto_merge"] is True
    code, result = run_json(
        capsys, ["config", "local", "import", "--overwrite", "--auto-merge", "off", *args]
    )
    assert code == 0 and result["data"]["settings"]["auto_merge"] is False


def test_git_pull_cannot_change_local_policy(repo: Path, tmp_path: Path) -> None:
    git(repo, "config", "user.name", "Compatibility test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Legacy backlog")
    remote = tmp_path / "remote.git"
    git(tmp_path, "clone", "--bare", str(repo), str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    second = tmp_path / "second"
    git(tmp_path, "clone", str(remote), str(second))
    git(second, "config", "user.name", "Compatibility test")
    git(second, "config", "user.email", "test@example.invalid")
    service = RepositorySettings(repo, tmp_path / "home")
    service.import_legacy()
    saved = service.path.read_bytes()
    path = second / "backlog/P/index.md"
    path.write_text(path.read_text().replace(": true", ": false"))
    git(second, "add", ".")
    git(second, "commit", "-m", "Change legacy policy elsewhere")
    git(second, "push", "origin", "HEAD")
    branch = git(repo, "branch", "--show-current").strip()
    git(repo, "pull", "--ff-only", "origin", branch)
    assert service.legacy_preview()["proposals"]["auto_merge"]["value"] is False
    assert RepositorySettings(repo, tmp_path / "home").read().auto_merge is True
    service.import_legacy()
    assert service.path.read_bytes() == saved


def test_preview_uses_legacy_binding_when_harness_switch_drops_model(
    repo: Path, tmp_path: Path
) -> None:
    path = repo / "backlog/P/S/P-S-T01.md"
    path.write_text(path.read_text().replace("status: todo", "status: todo\nharness: claude"))
    preview = RepositorySettings(repo, tmp_path / "home").legacy_preview()
    task = next(node for node in preview["nodes"] if node["id"] == "P-S-T01")
    assert task["values"]["harness"]["value"] == "claude"
    assert task["values"]["harness"]["origin"]["id"] == "P-S-T01"
    assert task["values"]["model"] == {"value": None, "origin": None}
    assert task["values"]["thinking"]["value"] == "high"
    assert preview["proposals"]["harness"]["conflict"] is True
