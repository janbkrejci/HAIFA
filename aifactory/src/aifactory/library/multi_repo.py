"""Sequential library operations on registered repositories, without a transaction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aifactory.config.errors import ConfigError
from aifactory.home import haifa_home
from aifactory.library.config_edit import execute_plan, plan_config
from aifactory.library.state import repo_items
from aifactory.library.store import LibraryStoreError
from aifactory.library.update import plan_update
from aifactory.providers.base import ProviderError
from aifactory.web.registry import RepoEntry, RepoError, parse_registry, registry_path


def registered_repos(
    selection: str = "all", environ: Mapping[str, str] | None = None
) -> list[RepoEntry]:
    path = registry_path(haifa_home(environ))
    if not path.is_file():
        raise LibraryStoreError("registry_missing", f"repository registry is missing: {path}")
    try:
        state, _ = parse_registry(path.read_text(encoding="utf-8"), str(path))
    except RepoError as exc:
        raise LibraryStoreError(exc.code, exc.message) from exc
    except (OSError, UnicodeError) as exc:
        raise LibraryStoreError("registry_invalid", str(exc)) from exc
    if selection == "all":
        return list(state.repos)
    ids = selection.split(",")
    if any(not id or state.by_id(id) is None for id in ids):
        raise LibraryStoreError("unknown_repo", f"unknown registered repository in {selection!r}")
    return [repo for repo in state.repos if repo.id in ids]


def where(type: str, name: str, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    from aifactory.library.config_edit import _check_type

    _check_type(type, name)
    rows: list[dict[str, Any]] = []
    for repo in registered_repos(environ=environ):
        if not Path(repo.path).is_dir():
            rows.append(
                {"repo": repo.to_json(), "slot": None, "state": "repo_missing", "version": None}
            )
            continue
        try:
            data = repo_items(Path(repo.path), environ=environ, save_cache=False)
            for item in data["items"]:
                if item["type"] == type and (
                    item["item"] == name or (item["item"] is None and item["name"] == name)
                ):
                    rows.append(
                        {
                            "repo": repo.to_json(),
                            "slot": item["name"],
                            "version": item["repo_version"],
                            **item,
                        }
                    )
        except (LibraryStoreError, ProviderError, ConfigError) as exc:
            rows.append(
                {
                    "repo": repo.to_json(),
                    "slot": None,
                    "state": exc.code,
                    "version": None,
                    "error": {"code": exc.code, "message": str(exc)},
                }
            )
    return {"type": type, "name": name, "repos": rows}


def run_repos(
    command: str,
    selection: str,
    *,
    dry_run: bool = False,
    commit: bool = False,
    pr: bool = False,
    expect: Sequence[str] = (),
    message: str | None = None,
    environ: Mapping[str, str] | None = None,
    **options: Any,
) -> dict[str, Any]:
    repos = registered_repos(selection, environ)
    expected: dict[str, str] = {}
    for value in expect:
        id, sep, digest = value.partition("=")
        if not sep or not digest or id in expected or id not in {r.id for r in repos}:
            raise LibraryStoreError("invalid_value", "--expect needs a unique selected ID=DIGEST")
        expected[id] = digest
    if expected and (not commit or dry_run or set(expected) != {r.id for r in repos}):
        raise LibraryStoreError(
            "conflicting_options", "--expect needs --commit and a digest for every selected repo"
        )
    rows: list[dict[str, Any]] = []
    for repo in repos:
        row: dict[str, Any] = {"repo": repo.to_json(), "plan": None, "result": None}
        rows.append(row)
        try:
            if not Path(repo.path).is_dir():
                raise LibraryStoreError(
                    "repo_missing", f"repository folder is missing: {repo.path}"
                )
            if command == "update":
                plan = plan_update(
                    Path(repo.path), commit=commit, pr=pr, environ=environ, **options
                )
            else:
                plan = plan_config(
                    "add", Path(repo.path), commit=commit, pr=pr, environ=environ, **options
                )
            row["plan"] = plan.to_json()
            result = execute_plan(
                plan,
                dry_run=dry_run,
                expect=expected.get(repo.id),
                message=message,
                environ=environ,
            )
            row["result"] = result.to_json()
            row["status"] = "planned" if dry_run else "ok"
        except (LibraryStoreError, ProviderError, ConfigError) as exc:
            row["status"] = exc.code
            row["error"] = {"code": exc.code, "message": str(exc)}
            row["result"] = getattr(exc, "data", None)
        except OSError as exc:
            row["status"] = "repo_io_error"
            row["error"] = {"code": "repo_io_error", "message": str(exc)}
    return {
        "command": command,
        "repos": rows,
        "dry_run": dry_run,
        "partial": any(row["status"] not in ("ok", "planned") for row in rows),
    }
