"""`providers.publish` and its git helpers: commits without a checkout, no forced push."""

from __future__ import annotations

from pathlib import Path

import pytest
from provider_repo import git, isolate_git, make_repo

from aifactory.providers import ProviderError
from aifactory.providers import git as pgit
from aifactory.providers.publish import PlannedFile, plan_digest, plan_files


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
