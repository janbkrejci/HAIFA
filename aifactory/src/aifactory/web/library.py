"""Global library API adapters. Core owns git writes and the cross-process flock."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aifactory.library import multi_repo, remote, reseed, store
from aifactory.library.model import ITEM_TYPES
from aifactory.providers import git
from aifactory.providers.base import ProviderError
from aifactory.providers.publish import PlannedFile
from aifactory.web.backlog import UsageError
from aifactory.web.factory import Failure
from aifactory.web.machine import GlobalState

OPTIONS = {
    "init": ("name", "remote"),
    "clone": ("url", "branch"),
    "import": ("path", "type", "name"),
    "seed": ("take",),
}
CONFLICTS = {
    "busy",
    "plan_changed",
    "library_exists",
    "library_missing",
    "library_dirty",
    "library_behind",
    "library_diverged",
    "remote_not_empty",
    "git_identity_missing",
    "no_remote",
    "invalid_library",
    "not_in_seed",
    "invalid_item",
}


@dataclass(frozen=True)
class Request:
    action: str
    options: dict[str, Any]
    digest: str | None = None


def parse_body(body: Mapping[str, Any], *, apply: bool = False) -> Request:
    allowed = {"action", "options", "digest"} if apply else {"action", "options"}
    if set(body) - allowed:
        raise UsageError("unknown request fields")
    action = body.get("action")
    if not isinstance(action, str) or action not in OPTIONS:
        raise UsageError("action must be init, clone, import or seed")
    options = body.get("options", {})
    if not isinstance(options, dict) or set(options) - set(OPTIONS[action]):
        raise UsageError("invalid or unknown options")
    for key, value in options.items():
        if key == "take":
            if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
                raise UsageError("take must be a list of non-empty strings")
        elif not isinstance(value, str) or not value.strip():
            raise UsageError(f"{key} must be a non-empty string")
    required = {"clone": ("url",), "import": ("path", "type")}.get(action, ())
    if any(key not in options for key in required):
        raise UsageError(f"required options: {', '.join(required)}")
    if action == "import" and options["type"] not in ITEM_TYPES:
        raise UsageError("unknown item type")
    digest = body.get("digest")
    if apply and (not isinstance(digest, str) or not digest.strip()):
        raise UsageError("digest must be the non-empty reviewed plan digest")
    return Request(action, dict(options), digest)


def environment(home: Path) -> dict[str, str]:
    return {**os.environ, "HAIFA_HOME": str(home)}


@contextmanager
def errors(*, write: bool = False) -> Iterator[None]:
    try:
        yield
    except (store.LibraryStoreError, ProviderError) as exc:
        code = exc.code
        status = 500
        if code in ("usage_error", "invalid_value"):
            status = 400
        elif code == "outside_home":
            status = 403
        elif code in ("unknown_item", "unknown_version") or (
            code == "library_missing" and not write
        ):
            status = 404
        elif code in CONFLICTS:
            status = 409
        elif code in ("push_failed", "fetch_failed", "clone_failed", "pull_failed"):
            status = 502
        raise Failure(
            code,
            exc.message,
            status,
            data=getattr(exc, "data", None),
            issues=[i.to_dict() for i in getattr(exc, "issues", [])],
        ) from exc


def warnings(data: Mapping[str, Any]) -> list[str]:
    result = []
    if data.get("compatible") is False:
        result.append(
            f"the library needs factory {data['min_factory_version']}, "
            f"installed is {data['factory_version']}"
        )
    if data.get("seed_update_available"):
        result.append(
            "seed_update_available: the installed seed has new versions of "
            f"{', '.join(data['seed_updates'])}; run factory library seed"
        )
    return result


def usage(kind: str, name: str, env: Mapping[str, str]) -> list[dict[str, Any]]:
    try:
        return list(multi_repo.where(kind, name, environ=env)["repos"])
    except store.LibraryStoreError as exc:
        if exc.code == "registry_missing":
            return []
        raise


def status(home: Path) -> tuple[dict[str, Any], list[str]]:
    env = environment(home)
    with errors():
        try:
            data = remote.library_status(fetch=False, environ=env)
        except store.LibraryStoreError as exc:
            if exc.code == "library_missing":
                return {"exists": False}, []
            raise
        items = store.list_items(environ=env)["items"]
        for item in items:
            item["repos"] = usage(item["type"], item["name"], env)
            shown = store.show_item(item["type"], item["name"], environ=env)
            item.update(_metadata(shown))
            item["n"] = next(
                (r["n"] for r in reversed(shown["history"]) if r["version"] == item["version"]),
                None,
            )
            item["repo_count"] = len(
                {row["repo"]["id"] for row in item["repos"] if row.get("slot") is not None}
            )
        return {"exists": True, **data, "items": items}, warnings(data)


def _metadata(shown: Mapping[str, Any]) -> dict[str, Any]:
    """Descriptions come from committed metadata; the dashboard never parses file content."""
    description = None
    for file in shown["files"]:
        text = file["content"]
        if not text or not (
            file["path"].endswith((".yaml", ".yml", ".json")) or file["path"] == "SKILL.md"
        ):
            continue
        if file["path"] == "SKILL.md":
            parts = text.split("---", 2)
            text = parts[1] if len(parts) == 3 and not parts[0].strip() else ""
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError:
            continue
        if isinstance(raw, dict) and isinstance(raw.get("description"), str):
            description = raw["description"]
            break
    return {"purpose": shown.get("purpose"), "description": description}


def detail(home: Path, kind: str, name: str, version: str | None) -> dict[str, Any]:
    env = environment(home)
    with errors():
        shown = store.show_item(kind, name, version, env)
        return {**shown, **_metadata(shown), "repos": usage(kind, name, env)}


def _source(options: Mapping[str, Any], user_home: Path) -> Path:
    path = Path(options["path"]).expanduser()
    if not path.is_absolute():
        path = user_home / path
    # Enforce both the dashboard boundary and the CLI's boundary before reading files.
    store._check_source(path, user_home.resolve())
    store._check_source(path, Path.home().resolve())
    return path


def _probe(root: Path) -> Path:
    path = root.parent
    while not path.is_dir():
        path = path.parent
    return path


def _blocker(exc: store.LibraryStoreError) -> dict[str, Any]:
    return {"code": exc.code, "message": exc.message}


def _observe(root: Path) -> dict[str, Any]:
    if not root.exists():
        return {"occupied": False, "head": None}
    occupied = not root.is_dir() or bool(list(root.iterdir()))
    return {
        "occupied": occupied,
        "head": git.rev_parse(root, "HEAD") if root.is_dir() else None,
        "entries": sorted(p.name for p in root.iterdir()) if root.is_dir() else [],
    }


def _local_blockers(root: Path, env: Mapping[str, str]) -> list[dict[str, Any]]:
    result = []
    data = remote.library_status(fetch=False, environ=env)
    if data["dirty"]:
        result.append({"code": "library_dirty", "message": "the library has uncommitted changes"})
    if data["behind"]:
        code = "library_diverged" if data["ahead"] else "library_behind"
        result.append({"code": code, "message": "the library is behind its known remote"})
    try:
        store.check_identity(root)
    except store.LibraryStoreError as exc:
        result.append(_blocker(exc))
    return result


def _remote_preview(cwd: Path, url: str, branch: str | None) -> dict[str, Any]:
    proc = git.run_bytes(cwd, ["ls-remote", "--symref", "--", url])
    if proc.returncode:
        raise store.LibraryStoreError("clone_failed", f"cannot read remote {git.redact_url(url)}")
    refs: dict[str, str] = {}
    default = None
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        value, sep, ref = line.partition("\t")
        if not sep:
            continue
        if value.startswith("ref: ") and ref == "HEAD":
            default = value[5:].removeprefix("refs/heads/")
        elif not value.startswith("ref: "):
            refs[ref] = value
    selected = branch or default
    oid = refs.get(f"refs/heads/{selected}") if selected else refs.get("HEAD")
    return {"branch": selected, "remote_head": oid, "refs": refs}


def plan(home: Path, user_home: Path, req: Request) -> tuple[dict[str, Any], list[str]]:
    env = environment(home)
    root = store.library_root(env).resolve()
    opts = dict(req.options)
    with errors(write=True):
        data: dict[str, Any] = {
            "action": req.action,
            "library": str(root),
            "head": None,
            "items": [],
            "files": [],
            "blockers": [],
        }
        notes: list[str] = []
        observed = _observe(root)
        if req.action in ("import", "seed"):
            if req.action == "import":
                source = _source(opts, user_home)
                opts["path"] = str(source)
                result = store.import_item(
                    source,
                    opts["type"],
                    opts.get("name"),
                    dry_run=True,
                    environ=env,
                )
            else:
                result = reseed.seed_library(opts.get("take", ()), dry_run=True, environ=env)
            data.update(result.to_json())
            data["core_digest"] = data.pop("digest")
            data["blockers"] = _local_blockers(root, env)
            notes = list(result.warnings)
        else:
            if observed["occupied"]:
                data["blockers"].append(
                    {
                        "code": "library_exists",
                        "message": f"{root} already exists",
                    }
                )
            if req.action == "init":
                try:
                    store.check_identity(_probe(root))
                except store.LibraryStoreError as exc:
                    data["blockers"].append(_blocker(exc))
                seed = store.packaged_seed()
                meta = {
                    "format": store.FORMAT,
                    "id": "<generated on apply>",
                    "name": opts.get("name", "library"),
                    "min_factory_version": None,
                    "seed": store.seed_versions(seed),
                }
                data["metadata"] = {**meta, "generated": ["id"]}
                data["items"] = [
                    store.PlanItem(i.type, i.name, i.version, None, "create").to_json()
                    for i in seed
                ]
                files = [store.NewFile("library.yaml", False, yaml.safe_dump(meta).encode())]
                files += [f for i in seed for f in i.files]
                data["files"] = [
                    PlannedFile(
                        f.path, "create", None, None, store._mode(f.executable), f.data
                    ).to_json()
                    for f in files
                ]
                if "remote" in opts:
                    try:
                        store._check_empty_remote(_probe(root), opts["remote"])
                    except store.LibraryStoreError as exc:
                        if exc.code != "remote_not_empty":
                            raise
                        data["blockers"].append(_blocker(exc))
            else:
                preview = _remote_preview(_probe(root), opts["url"], opts.get("branch"))
                data.update(preview)
                if preview["remote_head"] is None:
                    code = (
                        "clone_failed"
                        if opts.get("branch") and preview["refs"]
                        else "invalid_library"
                    )
                    data["blockers"].append(
                        {"code": code, "message": "remote has no selected commit"}
                    )
        # Raw URL participates in identity, but only its redacted form is returned.
        stable = {
            "domain": "haifa-library-api-plan-v1",
            "action": req.action,
            "options": opts,
            "library": str(root),
            "observed": observed,
            "core_digest": data.get("core_digest"),
            "head": data["head"],
            "remote_head": data.get("remote_head"),
            "branch": data.get("branch"),
            "files": data["files"],
            "items": data["items"],
            "blockers": [b["code"] for b in data["blockers"]],
        }
        data["digest"] = hashlib.sha256(
            json.dumps(
                stable,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
        ).hexdigest()
        data["options"] = {
            k: git.redact_url(v) if k in ("url", "remote") else v for k, v in opts.items()
        }
        return data, notes


@contextmanager
def exclusive(state: GlobalState) -> Iterator[None]:
    if not state.lock.acquire(blocking=False):
        raise Failure("busy", "another library write is running; try again", 409)
    try:
        yield
    finally:
        state.lock.release()


def apply(
    home: Path,
    user_home: Path,
    req: Request,
    state: GlobalState,
) -> tuple[dict[str, Any], list[str]]:
    with exclusive(state), errors(write=True):
        preview, _ = plan(home, user_home, req)
        if req.digest != preview["digest"]:
            raise Failure("plan_changed", "review the changed library plan", 409, data=preview)
        if preview["blockers"]:
            first = preview["blockers"][0]
            raise Failure(first["code"], first["message"], 409, data=preview)
        env = environment(home)
        opts = req.options
        try:
            if req.action == "init":
                result = store.init_library(opts.get("name"), env, remote=opts.get("remote"))
            elif req.action == "clone":
                data = remote.clone_library(opts["url"], opts.get("branch"), env)
                return {**data, "action": req.action, "reviewed_digest": req.digest}, warnings(data)
            elif req.action == "import":
                result = store.import_item(
                    _source(opts, user_home),
                    opts["type"],
                    opts.get("name"),
                    environ=env,
                )
            else:
                result = reseed.seed_library(opts.get("take", ()), environ=env)
            return {
                **result.to_json(),
                "action": req.action,
                "reviewed_digest": req.digest,
            }, list(result.warnings)
        finally:
            state.invalidate()


def sync(home: Path, state: GlobalState, *, push: bool) -> dict[str, Any]:
    with exclusive(state), errors(write=True):
        try:
            fn = remote.push_library if push else remote.pull_library
            return fn(environ=environment(home))
        finally:
            state.invalidate()


def repos_plan(home: Path, body: Mapping[str, Any]) -> dict[str, Any]:
    """Plan through L9 core; each row can be applied through the repository API."""
    from aifactory.web import factory

    factory._keys(body, ("action", "type", "name", "repos", "options"), "keys")
    action = body.get("action")
    if action not in ("add", "update"):
        raise UsageError("action must be add or update")
    kind, name = body.get("type"), body.get("name")
    if kind not in ITEM_TYPES or not isinstance(name, str) or not name.strip():
        raise UsageError("type and name must identify a library item")
    selection = body.get("repos")
    if isinstance(selection, list):
        if not selection or not all(isinstance(v, str) and v.strip() for v in selection):
            raise UsageError("repos must be a non-empty list of registered IDs")
        if any("," in v or v == "all" for v in selection):
            raise UsageError("repos list must contain individual registered IDs")
        selection = ",".join(selection)
    if not isinstance(selection, str) or not selection.strip():
        raise UsageError("repos must be all, comma-separated IDs, or an ID list")
    ids = selection.split(",")
    if any(not v.strip() for v in ids) or len(ids) != len(set(ids)):
        raise UsageError("repos must contain unique non-empty IDs")
    raw = body.get("options", {})
    if not isinstance(raw, dict):
        raise UsageError("options must be a JSON object")
    raw = dict(raw)
    target = raw.pop("target", "base")
    if target not in factory.TARGETS:
        raise UsageError("target must be base or pr")
    allowed = tuple(k for k in factory.OPTIONS[action] if k not in ("type", "name", "item"))
    factory._keys(raw, allowed, "options")
    if action == "add":
        options = factory._options(action, {**raw, "type": kind, "name": name})
    else:
        options = factory._options(action, {**raw, "item": [f"{kind}/{name}"]})
    with factory._core_errors(action):
        data = multi_repo.run_repos(
            action,
            selection,
            dry_run=True,
            commit=True,
            pr=target == "pr",
            environ=environment(home),
            **options,
        )
    for row in data["repos"]:
        preview = row["plan"]
        if preview is not None:
            preview.update(action=action, apply_options=dict(options), apply_target=target)
            if preview.get("blockers"):
                row["status"] = "blocked"
                data["partial"] = True
    return data
