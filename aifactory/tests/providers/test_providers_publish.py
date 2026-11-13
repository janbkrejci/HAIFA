"""`providers.publish` and its git helpers: commits without a checkout, no forced push."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from provider_repo import git, isolate_git, make_repo

from aifactory.providers import ProviderError
from aifactory.providers import git as pgit
from aifactory.providers.publish import PlannedFile, plan_digest, plan_files


@pytest.mark.parametrize("count", [10, 1309])
def test_pull_many_files_uses_constant_git_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    from aifactory.config.settings import ProjectSettings
    from aifactory.providers.publish import plan_pull_base, pull_base
    from aifactory.run import TaskRunStore

    isolate_git(monkeypatch)
    repo = make_repo(tmp_path, with_remote=True)
    git(repo, "checkout", "-qb", "incoming")
    for i in range(count):
        (repo / f"evidence {i}.png").write_bytes(BINARY + str(i).encode())
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "evidence")
    git(repo, "push", "-q", "origin", "HEAD:main")
    git(repo, "checkout", "-q", "main")

    calls: list[list[str]] = []
    run = subprocess.run

    def counted(args: list[str], **kwargs: Any) -> Any:
        if args[0] == "git":
            calls.append(args[1:])
        return run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", counted)
    settings = ProjectSettings(base="main", git_provider="local")
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        plan = plan_pull_base(repo, settings=settings, store=store)
        assert len(plan["files"]) == count
        assert all(f["binary"] and f["action"] == "create" for f in plan["files"])
        preview_calls = len(calls)
        assert sum(c[:2] == ["cat-file", "--batch"] for c in calls) == 1
        result = pull_base(repo, settings=settings, store=store, expect=plan["digest"])
        assert result.updated
        assert len(calls) < 60  # both preview and confirmation, independent of file count
        assert not any(c[0] == "ls-tree" for c in calls)
        # Confirmation revalidates the preview; execution on a clean checkout reads no blobs.
        assert sum(c[:2] == ["cat-file", "--batch"] for c in calls[preview_calls:]) == 1
        assert not git(repo, "status", "--porcelain")
        assert (repo / f"evidence {count - 1}.png").read_bytes() == BINARY + str(count - 1).encode()
    finally:
        store.close()


def test_pull_raw_diff_preserves_contents_modes_and_both_rename_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.providers.publish import _pull_files

    isolate_git(monkeypatch)
    repo = make_repo(tmp_path, with_remote=False)
    (repo / "binary").write_bytes(BINARY)
    (repo / "empty").write_bytes(b"")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "before")
    before = git(repo, "rev-parse", "HEAD")
    git(repo, "mv", "a.txt", "renamed space.txt")
    (repo / "binary").write_bytes(b"\x00\nchanged\n\x00")
    (repo / "empty").unlink()
    (repo / "new empty").write_bytes(b"")
    git(repo, "add", "-A")
    git(repo, "update-index", "--chmod=+x", "binary")
    git(repo, "commit", "-qm", "after")
    after = git(repo, "rev-parse", "HEAD")

    files = {f.path: f for f in _pull_files(repo, before, after)}
    assert set(files) == {"a.txt", "renamed space.txt", "binary", "empty", "new empty"}
    assert files["a.txt"].action == "delete"
    assert files["renamed space.txt"].content == files["a.txt"].old_content
    assert files["renamed space.txt"].action == "create"
    assert files["binary"].old_content == BINARY
    assert files["binary"].content == b"\x00\nchanged\n\x00"
    assert files["binary"].old_mode == "100644" and files["binary"].mode == "100755"
    assert files["empty"].old_content == b"" and files["empty"].content is None
    assert files["new empty"].content == b""


@pytest.mark.parametrize("local", ["matching", "staged", "conflict", "unrelated", "status_failed"])
def test_pull_reads_only_dirty_paths_and_preserves_conflicting_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, local: str
) -> None:
    from aifactory.config.settings import ProjectSettings
    from aifactory.providers.publish import pull_base
    from aifactory.run import TaskRunStore

    isolate_git(monkeypatch)
    repo = make_repo(tmp_path, with_remote=True)
    before = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-qb", "incoming")
    (repo / "a.txt").write_bytes(b"incoming\n")
    (repo / "other").write_bytes(BINARY)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "incoming")
    git(repo, "push", "-q", "origin", "HEAD:main")
    git(repo, "checkout", "-q", "main")
    (repo / "a.txt").write_bytes(b"incoming\n" if local in {"matching", "staged"} else b"local\n")
    if local == "staged":
        git(repo, "add", "a.txt")
    if local == "unrelated":
        (repo / "a.txt").write_bytes(b"one\ntwo\nthree\n")
        (repo / "unrelated").write_bytes(b"local\n")
        git(repo, "add", "unrelated")

    batches: list[bytes] = []
    run_bytes = pgit.run_bytes

    def inspect(cwd: Path, args: Any, **kwargs: Any) -> Any:
        if args[:2] == ["cat-file", "--batch"]:
            batches.append(kwargs["input_bytes"])
        if local == "status_failed" and args[0] == "status":
            return subprocess.CompletedProcess(args, 1, b"", b"status failed")
        return run_bytes(cwd, args, **kwargs)

    monkeypatch.setattr(pgit, "run_bytes", inspect)
    index = (repo / ".git/index").read_bytes()
    content = (repo / "a.txt").read_bytes()
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        settings = ProjectSettings(base="main", git_provider="local")
        if local in {"matching", "staged"}:
            assert pull_base(repo, settings=settings, store=store).updated
            assert not git(repo, "status", "--porcelain")
        else:
            with pytest.raises(ProviderError) as error:
                pull_base(repo, settings=settings, store=store)
            assert error.value.code == "dirty_base"
            assert git(repo, "rev-parse", "HEAD") == before
            assert (repo / ".git/index").read_bytes() == index
            assert (repo / "a.txt").read_bytes() == content
        if local != "status_failed":
            assert len(batches) == (0 if local == "unrelated" else 1)
            assert all(len(b.splitlines()) == 2 for b in batches)  # only old/new a.txt
    finally:
        store.close()


def test_batch_read_rejects_missing_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolate_git(monkeypatch)
    repo = make_repo(tmp_path, with_remote=False)
    with pytest.raises(ProviderError) as error:
        pgit.read_blobs(repo, ["0" * 40])
    assert error.value.code == "pull_failed"


def test_remove_worktree_does_not_delete_when_process_cannot_be_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory import worktree_processes

    isolate_git(monkeypatch)
    repo = make_repo(tmp_path, with_remote=False)
    worktree = tmp_path / "worktree"
    git(repo, "worktree", "add", "--detach", str(worktree))
    metadata = Path(git(worktree, "rev-parse", "--absolute-git-dir"))

    def cannot_stop(_path: Path) -> None:
        raise OSError("cannot stop process 123")

    monkeypatch.setattr(worktree_processes, "stop_directory_processes", cannot_stop)
    with pytest.raises(ProviderError, match="cannot stop process 123") as error:
        pgit.remove_worktree(repo, worktree)
    assert error.value.code == "worktree_remove_failed"
    assert metadata.is_dir()
    assert (worktree / "a.txt").is_file()


def test_remove_worktree_does_not_stop_processes_in_unregistered_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    from aifactory import worktree_processes

    isolate_git(monkeypatch)
    repo = make_repo(tmp_path, with_remote=False)
    personal = tmp_path / "personal"
    personal.mkdir()
    sentinel = personal / "file.txt"
    sentinel.write_bytes(b"keep")
    stop = Mock()
    monkeypatch.setattr(worktree_processes, "stop_directory_processes", stop)
    with pytest.raises(ProviderError, match="not a registered worktree"):
        pgit.remove_worktree(repo, personal)
    stop.assert_not_called()
    assert sentinel.read_bytes() == b"keep"


def test_remove_worktree_refuses_directory_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    from aifactory import worktree_processes

    isolate_git(monkeypatch)
    repo = make_repo(tmp_path, with_remote=False)
    worktree = tmp_path / "worktree"
    git(repo, "worktree", "add", "--detach", str(worktree))
    link = tmp_path / "link"
    try:
        link.symlink_to(worktree, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    stop = Mock()
    monkeypatch.setattr(worktree_processes, "stop_directory_processes", stop)
    with pytest.raises(ProviderError, match="symlink"):
        pgit.remove_worktree(repo, link)
    stop.assert_not_called()
    assert (worktree / "a.txt").is_file()


@pytest.mark.parametrize("change", ["delete", "rename", "staged_rename"])
def test_pull_accepts_local_deletions_and_both_sides_of_renames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    from aifactory.config.settings import ProjectSettings
    from aifactory.providers.publish import pull_base
    from aifactory.run import TaskRunStore

    isolate_git(monkeypatch)
    repo = make_repo(tmp_path, with_remote=True)
    git(repo, "checkout", "-qb", "incoming")
    if change == "delete":
        git(repo, "rm", "a.txt")
    else:
        git(repo, "mv", "a.txt", "renamed.txt")
    git(repo, "commit", "-qm", "incoming")
    git(repo, "push", "-q", "origin", "HEAD:main")
    git(repo, "checkout", "-q", "main")
    if change == "delete":
        (repo / "a.txt").unlink()
    else:
        (repo / "a.txt").rename(repo / "renamed.txt")
        if change == "staged_rename":
            git(repo, "add", "-A")
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        assert pull_base(
            repo, settings=ProjectSettings(base="main", git_provider="local"), store=store
        ).updated
        assert not git(repo, "status", "--porcelain")
        assert not (repo / "a.txt").exists()
        if change != "delete":
            assert (repo / "renamed.txt").read_bytes() == b"one\ntwo\nthree\n"
    finally:
        store.close()


def test_pull_digest_rejects_remote_movement_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.config.settings import ProjectSettings
    from aifactory.providers.publish import plan_pull_base, pull_base
    from aifactory.run import TaskRunStore

    isolate_git(monkeypatch)
    repo = make_repo(tmp_path, with_remote=True)
    remote = tmp_path / "origin.git"
    head = git(repo, "rev-parse", "main")
    settings = ProjectSettings(base="main", git_provider="local")
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        plan = plan_pull_base(repo, settings=settings, store=store)
        newer = pgit.commit_tree_with(repo, head, [], "remote advance")
        pgit.push_ref(repo, "origin", newer, "main")
        before = (repo / ".git/index").read_bytes()
        with pytest.raises(ProviderError) as error:
            pull_base(repo, settings=settings, store=store, expect=plan["digest"])
        assert error.value.code == "plan_changed"
        assert git(repo, "rev-parse", "main") == head
        assert git(remote, "rev-parse", "main") == newer
        assert (repo / ".git/index").read_bytes() == before
        current = plan_pull_base(repo, settings=settings, store=store)
        result = pull_base(repo, settings=settings, store=store, expect=current["digest"])
        assert result.updated and result.after == newer
    finally:
        store.close()


BINARY = bytes(range(256))


def test_commit_tree_with_leaves_index_and_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolate_git(monkeypatch)
    repo = make_repo(tmp_path, with_remote=False)
    (repo / "b.txt").write_text("b\n", encoding="utf-8", newline="\n")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-q", "-m", "b")
    (repo / "a.txt").write_text("staged\n", encoding="utf-8", newline="\n")
    git(repo, "add", "a.txt")
    head = git(repo, "rev-parse", "HEAD")
    index = (repo / ".git" / "index").read_bytes()

    blob = pgit.hash_blob(repo, BINARY)
    sha = pgit.commit_tree_with(
        repo, head, [("bin/data", "100644", blob), ("b.txt", None, None)], "msg"
    )

    assert git(repo, "rev-parse", "HEAD") == head
    assert (repo / ".git" / "index").read_bytes() == index
    assert git(repo, "rev-parse", f"{sha}^") == head
    assert git(repo, "show", "--name-status", "--format=", sha).split() == [
        "D",
        "b.txt",
        "A",
        "bin/data",
    ]
    assert pgit.read_blob(repo, git(repo, "rev-parse", f"{sha}:bin/data")) == BINARY
    assert pgit.blob_at(repo, sha, "a.txt") == pgit.blob_at(repo, head, "a.txt")


def test_push_ref_never_forces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolate_git(monkeypatch)
    repo = make_repo(tmp_path, with_remote=True)
    head = git(repo, "rev-parse", "HEAD")
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    unrelated = git(repo, "commit-tree", tree, "-m", "orphan")
    with pytest.raises(ProviderError) as info:
        pgit.push_ref(repo, "origin", unrelated, "main")
    assert info.value.code == "push_failed"
    assert git(tmp_path / "origin.git", "rev-parse", "main") == head
    child = pgit.commit_tree_with(repo, head, [], "empty child")
    pgit.push_ref(repo, "origin", child, "main")
    assert git(tmp_path / "origin.git", "rev-parse", "main") == child


def test_plan_files_and_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolate_git(monkeypatch)
    repo = make_repo(tmp_path, with_remote=False)
    head = git(repo, "rev-parse", "HEAD")
    assert plan_files(repo, head, ["a.txt", "missing"]) == []
    (repo / "a.txt").write_text("changed\n", encoding="utf-8", newline="\n")
    files = plan_files(repo, head, ["a.txt"])
    assert [(f.path, f.action, f.content) for f in files] == [("a.txt", "modify", b"changed\n")]

    digest = plan_digest("main", head, files)
    other = PlannedFile("a.txt", "modify", "100644", "0" * 40, "100644", b"changed\n")
    assert plan_digest("main", head, [other]) != digest
    assert plan_digest("main", "1" * 40, files) != digest
    assert plan_digest("dev", head, files) != digest
    edited = PlannedFile("a.txt", "modify", files[0].old_mode, files[0].old_blob, "100644", b"x")
    assert plan_digest("main", head, [edited]) != digest
    assert plan_digest("main", head, list(files)) == digest
