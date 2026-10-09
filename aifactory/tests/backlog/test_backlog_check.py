"""Each validation on a broken copy of the sample: code and file path."""

from __future__ import annotations

from pathlib import Path

from backlog_repo import (
    DOCS,
    ENDPOINT,
    FILTER,
    M01_S01,
    M01_S02,
    T01,
    T02,
    VIEW,
    rewrite,
    sample_repo,
    task_md,
    write,
)

from aifactory.backlog import Issue, check_backlog, load_backlog


def _issues(root: Path) -> list[Issue]:
    return check_backlog(load_backlog(root))


def _only(root: Path, code: str) -> list[Issue]:
    issues = _issues(root)
    found = [i for i in issues if i.code == code]
    assert found, issues
    return found


def test_duplicate_id(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T02, "id: M01-S01-T02", "id: M01-S01-T01")
    [issue] = _only(root, "duplicate_id")
    assert issue.path == T02
    assert T01 in issue.message


def test_duplicate_container_id_points_to_index(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / M01_S02 / "index.md", "id: M01-S02", "id: M01-S01")
    [issue] = _only(root, "duplicate_id")
    assert issue.path == f"{M01_S02}/index.md"


def test_unknown_task_ref(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T02, "depends_on: [M01-S01-T01]", "depends_on: [M01-S01-T99]")
    [issue] = _only(root, "unknown_ref")
    assert issue.path == T02
    assert "M01-S01-T99" in issue.message


def test_unknown_step_ref(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / ENDPOINT, "depends_on: [M01-S01]", "depends_on: [M01-S09]")
    [issue] = _only(root, "unknown_ref")
    assert issue.path == ENDPOINT
    assert "'M01-S09'" in issue.message


def test_unknown_related_ref(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / ENDPOINT, "related: [M02-S01-T01]", "related: [M03]")
    [issue] = _only(root, "unknown_ref")
    assert issue.path == ENDPOINT
    assert "related" in issue.message


def test_task_cycle(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / VIEW, "depends_on: [M01-S01-T01]", "depends_on: [M02-S01-T02]")
    [issue] = _only(root, "cycle")
    assert issue.path == VIEW
    assert issue.message == "dependency cycle: M02-S01-T01 -> M02-S01-T02 -> M02-S01-T01"


def test_task_depends_on_own_step_is_cycle(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T02, "depends_on: [M01-S01-T01]", "depends_on: [M01-S01]")
    [issue] = _only(root, "cycle")
    assert issue.path == f"{M01_S01}/index.md"
    assert "->" in issue.message
    assert "M01-S01-T02" in issue.message


def test_invalid_status(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T02, "status: todo", "status: running")
    [issue] = _only(root, "invalid_status")
    assert issue.path == T02
    assert "'running'" in issue.message


def test_missing_status(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T02, "status: todo\n", "")
    [issue] = _only(root, "missing_field")
    assert issue.path == T02
    assert "'status'" in issue.message


def test_missing_title(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / DOCS, "title: Docs\n", "")
    [issue] = _only(root, "missing_field")
    assert (issue.path, issue.id) == (DOCS, "M01-S02-T02")
    assert "'title'" in issue.message


def test_missing_index_id(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / M01_S02 / "index.md", "id: M01-S02\n", "")
    [issue] = _only(root, "missing_field")
    assert issue.path == f"{M01_S02}/index.md"
    assert "'id'" in issue.message


def test_depends_on_must_be_a_list(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T02, "depends_on: [M01-S01-T01]", "depends_on: M01-S01-T01")
    [issue] = _only(root, "invalid_field")
    assert issue.path == T02
    assert "depends_on" in issue.message


def test_index_writes_must_be_a_list(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / "backlog/M01-core/index.md", "writes: [src/]", "writes: src/")
    [issue] = _only(root, "invalid_field")
    assert issue.path == "backlog/M01-core/index.md"
    backlog = load_backlog(root)
    m01 = backlog.by_id["M01"]
    assert "writes" not in getattr(m01, "defaults", {})


def test_invalid_frontmatter(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    write(root, FILTER, "no header here\n")
    [issue] = _only(root, "invalid_frontmatter")
    assert issue.path == FILTER


def test_missing_index(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    (root / M01_S02 / "index.md").unlink()
    [issue] = _only(root, "missing_index")
    assert issue.path == M01_S02


def test_misplaced_file(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    write(root, "backlog/M01-core/M01-T9.md", task_md("M01-T9"))
    [issue] = _only(root, "misplaced_file")
    assert issue.path == "backlog/M01-core/M01-T9.md"


def test_misplaced_dir(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    write(root, f"{M01_S01}/deeper/x.md", task_md("M01-S01-X"))
    [issue] = _only(root, "misplaced_dir")
    assert issue.path == f"{M01_S01}/deeper"


def test_id_prefix(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    write(root, f"{M01_S01}/other.md", task_md("M01-X-1", status="done"))
    [issue] = _only(root, "id_prefix")
    assert issue.path == f"{M01_S01}/other.md"
    assert "'M01-S01-'" in issue.message


def test_missing_backlog_dir(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    write(root, ".factory/config.yaml", "backlog_dir: nowhere\n")
    [issue] = _only(root, "missing_backlog_dir")
    assert issue.path == "nowhere"


def test_issues_are_sorted(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T02, "status: todo", "status: running")
    rewrite(root / VIEW, "status: todo", "status: failed")
    paths = [i.path for i in _issues(root)]
    assert paths == sorted(paths)
    assert paths == [T02, VIEW]
