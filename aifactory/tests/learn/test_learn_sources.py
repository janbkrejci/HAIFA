"""``learn.sources``: objections of every registered repo, and the factory repo."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from aifactory.home import haifa_home
from aifactory.learn.collect import collect
from aifactory.learn.sources import (
    FACTORY_REPO_ENV,
    collect_all,
    factory_repo,
    registered_repos,
    resolve_objections,
)
from learn_fixture import register_learn_repos


@pytest.fixture
def repos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.delenv(FACTORY_REPO_ENV, raising=False)
    return register_learn_repos(tmp_path, "alpha", "beta")


def _make_factory(root: Path) -> None:
    (root / "aifactory").mkdir()
    (root / "aifactory/pyproject.toml").write_text(
        '[project]\nname = "aifactory"\nversion = "1"\n', encoding="utf-8"
    )


def test_registered_repos_lists_every_repo_with_its_trace_db(repos: dict[str, Path]) -> None:
    found, warnings = registered_repos()

    assert warnings == []
    assert [(r.id, r.name, r.path) for r in found] == [
        ("alpha", "alpha", repos["alpha"]),
        ("beta", "beta", repos["beta"]),
    ]
    assert found[0].trace_db == (repos["alpha"] / ".factory/trace.db").resolve()


def test_registered_repos_skips_a_missing_repo_and_one_without_trace_db(
    repos: dict[str, Path], tmp_path: Path
) -> None:
    shutil.rmtree(repos["alpha"])
    (repos["beta"] / ".factory/trace.db").unlink()

    found, warnings = registered_repos(home=haifa_home())

    assert found == []
    assert len(warnings) == 2
    assert warnings[0].startswith("alpha:") and "does not exist" in warnings[0]
    assert warnings[1].startswith("beta:") and "no trace DB" in warnings[1]


def test_collect_all_prefixes_keys_with_the_repo_id(repos: dict[str, Path]) -> None:
    plain = collect(repos["alpha"] / ".factory/trace.db")

    found, warnings = collect_all()

    assert warnings == []
    assert len(found) == 2 * len(plain) == 6
    assert [o.key for o in found if o.repo == "alpha"] == [f"alpha:{o.key}" for o in plain]
    assert [o.key for o in found if o.repo == "beta"] == [f"beta:{o.key}" for o in plain]
    assert len({o.key for o in found}) == len(found)
    assert found[0].to_json()["repo"] == "alpha"
    # the plain read keeps its keys (lessons stored before refer to them)
    assert all(o.repo == "" and o.key.startswith("env-") for o in plain)
    assert plain[0].to_json()["repo"] == ""


def test_collect_all_honours_since(repos: dict[str, Path]) -> None:
    found, _warnings = collect_all(since="2026-10-05T00:00:00")

    assert {o.repo for o in found} == {"alpha", "beta"}
    assert all(o.created_at >= "2026-10-05" for o in found)
    assert len(found) == 4


def test_collect_all_skips_a_broken_repo_with_a_warning(repos: dict[str, Path]) -> None:
    shutil.rmtree(repos["beta"])

    found, warnings = collect_all()

    assert {o.repo for o in found} == {"alpha"}
    assert len(warnings) == 1 and warnings[0].startswith("beta:")


def test_factory_repo_by_project_name(repos: dict[str, Path]) -> None:
    assert factory_repo() is None
    _make_factory(repos["beta"])

    found = factory_repo()

    assert found is not None and found.id == "beta"


def test_factory_repo_ignores_another_project_name(repos: dict[str, Path]) -> None:
    (repos["alpha"] / "aifactory").mkdir()
    (repos["alpha"] / "aifactory/pyproject.toml").write_text(
        '[project]\nname = "other"\n', encoding="utf-8"
    )

    assert factory_repo() is None


def test_factory_repo_from_environment(
    repos: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_factory(repos["beta"])
    monkeypatch.setenv(FACTORY_REPO_ENV, "alpha")

    found = factory_repo()

    assert found is not None and found.id == "alpha"
    monkeypatch.setenv(FACTORY_REPO_ENV, "unknown")
    assert factory_repo() is None


def test_resolve_objections_with_and_without_prefix(repos: dict[str, Path]) -> None:
    plain = collect(repos["alpha"] / ".factory/trace.db")
    keys = [
        plain[0].key,  # no prefix: the origin repo (alpha)
        f"beta:{plain[1].key}",
        f"gone:{plain[0].key}",  # unknown repo
        "beta:env-missing#0",  # unknown key
        "env-missing#0",
    ]

    found = resolve_objections(keys, repos["alpha"])

    assert [(o.key, o.repo, o.text) for o in found] == [
        (plain[0].key, "alpha", plain[0].text),
        (f"beta:{plain[1].key}", "beta", plain[1].text),
    ]


def test_resolve_objections_of_an_unregistered_origin(
    repos: dict[str, Path], tmp_path: Path
) -> None:
    plain = collect(repos["beta"] / ".factory/trace.db")
    gone = tmp_path / "gone"

    assert resolve_objections([plain[0].key], gone) == []
    found = resolve_objections([plain[0].key, f"alpha:{plain[2].key}"], repos["beta"])
    assert [o.repo for o in found] == ["beta", "alpha"]
