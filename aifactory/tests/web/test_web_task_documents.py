"""Task documents in the dashboard: the backlog item, spec and doc, read-only."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from backlog_fixture import A3, git, make_backlog_repo
from starlette.testclient import TestClient

from aifactory.skill import envelope_problems
from aifactory.web import create_app

BASE = "http://127.0.0.1:4700"


def _client(root: Path, tmp_path: Path) -> TestClient:
    return TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=BASE)


def _get(client: TestClient, url: str, status: int = 200) -> Any:
    response = client.get(url)
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def _docs(client: TestClient, task_id: str = A3) -> dict[str, Any]:
    data = _get(client, f"/api/backlog/tasks/{task_id}/documents")["data"]
    assert data["task_id"] == task_id
    return {d["kind"]: d for d in data["documents"]}


def _status(root: Path) -> str:
    return git(root, "status", "--porcelain", "-uall")


def test_task_without_spec_and_doc_lists_only_the_backlog_item(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    before = _status(root)
    docs = _docs(_client(root, tmp_path))
    assert list(docs) == ["backlog", "spec", "doc"]
    item = docs["backlog"]
    assert item["exists"] is True
    assert item["path"] == "backlog/M01-core/S01-model/M01-S01-T03-writer.md"
    assert "Zadání Writer." in item["content"]
    assert docs["spec"] == {
        "kind": "spec",
        "label": "Spec",
        "path": "specs/M01-core/S01-model/M01-S01-T03-writer.md",
        "exists": False,
        "content": None,
        "problem": None,
    }
    assert docs["doc"]["path"] == "docs/M01-core/S01-model/M01-S01-T03-writer.md"
    assert docs["doc"]["exists"] is False
    assert _status(root) == before  # nothing is written


def test_spec_and_doc_are_found_by_task_id(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    for kind, text in (("specs", "# Plán\nKroky."), ("docs", "# Dokumentace\nPopis.")):
        path = root / kind / "M01-core/S01-model/M01-S01-T03-writer.md"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
    docs = _docs(client)
    assert docs["spec"]["exists"] is True
    assert docs["spec"]["content"] == "# Plán\nKroky."
    assert docs["doc"]["content"] == "# Dokumentace\nPopis."


def test_unknown_task_is_404(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    body = _get(_client(root, tmp_path), "/api/backlog/tasks/NOPE/documents", 404)
    assert body["error"]["code"] == "unknown_task"


def test_task_id_in_url_cannot_reach_other_files(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    response = client.get("/api/backlog/tasks/..%2F..%2Fetc%2Fpasswd/documents")
    assert response.status_code == 404
    assert "root:" not in response.text


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_symlink_out_of_repo_or_to_non_markdown_is_not_read(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    secret = tmp_path / "secret.md"
    secret.write_text("TOP SECRET", encoding="utf-8")
    (root / "notes.txt").write_text("plain text", encoding="utf-8")
    folder = "M01-core/S01-model"
    (root / "specs" / folder).mkdir(parents=True)
    (root / "docs" / folder).mkdir(parents=True)
    (root / "specs" / folder / "M01-S01-T03-writer.md").symlink_to(secret)
    (root / "docs" / folder / "M01-S01-T03-writer.md").symlink_to(root / "notes.txt")
    docs = _docs(_client(root, tmp_path))
    assert docs["spec"]["exists"] is False
    assert docs["spec"]["content"] is None
    assert docs["spec"]["problem"] == "outside the repository"
    assert docs["doc"]["exists"] is False
    assert docs["doc"]["content"] is None
    assert docs["doc"]["problem"] == "not a markdown file"
