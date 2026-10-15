"""``merged_at`` of a PR merged at the provider is the provider's merge time."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from aifactory.providers import MERGED, GitProvider, PrStatus, PullRequest
from aifactory.review import flow, sync
from aifactory.review.flow import _Ctx, _record_state
from aifactory.review.sync import SyncResult, _refresh_sync_prs
from aifactory.run.store import TaskPrRow

MERGED_AT = "2026-09-27T11:00:05.000+00:00"
NOW = "2026-10-15T08:00:00.000+00:00"


class _Row:
    branch = "factory/T01-1"

    def request(self) -> PullRequest:
        return PullRequest("7", "url", self.branch, "main", "T01: title")


class _Store:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update_pr(self, branch: str, **fields: Any) -> None:
        self.updates.append({"branch": branch, **fields})

    update_sync_pr = update_pr

    def open_sync_prs(self) -> list[_Row]:
        return [_Row()]


class _Provider:
    def __init__(self, status: PrStatus) -> None:
        self._status = status

    def status(self, pr: PullRequest) -> PrStatus:
        return self._status


def _ctx(store: _Store, status: PrStatus) -> _Ctx:
    provider = cast(GitProvider, _Provider(status))
    return _Ctx(Path("."), cast(Any, None), cast(Any, store), provider)


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flow, "_now", lambda: NOW)
    monkeypatch.setattr(sync, "_now", lambda: NOW)


@pytest.mark.parametrize(("merged_at", "expected"), [(MERGED_AT, MERGED_AT), (None, NOW)])
def test_record_state_uses_provider_merge_time(merged_at: str | None, expected: str) -> None:
    store = _Store()
    status = PrStatus(MERGED, merge_sha="m", merged_at=merged_at)
    _record_state(_ctx(store, status), cast(TaskPrRow, _Row()), status)
    assert store.updates == [
        {"branch": _Row.branch, "state": MERGED, "merged_at": expected, "merge_sha": "m"}
    ]


@pytest.mark.parametrize(("merged_at", "expected"), [(MERGED_AT, MERGED_AT), (None, NOW)])
def test_refresh_sync_prs_uses_provider_merge_time(merged_at: str | None, expected: str) -> None:
    store = _Store()
    status = PrStatus(MERGED, merge_sha="m", merged_at=merged_at)
    result = SyncResult(pr=None, created=False, updated=False)
    _refresh_sync_prs(_ctx(store, status), result)
    assert store.updates == [
        {"branch": _Row.branch, "state": MERGED, "merged_at": expected, "merge_sha": "m"}
    ]
    assert result.warnings == []
