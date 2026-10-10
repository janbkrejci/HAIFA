"""The dashboard ASGI app: ``/api/`` answers in the CLI's JSON envelope, ``/`` is the Vue build.

Endpoints: ``GET /api/health``; ``GET /api/runs?state=&task=&archived=`` (runs and cost
totals; ``archived=1`` lists the archived runs instead of the active ones),
``GET /api/runs/{run_id}`` (phases, gates, envelopes), ``GET /api/runs/{run_id}/events``
(trace events, ``after``/``limit`` cursor) and ``POST /api/runs/{run_id}/stop`` (the same
``stop_run`` as ``factory task stop``); ``POST /api/runs/{run_id}/pause`` and ``.../resume``
call ``pause_run`` and ``resume_run`` of ``factory task pause|resume`` (HTTP 409 when the run
is not running, already paused or not paused). ``POST /api/runs/{run_id}/publish`` is
``factory task publish`` for a succeeded run without a PR (its ``pr_error`` is in the run
summary). ``GET /api/runs/{run_id}/tail?events=&phases=&gates=
&envelopes=&open=&limit=`` returns only what is new since the rowid cursors (``cursors`` of
the detail or of the previous tail); ``open`` lists the phases the client shows as running.
``GET /api/runs/{run_id}/phases/{phase_id}/prompts`` returns the system and user prompt
of one phase from the run's session directory (``null`` for a missing file; ``source:
agent`` and ``legacy: true`` for an older run with only the agent's last prompts).
Archive: ``POST /api/runs/archive-finished`` archives every finished run,
``POST /api/runs/delete-archived`` erases every archived run with its trace,
``POST /api/runs/{run_id}/archive``, ``.../unarchive`` and ``.../delete`` act on one run
(archive refuses a running run, delete a run that is not archived; HTTP 409).
``GET /api/chains`` (``chains.py``) lists the auto-continue chains: their runs with results,
free slots (``max_parallel_runs``), the tasks skipped with their reasons and the tasks that
ran alone. ``POST /api/chains/{chain_id}/dismiss`` erases an ended chain (HTTP 409 while it
runs), its runs stay.

Live updates: ``GET /api/live`` is a Server-Sent Events stream (``live.py``). ``files``
events name changed paths under ``backlog/`` and ``.factory/``, ``trace`` events the runs
and tasks with new trace rows; ``resync`` asks the client to reload its screen.

Backlog: ``GET /api/backlog?status=`` (tree, kanban tasks, workflows, steps),
``GET /api/backlog/names`` (``{levels, names: {id: {title, level}}}`` for every project,
step and task id, the tooltips of codes),
``GET /api/backlog/tasks/{task_id}`` (``factory task show`` plus both link directions) and
``POST /api/backlog/tasks``, ``/api/backlog/tasks/{task_id}/edit`` and ``.../link``, which call
the same core functions as ``factory task add|edit|link``. A write that would break the
backlog is rejected with ``backlog_invalid`` (HTTP 422) and ``error.issues``. Writes stay in
the working tree: ``GET /api/backlog/status`` lists the backlog files not committed to base
(``{base, commit, clean, changes}``, shown on every screen) and ``POST /api/backlog/commit``
commits them all like ``factory backlog commit``.

Run and auto-continue: ``GET /api/backlog/tasks/{task_id}/run-check`` (uncommitted config,
D4, unmet dependencies in base, a running run), ``POST /api/backlog/tasks/{task_id}/run``
(``{note?, force?}``, HTTP 202) starts ``factory task run`` as a separate process
(``launcher.py``); runs of several tasks run concurrently.
``GET /api/backlog/containers/{id}/graph`` returns the tasks of a project or step and
their ``depends_on`` edges, and ``POST /api/backlog/containers/{id}/auto-continue``
(``{mode: on|off|inherit}``) calls ``set_auto_continue`` like ``factory backlog auto-continue``;
``POST /api/backlog/containers/{id}/auto-merge`` likewise calls ``set_auto_merge``
(``factory backlog auto-merge``). The kanban's queue for auto-continue lives in the trace
DB (``task_queue``): ``POST /api/backlog/queue/order`` (``{order: [task ids]}``) saves the
order of ready tasks and ``POST /api/backlog/tasks/{task_id}/auto-exclude``
(``{excluded: bool}``) keeps a task out of auto-continue; ``GET /api/backlog`` returns
``queue_rank`` and ``auto_excluded`` of each task and lists the tasks in queue order.

Projects and steps: ``GET /api/backlog/containers/{id}`` (title, description, own values of
``index.md`` and effective values with their origin: a level or ``.factory/config.yaml``),
``POST /api/backlog/containers`` (``{parent?, id, title, body?}``) and
``POST /api/backlog/containers/{id}/edit`` (``{title?, workflow?, writes?, test?, source?,
target?, specs_dir?, docs_dir?, auto_continue?, clear?}``; ``null`` or ``clear`` removes a
key) call ``add_container`` and ``edit_container`` like ``factory backlog add|edit``.

Review: ``GET /api/review`` (open task PRs with mergeability and costs; ``?done=1``
adds the merged and closed task PRs in ``done``),
``GET /api/review/{task_id}`` (PR body, diff per file, gates and tests, the
reviewer's verdict, runs), ``POST /api/review/{task_id}/approve`` (HTTP 200),
``.../return`` (``{note}``, HTTP 202) and ``.../resolve`` (``{}``, HTTP 202). They call
``approve_task``, ``return_task`` and ``resolve_task`` of ``aifactory.review``, like
``factory task approve|return|resolve``; return and resolve start ``factory task
return|resolve`` as a separate process (``launcher.py``).
Approve sends an Azure approval vote after the final push and before merge;
providers without supported self-approval report reviewed: false.

Settings: ``GET /api/settings`` (the form values of the shared ``.factory/config.yaml`` and
the machine-local ``.factory/local.yaml``, allowed options, problems of the files on disk and
the config status) and ``POST /api/settings`` (``{shared?: {...}, local?: {...}}``, only the
changed keys; ``null`` drops a key). ``local`` carries only ``trace_db``: the dashboard
port is in the registry (D22) and ``local.port`` is ``invalid_value``. Every value is
validated before anything is written; an invalid value is rejected with ``invalid_value``
(HTTP 422) and one ``error.issues`` entry per field (``id`` is the field name). Nothing is
committed and ``local.yaml`` is kept out of git. ``GET /api/config/status`` is
``factory config status``: shared configuration in ``.factory/`` with uncommitted changes
against ``base`` (D4), shown on every screen.

Factory tab (``factory.py``): ``GET /api/factory/check?offline=&fresh=`` is ``factory
check`` plus the registry finding ``trace_db_shared`` (another registered repository uses
the same trace DB); the result is kept 60 s per ``offline`` flag and ``fresh=1`` renews it
(``checked_at``, ``cached``); every answer also carries the base manifest (``manifest``
``{format, written_by}`` or null, ``manifest_error``) and the package ``version``. It
answers HTTP 200 with the CLI envelope: ``ok``, or ``checks_failed`` with the report in
``data``. ``POST /api/factory/plan`` (``{action,
options?, target?}``) only reads and returns the plan with its ``digest`` (``init`` also
``detected`` and ``available``); ``action`` is ``init`` (options ``agents``,
``bind`` ``{agent: {harness, model?, thinking?}}``, ``workflows``, ``base``, ``provider``,
``azure``, ``backlog_dir``, ``specs_dir``, ``docs_dir``), ``update``
(``item``, ``take``, ``merge``, ``migrate``), ``config_commit``, ``add``, ``set``,
``remove``, ``export``, ``revert``, ``onboard`` or ``adopt`` (see factory.py for options);
``target`` is ``base`` (default) or ``pr``. ``POST /api/factory/apply``
(``{action, digest, options?, target?, message?}``) recomputes the plan like
``factory init|update|config commit --commit --expect``: another digest is HTTP
409 ``plan_changed`` with the new plan in ``data``, a blocker HTTP 409 with its code, a
rejected push HTTP 502 ``push_failed``; success is ``{commit, pushed, pr, warnings}``. The
digest does not depend on the target, so a rejected direct push can go as a PR with the
same digest. ``POST /api/config/pull`` is ``factory config pull``. Apply and pull run one
at a time per repository (HTTP 409 ``busy``); apply takes no paths or file contents, any
other body key is ``usage_error``. ``GET /api/factory/items?base=`` returns CLI item states
without writing the cache. ``GET /api/factory/roster`` returns the agents with harness, model
and thinking, ``presets``, ``thinking_levels`` and the step overrides of the workflows
(``workflow_overrides``); ``POST /api/factory/roster`` (``{preset?, agent?, harness?,
model?, thinking?, dry_run}``) is ``factory config roster set`` on the working tree and
returns ``{agents, before, diff, changed, dry_run, comments_preserved}``, an invalid change
is HTTP 422 ``invalid_config``. Export/onboard/adopt share the global library write lock;
adopt writes only the library and rejects PR targets and messages.

Limits: ``GET /api/limits`` (``limits.py``) lists the 5-hour and weekly session limits of
the Claude and Codex subscriptions the repository's harnesses use or this machine has, for
the topbar. The multi-repo app also serves the global ``GET /api/limits`` (no repository:
only the subscriptions available on this machine).

Global library: ``GET /api/machine/check?offline=&fresh=`` caches the outside-repo
CLI check; the server runs it once at start and again only for ``fresh=1``.
``GET /api/library`` returns status without fetch and item metadata with repo counts
(``?items=0``: status only); ``GET /api/library/items/{type}/{name}?version=`` returns
files, history and usage. ``POST /api/library/plan`` and ``/apply`` take
``{action, options?, digest?}`` for init, clone, import and seed. Apply recomputes the
reviewed digest. All writes including ``POST /api/library/pull`` and ``/push`` share
one nonblocking lock. ``POST /api/library/repos-plan`` takes
``{action: add|update, type, name, repos, options?}`` and returns per-repo plans,
digests, apply_options and apply_target for individual Factory apply calls. A blocked
row sets partial=true while preserving the other plans. This route also works in
create_app. See ``library.py`` for validation and core adapters.

More repositories: ``create_multi_app`` serves every repository in ``dashboard.yaml`` of
the HAIFA home (``registry.py``). ``GET /api/health`` (``app: haifa-dashboard``, ``version``,
``home``), ``GET /api/code`` and ``POST /api/restart`` (as above, no repository needed;
not served per repository), ``GET /api/limits`` (the machine's subscriptions),
``GET /api/repos`` (the repositories with ``status`` and the ``factory`` state),
``POST /api/repos`` (``{path}``, idempotent; HTTP 201 when added; registers and installs
factory from the library in one commit, replacing an existing ``.factory/``),
``POST /api/repos/inspect`` (``{path}``, reads only), ``GET /api/repos/{id}/removal`` (what
removing commits, and the repo's own items), ``DELETE /api/repos/{id}`` (``{export?,
uninstall?}``: exports the chosen items, commits the removal of ``.factory/`` and drops the
registry entry) and ``GET``/``POST /api/dashboard/settings`` (``port``, ``home``,
``restart_required``). Choosing the folder to add (``fs.py``): ``GET /api/fs/dirs?path=``
lists the visible subdirectories of a directory under the user's home (default: home) as
``{path, parent, entries: [{name, path, is_git, has_factory}], truncated}``, HTTP 403
``outside_home`` outside it; ``GET /api/fs/pick`` tells ``{available}`` and
``POST /api/fs/pick`` opens the system folder dialog on the server's session and answers
``{path}`` or ``{cancelled: true}`` (``picker_unavailable``, ``picker_busy``,
``picker_timeout``). ``GET /api/overview`` (``overview.py``) tells for every repository what
runs, waits for review and failed and the state of its configuration; it only reads.
Each repository's endpoints above are under
``/api/repos/{id}/`` with the same relative paths (``/health`` excepted) and their own
``/live`` hub; an unknown id gives HTTP 404 ``unknown_repo``, a missing folder HTTP 404
``repo_missing``. Handlers read the repository from the request (``RepoScope``), and
``create_app`` serves one repository the same way under ``/api/``.

Write guard (``guard.py``): every POST, PUT, PATCH and DELETE under ``/api/`` is checked
before the handler. ``Origin``, if sent, must be ``http://<Host>`` and ``Sec-Fetch-Site``, if
sent, ``same-origin``, otherwise HTTP 403 ``cross_origin``; a body that is not
``application/json`` gets HTTP 415 ``unsupported_media_type``. Requests without these headers
(CLI, curl) and a POST without a body pass; GET is not checked.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import BaseRoute, Mount, Route, Router
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from aifactory import __version__
from aifactory.backlog import TaskEditError
from aifactory.codeprint import CodeWatch
from aifactory.config import ConfigError
from aifactory.harness import settings as harness_settings
from aifactory.home import haifa_home
from aifactory.review.errors import ReviewError
from aifactory.run import gitops
from aifactory.run import pause as run_pause
from aifactory.run import stop as run_stop
from aifactory.run.errors import TaskRunError
from aifactory.run.store import is_db_busy
from aifactory.skill.envelope import envelope_fail, envelope_ok
from aifactory.web import backlog, chains, factory, library, machine, review, runs, settings
from aifactory.web import server as web_server
from aifactory.web.fs import FolderPicker, list_dirs
from aifactory.web.guard import StaleCodeMiddleware, WriteGuardMiddleware, is_api_path
from aifactory.web.launcher import Launcher, RunLauncher
from aifactory.web.limits import LimitsSource
from aifactory.web.live import LiveHub
from aifactory.web.overview import Overview
from aifactory.web.registry import Registry, RepoError
from aifactory.web.repos import (
    RepoContext,
    RepoContexts,
    add_repo,
    inspect_repo,
    remove_repo,
    repo_status,
)
from aifactory.web.updates import Updates
from aifactory.web.workflow_advice import AdviceManager

STATIC_DIR = Path(__file__).parent / "static"
"""The frontend build (``just web-build``), shipped inside the package."""

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
_NOT_BUILT = "dashboard frontend is not built; run: just web-build"

APP_NAME = web_server.APP_NAME
REPO_SCOPE_KEY = "haifa.repo"
"""The ASGI scope key under which ``RepoScope`` puts the request's ``RepoContext``."""


def _ctx(request: Request) -> RepoContext:
    ctx: RepoContext = request.scope[REPO_SCOPE_KEY]
    return ctx


def _repo(request: Request) -> Path:
    """The root of the repository the request is for (set by ``RepoScope``)."""
    return _ctx(request).root


_REPO_ERROR_STATUS = {
    "unknown_repo": 404,
    "repo_missing": 404,
    "path_not_found": 404,
    "not_a_directory": 422,
    "not_git": 422,
    "bare_repo": 422,
    "linked_worktree": 422,
    "run_worktree": 422,
    "no_commits": 422,
    "trace_db_shared": 409,
    "library_missing": 409,
    "registry_invalid": 409,
    "invalid_value": 422,
    "outside_home": 403,
    "permission_denied": 403,
    "picker_unavailable": 503,
    "picker_busy": 409,
    "picker_timeout": 504,
    "picker_failed": 502,
    "busy": 409,
    # install and removal (commit on base)
    "run_in_progress": 409,
    "not_on_base": 409,
    "base_behind": 409,
    "base_diverged": 409,
    "dirty_paths": 409,
    "invalid_plan": 422,
    "push_failed": 502,
    "fetch_failed": 502,
    "commit_failed": 500,
    "base_moved": 409,
}


def _repo_error(exc: RepoError) -> JSONResponse:
    body = envelope_fail(exc.code, exc.message, data=exc.data or None)
    return JSONResponse(body, status_code=_REPO_ERROR_STATUS.get(exc.code, 500))


class RepoScope:
    """Put the request's ``RepoContext`` into the scope before the repository's routes."""

    def __init__(self, app: ASGIApp, resolve: Callable[[Scope], Awaitable[RepoContext]]) -> None:
        self.app = app
        self.resolve = resolve

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            ctx = await self.resolve(scope)
        except RepoError as exc:
            await _repo_error(exc)(scope, receive, send)
            return
        scope[REPO_SCOPE_KEY] = ctx
        await self.app(scope, receive, send)


async def code_state(request: Request) -> JSONResponse:
    """Whether the package on disk changed since the dashboard started (``stale``)."""
    watch: CodeWatch = request.app.state.code
    current = await run_in_threadpool(watch.current)
    data = {"stale": current != watch.started, "started": watch.started, "current": current}
    return JSONResponse(envelope_ok(data))


async def restart_dashboard(request: Request) -> JSONResponse:
    """Answer, then replace the server process with a fresh one running the code on disk."""
    restart: Callable[[], None] = request.app.state.restart
    return JSONResponse(envelope_ok({"restarting": True}), background=BackgroundTask(restart))


async def updates_check(request: Request) -> JSONResponse:
    source: Updates = request.app.state.updates
    data = await run_in_threadpool(source.check, request.query_params.get("fresh") == "1")
    return JSONResponse(envelope_ok(data))


async def updates_install(request: Request) -> JSONResponse:
    from aifactory.upgrade import UpgradeError

    source: Updates = request.app.state.updates
    if request.app.state.launcher.running():
        return JSONResponse(
            envelope_fail("runs_active", "Nejdřív nech doběhnout aktivní tasky."), status_code=409
        )
    overview = getattr(request.app.state, "overview", None)
    if overview is not None:
        data, _ = await overview.collect()
        if data["totals"]["running"]:
            return JSONResponse(
                envelope_fail("runs_active", "Nejdřív nech doběhnout aktivní tasky."),
                status_code=409,
            )
    try:
        data = await run_in_threadpool(source.begin)
    except UpgradeError as exc:
        return JSONResponse(envelope_fail(exc.code, exc.message), status_code=409)
    # The fresh release request can take seconds. A run may have started meanwhile;
    # begin now blocks new writes, so check again before scheduling installation.
    newly_running = bool(request.app.state.launcher.running())
    if overview is not None and not newly_running:
        latest, _ = await overview.collect()
        newly_running = bool(latest["totals"]["running"])
    if newly_running:
        source.cancel()
        return JSONResponse(
            envelope_fail("runs_active", "Nejdřív nech doběhnout aktivní tasky."), status_code=409
        )
    return JSONResponse(
        envelope_ok(data),
        status_code=202,
        background=BackgroundTask(source.install, request.app.state.restart),
    )


async def limits(request: Request) -> JSONResponse:
    """Session limits of the subscriptions the repository uses or this machine has."""
    source: LimitsSource = request.app.state.limits
    data = await run_in_threadpool(source.get, _repo(request))
    return JSONResponse(envelope_ok(data))


async def global_limits(request: Request) -> JSONResponse:
    """Session limits of the subscriptions available on this machine (no repository)."""
    source: LimitsSource = request.app.state.limits
    data = await run_in_threadpool(source.get, None)
    return JSONResponse(envelope_ok(data))


async def machine_harnesses(request: Request) -> JSONResponse:
    try:
        home = request.app.state.home
        if request.method == "POST":
            body = await _json_body(request)
            await run_in_threadpool(harness_settings.write, body, home)
            request.app.state.library.invalidate()
        data = await run_in_threadpool(request.app.state.library.harnesses, home)
        return JSONResponse(envelope_ok(data))
    except (ValueError, OSError, backlog.UsageError) as exc:
        return _usage_error(str(exc))


async def machine_harness_test(request: Request) -> JSONResponse:
    from aifactory.harness.probe import test_and_record

    try:
        body = await _json_body(request)
        if (
            not {"harness", "model"} <= set(body) <= {"harness", "model", "thinking"}
            or not all(isinstance(body[key], str) for key in ("harness", "model"))
            or (body.get("thinking") is not None and not isinstance(body["thinking"], str))
        ):
            raise ValueError("give harness and model strings")
        result = await run_in_threadpool(
            test_and_record,
            body["harness"],
            body["model"],
            request.app.state.home,
            body.get("thinking"),
        )
        request.app.state.library.invalidate()
        return JSONResponse(envelope_ok(result))
    except (ValueError, OSError, backlog.UsageError) as exc:
        return _usage_error(str(exc))


async def health(request: Request) -> JSONResponse:
    repo: Path = _repo(request)
    return JSONResponse(envelope_ok({"version": __version__, "repo": str(repo)}))


_RUN_ERROR_STATUS = {
    "unknown_run": 404,
    "unknown_phase": 404,
    "run_not_running": 409,
    "run_already_paused": 409,
    "run_not_paused": 409,
    "run_running": 409,
    "run_not_archived": 409,
    "unknown_chain": 404,
    "chain_running": 409,
    "invalid_status": 400,
    "invalid_value": 400,
    "trace_db_locked": 503,
    "already_running": 409,
    "unmet_dependencies": 409,
    "task_not_in_base": 409,
    "no_writes": 422,
    "no_workflow": 422,
    "unknown_workflow": 422,
    "invalid_workflow": 422,
    "unknown_task": 404,
    "worktree_failed": 500,
    "no_pr": 404,
    "pr_not_open": 409,
    "conflict": 409,
    "dirty_worktree": 409,
    "branch_checked_out": 409,
    "missing_note": 400,
    "merge_failed": 502,
    "unknown_base": 500,
    "invalid_config": 500,
}


DB_BUSY = "trace_db_locked"
DB_BUSY_MESSAGE = (
    "the trace DB is busy with other runs and stayed locked while we waited; try again"
)


def _db_busy() -> JSONResponse:
    """A trace DB that stayed locked through the whole wait: HTTP 503, retry later."""
    return JSONResponse(envelope_fail(DB_BUSY, DB_BUSY_MESSAGE), status_code=503)


def _run_error(exc: TaskRunError | ConfigError) -> JSONResponse:
    if isinstance(exc, ConfigError):
        return JSONResponse(envelope_fail("invalid_config", str(exc)), status_code=500)
    if is_db_busy(exc):
        return _db_busy()
    status = _RUN_ERROR_STATUS.get(exc.code, 500)
    return JSONResponse(envelope_fail(exc.code, exc.message), status_code=status)


def _int_param(request: Request, name: str, default: int) -> int:
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise HTTPException(400, f"{name} must be an integer, got {raw!r}") from None


def list_runs(request: Request) -> JSONResponse:
    repo: Path = _repo(request)
    try:
        data, warnings = runs.list_runs(
            repo,
            state=request.query_params.get("state") or None,
            task=request.query_params.get("task") or None,
            archived=request.query_params.get("archived") in ("1", "true"),
        )
    except (TaskRunError, ConfigError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


def runs_totals(request: Request) -> JSONResponse:
    repo: Path = _repo(request)
    try:
        data, warnings = runs.run_totals(repo)
    except (TaskRunError, ConfigError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


def list_chains(request: Request) -> JSONResponse:
    repo: Path = _repo(request)
    try:
        data, warnings = chains.list_chains(repo)
    except (TaskRunError, ConfigError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


def dismiss_chain(request: Request) -> JSONResponse:
    """Erase one ended chain: ``{dismissed: chain_id}``."""
    try:
        data = chains.dismiss_chain(_repo(request), request.path_params["chain_id"])
    except (TaskRunError, ConfigError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data))


def run_detail(request: Request) -> JSONResponse:
    repo: Path = _repo(request)
    try:
        data, warnings = runs.run_detail(repo, request.path_params["run_id"])
    except (TaskRunError, ConfigError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


def run_phase_prompts(request: Request) -> JSONResponse:
    repo: Path = _repo(request)
    try:
        data, warnings = runs.phase_prompts(
            repo, request.path_params["run_id"], request.path_params["phase_id"]
        )
    except (TaskRunError, ConfigError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


def run_events(request: Request) -> JSONResponse:
    repo: Path = _repo(request)
    after = _int_param(request, "after", 0)
    limit = _int_param(request, "limit", runs.DEFAULT_EVENTS_LIMIT)
    try:
        data = runs.run_events(repo, request.path_params["run_id"], after=after, limit=limit)
    except (TaskRunError, ConfigError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data))


_MAX_OPEN = 50
_PING_S = 15.0


def run_tail(request: Request) -> JSONResponse:
    """New events, phases, gates and envelopes of a run since the rowid cursors."""
    repo: Path = _repo(request)
    raw_open = request.query_params.get("open") or ""
    open_phases = [p for p in (x.strip() for x in raw_open.split(",")) if p][:_MAX_OPEN]
    events_after = _int_param(request, "events", 0)
    phases_after = _int_param(request, "phases", 0)
    gates_after = _int_param(request, "gates", 0)
    envelopes_after = _int_param(request, "envelopes", 0)
    limit = _int_param(request, "limit", runs.DEFAULT_EVENTS_LIMIT)
    try:
        data = runs.run_tail(
            repo,
            request.path_params["run_id"],
            events_after=events_after,
            phases_after=phases_after,
            gates_after=gates_after,
            envelopes_after=envelopes_after,
            open_phases=open_phases,
            limit=limit,
        )
    except (TaskRunError, ConfigError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data))


def _sse(kind: str, data: dict[str, Any]) -> str:
    return f"event: {kind}\ndata: {json.dumps(data)}\n\n"


async def live(request: Request) -> StreamingResponse:
    """Server-Sent Events: ``hello``, then ``files``/``trace``/``resync`` as they happen."""
    hub: LiveHub = _ctx(request).live

    async def stream() -> AsyncIterator[str]:
        queue = await hub.subscribe()
        try:
            yield "retry: 2000\n\n"
            yield _sse("hello", {"interval": hub.interval})
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_PING_S)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                if event is None:
                    return
                yield _sse(event.kind, event.data)
        finally:
            hub.unsubscribe(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def stop_run(request: Request) -> JSONResponse:
    """Stop a running run with ``aifactory.run.stop.stop_run``, as ``factory task stop`` does."""
    repo: Path = _repo(request)
    run_id: str = request.path_params["run_id"]
    try:
        result = run_stop.stop_run(repo, run_id)
        summary = runs.run_summary(repo, run_id)
    except (TaskRunError, ConfigError) as exc:
        return _run_error(exc)
    data = {"run": summary, "signalled": result.signalled, "killed": result.killed}
    return JSONResponse(envelope_ok(data))


def _paused(repo: Path, run_id: str) -> dict[str, Any]:
    run_pause.pause_run(repo, run_id)
    return {"run": runs.run_summary(repo, run_id)}


def _resumed(repo: Path, run_id: str) -> dict[str, Any]:
    run_pause.resume_run(repo, run_id)
    return {"run": runs.run_summary(repo, run_id)}


def pause_run(request: Request) -> JSONResponse:
    """Ask a running run to pause before its next phase, as ``factory task pause`` does."""
    return _run_action(request, _paused)


def resume_run(request: Request) -> JSONResponse:
    """Let a paused run go on with its next phase, as ``factory task resume`` does."""
    return _run_action(request, _resumed)


async def publish_run(request: Request) -> JSONResponse:
    """``factory task publish`` for a succeeded run without a PR: ``{run, pr, pr_error}``."""
    repo: Path = _repo(request)
    try:
        data, warnings = await run_in_threadpool(
            runs.publish_run, repo, request.path_params["run_id"]
        )
    except (ReviewError, TaskRunError, ConfigError) as exc:
        return _review_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


def _run_action(request: Request, action: Any) -> JSONResponse:
    repo: Path = _repo(request)
    try:
        data = action(repo, request.path_params["run_id"])
    except (TaskRunError, ConfigError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data))


def archive_run(request: Request) -> JSONResponse:
    """Archive one finished run: ``{run}``."""
    return _run_action(request, lambda repo, run_id: {"run": runs.archive_run(repo, run_id)})


def unarchive_run(request: Request) -> JSONResponse:
    """Return one archived run to the active ones: ``{run}``."""
    return _run_action(request, lambda repo, run_id: {"run": runs.unarchive_run(repo, run_id)})


def delete_run(request: Request) -> JSONResponse:
    """Erase one archived run and its trace: ``{deleted: [run_id]}``."""
    return _run_action(request, runs.delete_run)


def archive_finished(request: Request) -> JSONResponse:
    """Archive every finished run: ``{archived: [run_id, ...]}``."""
    try:
        data = runs.archive_finished(_repo(request))
    except (TaskRunError, ConfigError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data))


def delete_archived(request: Request) -> JSONResponse:
    """Erase every archived run and its trace: ``{deleted: [run_id, ...]}``."""
    try:
        data = runs.delete_archived(_repo(request))
    except (TaskRunError, ConfigError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data))


_EDIT_ERROR_STATUS = {
    "unknown_workflow_advice": 404,
    "busy": 409,
    "backlog_invalid": 422,
    "unknown_task": 404,
    "unknown_step": 404,
    "missing_backlog_dir": 404,
    "file_exists": 409,
    "duplicate_id": 409,
    "write_failed": 500,
    "unknown_container": 404,
    "no_index": 409,
    "invalid_value": 400,
    "not_on_base": 409,
    "invalid_config": 500,
    "commit_failed": 500,
    "push_failed": 502,
}


def _edit_error(exc: TaskEditError | ConfigError | TaskRunError) -> JSONResponse:
    if isinstance(exc, ConfigError):
        issues = [
            {"code": "invalid_config", "message": i.message, "path": i.path, "id": None}
            for i in exc.issues
        ]
        return JSONResponse(
            envelope_fail("invalid_config", str(exc), issues=issues), status_code=500
        )
    if isinstance(exc, TaskRunError):
        return _run_error(exc)
    status = _EDIT_ERROR_STATUS.get(exc.code, 400)
    body = envelope_fail(
        exc.code,
        exc.message,
        path=exc.path,
        id=exc.id,
        issues=[i.to_dict() for i in exc.issues],
    )
    return JSONResponse(body, status_code=status)


def _usage_error(message: str) -> JSONResponse:
    return JSONResponse(envelope_fail("usage_error", message), status_code=400)


async def _json_body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    try:
        body = json.loads(raw) if raw else None
    except ValueError:
        raise backlog.UsageError("the request body is not valid JSON") from None
    if not isinstance(body, dict):
        raise backlog.UsageError("the request body must be a JSON object")
    return body


def backlog_list(request: Request) -> JSONResponse:
    repo: Path = _repo(request)
    try:
        data, warnings = backlog.backlog_view(
            repo,
            status=request.query_params.get("status") or None,
        )
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


def backlog_names(request: Request) -> JSONResponse:
    repo: Path = _repo(request)
    try:
        data, warnings = backlog.names(repo)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


def backlog_task(request: Request) -> JSONResponse:
    repo: Path = _repo(request)
    try:
        data, warnings = backlog.task_detail(repo, request.path_params["task_id"])
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def workflow_advice_start(request: Request) -> JSONResponse:
    try:
        body = await _json_body(request)
        data = await run_in_threadpool(
            request.app.state.workflow_advice.start, _repo(request), body
        )
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data), status_code=202)


async def workflow_advice_get(request: Request) -> JSONResponse:
    try:
        data = request.app.state.workflow_advice.get(
            _repo(request), request.path_params["job_id"]
        ).json()
    except TaskEditError as exc:
        return JSONResponse(envelope_fail(exc.code, exc.message), status_code=404)
    return JSONResponse(envelope_ok(data))


async def task_advice_options(request: Request) -> JSONResponse:
    try:
        data = await run_in_threadpool(request.app.state.task_advice.options, _repo(request))
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data))


async def task_advice_start(request: Request) -> JSONResponse:
    try:
        data = await run_in_threadpool(
            request.app.state.task_advice.start, _repo(request), await _json_body(request)
        )
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data), status_code=202)


async def task_advice_get(request: Request) -> JSONResponse:
    try:
        data = request.app.state.task_advice.get(
            _repo(request), request.path_params["job_id"]
        ).json()
    except TaskEditError as exc:
        return JSONResponse(envelope_fail(exc.code, exc.message), status_code=404)
    return JSONResponse(envelope_ok(data))


async def backlog_add(request: Request) -> JSONResponse:
    """Create a task with ``aifactory.backlog.add_task``, as ``factory task add`` does."""
    repo: Path = _repo(request)
    try:
        body = await _json_body(request)
        if "workflow_advice_id" in body:
            data, warnings = await run_in_threadpool(
                backlog.add, repo, body, advice=request.app.state.workflow_advice
            )
        else:
            data, warnings = await run_in_threadpool(backlog.add, repo, body)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def backlog_edit(request: Request) -> JSONResponse:
    """Edit a task (and assign its workflow) with ``aifactory.backlog.edit_task``."""
    repo: Path = _repo(request)
    task_id: str = request.path_params["task_id"]
    try:
        body = await _json_body(request)
        if "workflow_advice_id" in body:
            data, warnings = await run_in_threadpool(
                backlog.edit, repo, task_id, body, advice=request.app.state.workflow_advice
            )
        else:
            data, warnings = await run_in_threadpool(backlog.edit, repo, task_id, body)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def backlog_link(request: Request) -> JSONResponse:
    """Add or remove links of a task with ``aifactory.backlog.link_task``."""
    repo: Path = _repo(request)
    task_id: str = request.path_params["task_id"]
    try:
        body = await _json_body(request)
        data, warnings = await run_in_threadpool(backlog.link, repo, task_id, body)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def backlog_status(request: Request) -> JSONResponse:
    """Backlog files not committed to base (runs read base)."""
    repo: Path = _repo(request)
    try:
        data, warnings = await run_in_threadpool(backlog.status, repo)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def backlog_commit(request: Request) -> JSONResponse:
    """Commit the backlog changes to base with ``aifactory.backlog.commit_backlog``."""
    repo: Path = _repo(request)
    try:
        body = await _json_body(request)
        data, warnings = await run_in_threadpool(backlog.commit, repo, body)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def backlog_run_check(request: Request) -> JSONResponse:
    """Warnings before a run: uncommitted config (D4), unmet dependencies, a running run."""
    repo: Path = _repo(request)
    launcher: Launcher = request.app.state.launcher
    task_id: str = request.path_params["task_id"]
    try:
        data, warnings = await run_in_threadpool(
            backlog.run_check, repo, task_id, launcher_busy=launcher.busy()
        )
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def backlog_run(request: Request) -> JSONResponse:
    """Start ``factory task run`` as a separate process; HTTP 202."""
    repo: Path = _repo(request)
    launcher: Launcher = request.app.state.launcher
    task_id: str = request.path_params["task_id"]
    try:
        body = await _json_body(request)
        data, warnings = await run_in_threadpool(backlog.start_run, repo, task_id, body, launcher)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings), status_code=202)


async def backlog_graph(request: Request) -> JSONResponse:
    """The dependency graph of a module or step."""
    repo: Path = _repo(request)
    try:
        data, warnings = await run_in_threadpool(
            backlog.container_graph, repo, request.path_params["container_id"]
        )
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


def backlog_container(request: Request) -> JSONResponse:
    repo: Path = _repo(request)
    try:
        data, warnings = backlog.container_detail(repo, request.path_params["container_id"])
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def backlog_container_add(request: Request) -> JSONResponse:
    """Create a project or step with ``aifactory.backlog.add_container`` (``backlog add``)."""
    repo: Path = _repo(request)
    try:
        body = await _json_body(request)
        data, warnings = await run_in_threadpool(backlog.add_container, repo, body)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def backlog_container_edit(request: Request) -> JSONResponse:
    """Edit a project or step with ``aifactory.backlog.edit_container`` (``backlog edit``)."""
    repo: Path = _repo(request)
    container_id: str = request.path_params["container_id"]
    try:
        body = await _json_body(request)
        data, warnings = await run_in_threadpool(backlog.edit_container, repo, container_id, body)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def backlog_auto_continue(request: Request) -> JSONResponse:
    """Set auto-continue of a module or step with ``aifactory.backlog.set_auto_continue``."""
    repo: Path = _repo(request)
    container_id: str = request.path_params["container_id"]
    try:
        body = await _json_body(request)
        data, warnings = await run_in_threadpool(backlog.auto_continue, repo, container_id, body)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def backlog_queue_order(request: Request) -> JSONResponse:
    """Save the kanban's order of ready tasks for auto-continue (trace DB ``task_queue``)."""
    repo: Path = _repo(request)
    try:
        body = await _json_body(request)
        data, warnings = await run_in_threadpool(backlog.queue_order, repo, body)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def backlog_auto_exclude(request: Request) -> JSONResponse:
    """Exclude a task from auto-continue, or include it again (``{excluded: bool}``)."""
    repo: Path = _repo(request)
    task_id: str = request.path_params["task_id"]
    try:
        body = await _json_body(request)
        data, warnings = await run_in_threadpool(backlog.auto_exclude, repo, task_id, body)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def backlog_auto_merge(request: Request) -> JSONResponse:
    """Set auto-merge of a module or step with ``aifactory.backlog.set_auto_merge``."""
    repo: Path = _repo(request)
    container_id: str = request.path_params["container_id"]
    try:
        body = await _json_body(request)
        data, warnings = await run_in_threadpool(backlog.auto_merge, repo, container_id, body)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (TaskEditError, ConfigError, TaskRunError) as exc:
        return _edit_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


_REVIEW_ERROR_STATUS = {
    "no_pr": 404,
    "unknown_task": 404,
    "unknown_run": 404,
    "no_succeeded_run": 409,
    "pr_exists": 409,
    "invalid_value": 400,
    "unknown_branch": 409,
    "pr_not_open": 409,
    "conflict": 409,
    "already_running": 409,
    "dirty_worktree": 409,
    "branch_checked_out": 409,
    "missing_note": 400,
    "merge_failed": 502,
    "unknown_base": 500,
    "invalid_config": 500,
    "worktree_failed": 500,
}


def _review_error(exc: ReviewError | TaskRunError | ConfigError) -> JSONResponse:
    if not isinstance(exc, ReviewError):
        return _run_error(exc)
    status = _REVIEW_ERROR_STATUS.get(exc.code, 500)
    return JSONResponse(envelope_fail(exc.code, exc.message), status_code=status)


async def review_list(request: Request) -> JSONResponse:
    """Open task PRs."""
    repo: Path = _repo(request)
    try:
        done = request.query_params.get("done", "").strip().lower() in ("1", "true", "yes")
        data, warnings = await run_in_threadpool(review.review_list, repo, done)
    except (ReviewError, TaskRunError, ConfigError) as exc:
        return _review_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def review_detail(request: Request) -> JSONResponse:
    """The task's newest PR with its diff, gates and tests, verdict and runs."""
    repo: Path = _repo(request)
    try:
        data, warnings = await run_in_threadpool(
            review.review_detail, repo, request.path_params["task_id"]
        )
    except (ReviewError, TaskRunError, ConfigError) as exc:
        return _review_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def review_approve(request: Request) -> JSONResponse:
    """``approve_task`` (``factory task approve``), including Azure's approval vote."""
    repo: Path = _repo(request)
    try:
        data, warnings = await run_in_threadpool(
            review.approve, repo, request.path_params["task_id"]
        )
    except (ReviewError, TaskRunError, ConfigError) as exc:
        return _review_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def review_return(request: Request) -> JSONResponse:
    """``factory task return`` as a separate process; HTTP 202."""
    repo: Path = _repo(request)
    launcher: Launcher = request.app.state.launcher
    task_id: str = request.path_params["task_id"]
    try:
        body = await _json_body(request)
        data, warnings = await run_in_threadpool(review.start_return, repo, task_id, body, launcher)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (ReviewError, TaskRunError, ConfigError) as exc:
        return _review_error(exc)
    return JSONResponse(envelope_ok(data, warnings), status_code=202)


async def review_resolve(request: Request) -> JSONResponse:
    """``factory task resolve`` as a separate process; HTTP 202."""
    repo: Path = _repo(request)
    launcher: Launcher = request.app.state.launcher
    task_id: str = request.path_params["task_id"]
    try:
        body = await _json_body(request)
        data, warnings = await run_in_threadpool(
            review.start_resolve, repo, task_id, body, launcher
        )
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except (ReviewError, TaskRunError, ConfigError) as exc:
        return _review_error(exc)
    return JSONResponse(envelope_ok(data, warnings), status_code=202)


def _settings_error(exc: settings.SettingsError) -> JSONResponse:
    body = envelope_fail(exc.code, exc.message, issues=exc.issues)
    return JSONResponse(body, status_code=422)


async def settings_get(request: Request) -> JSONResponse:
    """Shared and local settings for the Settings form."""
    repo: Path = _repo(request)
    try:
        data, warnings = await run_in_threadpool(settings.settings_view, repo)
    except (ConfigError, TaskRunError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def settings_save(request: Request) -> JSONResponse:
    """Validate and write ``.factory/config.yaml`` / ``.factory/local.yaml`` (all or nothing)."""
    repo: Path = _repo(request)
    try:
        body = await _json_body(request)
        data, warnings = await run_in_threadpool(settings.save_settings, repo, body)
    except (backlog.UsageError, settings.UsageError) as exc:
        return _usage_error(exc.message)
    except settings.SettingsError as exc:
        return _settings_error(exc)
    except (ConfigError, TaskRunError) as exc:
        return _run_error(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def config_status(request: Request) -> JSONResponse:
    """``factory config status``: uncommitted shared config against base (D4)."""
    repo: Path = _repo(request)
    try:
        root = await run_in_threadpool(gitops.main_root, repo)
    except TaskRunError as exc:
        return _run_error(exc)
    data, warnings = await run_in_threadpool(settings.config_status, root)
    if data is None:
        return JSONResponse(envelope_fail("invalid_config", "; ".join(warnings)), status_code=500)
    return JSONResponse(envelope_ok(data, warnings))


# ── Factory tab ──────────────────────────────────────────────────────────────────

_TRUE = ("1", "true", "yes")
_FALSE = ("", "0", "false", "no")


def _flag(request: Request, name: str) -> bool:
    raw = request.query_params.get(name)
    if raw is None or raw.lower() in _FALSE:
        return False
    if raw.lower() in _TRUE:
        return True
    raise HTTPException(400, f"{name} must be 1 or 0, got {raw!r}")


def _failure(exc: factory.Failure) -> JSONResponse:
    body = envelope_fail(exc.code, exc.message, data=exc.data, issues=exc.issues)
    return JSONResponse(body, status_code=exc.status)


async def factory_check(request: Request) -> JSONResponse:
    """``factory check`` of the repository (60 s cache, ``fresh=1``); HTTP 200 either way."""
    ctx = _ctx(request)
    offline, fresh = _flag(request, "offline"), _flag(request, "fresh")
    registry: Registry | None = getattr(request.app.state, "registry", None)
    try:
        reg_state = None
        if registry is not None:
            reg_state = (await run_in_threadpool(registry.snapshot))[0]
        data, ok, message = await run_in_threadpool(
            lambda: factory.check_view(
                ctx.root,
                ctx.factory,
                offline=offline,
                fresh=fresh,
                machine=request.app.state.check_machine,
                registry_state=reg_state,
            )
        )
    except factory.Failure as exc:
        return _failure(exc)
    except RepoError as exc:
        return _repo_error(exc)
    if ok:
        return JSONResponse(envelope_ok(data))
    return JSONResponse(envelope_fail("checks_failed", message, data=data))


async def factory_items(request: Request) -> JSONResponse:
    """CLI item states against the working tree or the requested base."""
    try:
        data = await run_in_threadpool(
            factory.items,
            _ctx(request).root,
            base=request.query_params.get("base"),
            environ=library.environment(request.app.state.home),
        )
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data))


async def factory_roster(request: Request) -> JSONResponse:
    try:
        data = await run_in_threadpool(factory.roster, _ctx(request).root)
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data))


async def factory_roster_set(request: Request) -> JSONResponse:
    """``factory config roster set`` on the working tree; ``dry_run`` previews the diff."""
    ctx = _ctx(request)
    try:
        change = factory.parse_roster_body(await _json_body(request))
        if change.dry_run:
            data = await run_in_threadpool(factory.roster_change, ctx.root, change)
        else:
            with factory.exclusive(ctx.factory):
                data = await run_in_threadpool(factory.roster_change, ctx.root, change, ctx.factory)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except RepoError as exc:
        return _repo_error(exc)
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data))


async def factory_item_diff(request: Request) -> JSONResponse:
    try:
        data = await run_in_threadpool(
            factory.item_diff,
            _ctx(request).root,
            request.query_params.get("type", ""),
            request.query_params.get("name", ""),
            library.environment(request.app.state.home),
        )
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data))


async def library_repos_plan(request: Request) -> JSONResponse:
    """Read-only add/update plans for registered repositories."""
    try:
        data = await run_in_threadpool(
            library.repos_plan, request.app.state.home, await _json_body(request)
        )
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data))


async def factory_plan(request: Request) -> JSONResponse:
    """The core plan of a Factory operation with its digest; reads only."""
    ctx = _ctx(request)
    try:
        req = factory.parse_plan_body(await _json_body(request))
        data, warnings = await run_in_threadpool(
            factory.plan, ctx.root, req, environ=library.environment(request.app.state.home)
        )
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def factory_apply(request: Request) -> JSONResponse:
    """Recompute the plan and commit it to base or a PR when the digest still matches."""
    ctx = _ctx(request)
    try:
        req = factory.parse_apply_body(await _json_body(request))
        with factory.exclusive(ctx.factory):
            if req.action in ("export", "onboard", "adopt"):
                with library.exclusive(request.app.state.library):
                    try:
                        data, warnings = await run_in_threadpool(
                            factory.apply,
                            ctx.root,
                            req,
                            ctx.factory,
                            environ=library.environment(request.app.state.home),
                        )
                    finally:
                        request.app.state.library.invalidate()
            else:
                data, warnings = await run_in_threadpool(
                    factory.apply,
                    ctx.root,
                    req,
                    ctx.factory,
                    environ=library.environment(request.app.state.home),
                )
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except RepoError as exc:
        return _repo_error(exc)
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def config_pull_plan(request: Request) -> JSONResponse:
    ctx = _ctx(request)
    try:
        data, warnings = await run_in_threadpool(factory.pull_plan, ctx.root)
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def config_pull(request: Request) -> JSONResponse:
    """``factory config pull``: fast-forward the local base to the remote base."""
    ctx = _ctx(request)
    try:
        body = await _json_body(request)
        factory._keys(body, ("digest",), "keys")
        digest = body.get("digest")
        if not isinstance(digest, str) or not digest.strip():
            raise backlog.UsageError("digest must be the non-empty digest of the reviewed plan")
        with factory.exclusive(ctx.factory):
            data, warnings = await run_in_threadpool(
                factory.pull, ctx.root, ctx.factory, digest=digest
            )
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except RepoError as exc:
        return _repo_error(exc)
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def frontend_missing(request: Request) -> PlainTextResponse:
    return PlainTextResponse(_NOT_BUILT, status_code=503)


def _is_api(request: Request) -> bool:
    return is_api_path(request.url.path)


async def _http_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, HTTPException)
    if _is_api(request):
        if exc.status_code == 404:
            code, message = "not_found", f"no API endpoint {request.method} {request.url.path}"
        else:
            code, message = "usage_error", f"HTTP {exc.status_code}: {exc.detail}"
        return JSONResponse(
            envelope_fail(code, message),
            status_code=exc.status_code,
            headers=exc.headers,
        )
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code, headers=exc.headers)


async def _internal_error(request: Request, exc: Exception) -> Response:
    if _is_api(request) and is_db_busy(exc):
        return _db_busy()
    if _is_api(request):
        message = f"{type(exc).__name__}: {exc}"
        return JSONResponse(envelope_fail("internal_error", message), status_code=500)
    return PlainTextResponse("Internal Server Error", status_code=500)


def _repo_routes() -> list[BaseRoute]:
    """The API of one repository (every endpoint but ``/health``), relative to its prefix."""
    return [
        Route("/limits", limits, methods=["GET"]),
        Route("/runs", list_runs, methods=["GET"]),
        Route("/runs/totals", runs_totals, methods=["GET"]),
        Route("/chains", list_chains, methods=["GET"]),
        Route("/chains/{chain_id}/dismiss", dismiss_chain, methods=["POST"]),
        Route("/runs/archive-finished", archive_finished, methods=["POST"]),
        Route("/runs/delete-archived", delete_archived, methods=["POST"]),
        Route("/runs/{run_id}", run_detail, methods=["GET"]),
        Route("/runs/{run_id}/events", run_events, methods=["GET"]),
        Route("/runs/{run_id}/tail", run_tail, methods=["GET"]),
        Route(
            "/runs/{run_id}/phases/{phase_id}/prompts",
            run_phase_prompts,
            methods=["GET"],
        ),
        Route("/live", live, methods=["GET"]),
        Route("/runs/{run_id}/stop", stop_run, methods=["POST"]),
        Route("/runs/{run_id}/pause", pause_run, methods=["POST"]),
        Route("/runs/{run_id}/resume", resume_run, methods=["POST"]),
        Route("/runs/{run_id}/publish", publish_run, methods=["POST"]),
        Route("/runs/{run_id}/archive", archive_run, methods=["POST"]),
        Route("/runs/{run_id}/unarchive", unarchive_run, methods=["POST"]),
        Route("/runs/{run_id}/delete", delete_run, methods=["POST"]),
        Route("/backlog", backlog_list, methods=["GET"]),
        Route("/backlog/names", backlog_names, methods=["GET"]),
        Route("/backlog/task-advice/options", task_advice_options, methods=["GET"]),
        Route("/backlog/task-advice", task_advice_start, methods=["POST"]),
        Route("/backlog/task-advice/{job_id}", task_advice_get, methods=["GET"]),
        Route("/backlog/workflow-advice", workflow_advice_start, methods=["POST"]),
        Route("/backlog/workflow-advice/{job_id}", workflow_advice_get, methods=["GET"]),
        Route("/backlog/tasks", backlog_add, methods=["POST"]),
        Route("/backlog/status", backlog_status, methods=["GET"]),
        Route("/backlog/commit", backlog_commit, methods=["POST"]),
        Route("/backlog/tasks/{task_id}", backlog_task, methods=["GET"]),
        Route("/backlog/tasks/{task_id}/edit", backlog_edit, methods=["POST"]),
        Route("/backlog/tasks/{task_id}/link", backlog_link, methods=["POST"]),
        Route("/backlog/tasks/{task_id}/run-check", backlog_run_check, methods=["GET"]),
        Route("/backlog/tasks/{task_id}/run", backlog_run, methods=["POST"]),
        Route("/backlog/tasks/{task_id}/auto-exclude", backlog_auto_exclude, methods=["POST"]),
        Route("/backlog/queue/order", backlog_queue_order, methods=["POST"]),
        Route("/backlog/containers", backlog_container_add, methods=["POST"]),
        Route("/backlog/containers/{container_id}", backlog_container, methods=["GET"]),
        Route(
            "/backlog/containers/{container_id}/edit",
            backlog_container_edit,
            methods=["POST"],
        ),
        Route("/backlog/containers/{container_id}/graph", backlog_graph, methods=["GET"]),
        Route(
            "/backlog/containers/{container_id}/auto-continue",
            backlog_auto_continue,
            methods=["POST"],
        ),
        Route(
            "/backlog/containers/{container_id}/auto-merge",
            backlog_auto_merge,
            methods=["POST"],
        ),
        Route("/review", review_list, methods=["GET"]),
        Route("/review/{task_id}", review_detail, methods=["GET"]),
        Route("/review/{task_id}/approve", review_approve, methods=["POST"]),
        Route("/review/{task_id}/return", review_return, methods=["POST"]),
        Route("/review/{task_id}/resolve", review_resolve, methods=["POST"]),
        Route("/settings", settings_get, methods=["GET"]),
        Route("/settings", settings_save, methods=["POST"]),
        Route("/config/status", config_status, methods=["GET"]),
        Route("/config/pull", config_pull, methods=["POST"]),
        Route("/config/pull/plan", config_pull_plan, methods=["GET"]),
        Route("/factory/check", factory_check, methods=["GET"]),
        Route("/factory/items", factory_items, methods=["GET"]),
        Route("/factory/roster", factory_roster, methods=["GET"]),
        Route("/factory/roster", factory_roster_set, methods=["POST"]),
        Route("/factory/item-diff", factory_item_diff, methods=["GET"]),
        Route("/factory/plan", factory_plan, methods=["POST"]),
        Route("/factory/apply", factory_apply, methods=["POST"]),
    ]


def _starlette(
    api: Mount,
    static_dir: Path | None,
    lifespan: Callable[[Starlette], Any],
    allowed_hosts: Sequence[str] = ALLOWED_HOSTS,
) -> Starlette:
    """The app around the ``/api`` mount: static build, middleware, error handlers.

    ``allowed_hosts`` are the accepted Host headers (``["*"]`` on a network address).
    """
    static = STATIC_DIR if static_dir is None else static_dir
    routes: list[BaseRoute] = [api]
    if (static / "index.html").is_file():
        routes.append(Mount("/", app=StaticFiles(directory=static, html=True), name="static"))
    else:
        routes.append(Route("/", frontend_missing))
    return Starlette(
        routes=routes,
        lifespan=lifespan,
        middleware=[
            Middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts)),
            Middleware(WriteGuardMiddleware),
            Middleware(StaleCodeMiddleware),
        ],
        exception_handlers={
            HTTPException: _http_error,
            sqlite3.OperationalError: _internal_error,  # answered, not re-raised
            Exception: _internal_error,
        },
    )


def _shared_state(
    app: Starlette,
    launcher: Launcher | None,
    code_watch: CodeWatch | None,
    restart: Callable[[], None] | None,
    limits_source: LimitsSource | None,
) -> None:
    app.state.launcher = launcher if launcher is not None else RunLauncher()
    app.state.code = code_watch if code_watch is not None else CodeWatch()
    app.state.restart = restart if restart is not None else web_server.restart_process
    app.state.updates = Updates()

    def enabled(name: str) -> bool:
        home = getattr(app.state, "home", None)
        choices = harness_settings.read(home)
        if choices:
            choice = choices.harnesses[name]
            return choice.enabled and not harness_settings.test_failed(name, choice.model, home)
        tests = harness_settings.read_tests(home).get(name, {})
        latest: dict[str, Any] = max(tests.values(), key=lambda t: t.get("at", ""), default={})
        return latest.get("ok") is not False

    app.state.limits = limits_source if limits_source is not None else LimitsSource(enabled=enabled)
    app.state.check_machine = None  # factory check: the real machine (tests set a fake)


def create_app(
    repo: Path,
    *,
    static_dir: Path | None = None,
    live_interval: float = 0.5,
    launcher: Launcher | None = None,
    code_watch: CodeWatch | None = None,
    restart: Callable[[], None] | None = None,
    limits_source: LimitsSource | None = None,
    allowed_hosts: Sequence[str] = ALLOWED_HOSTS,
) -> Starlette:
    """The dashboard for the repository at ``repo`` (``static_dir`` overrides the build).

    ``live_interval`` is how often (seconds) ``/api/live`` polls files and the trace DB.
    ``launcher`` starts the runs (default: a ``RunLauncher``, one process per run).
    ``code_watch`` notices a changed package (default: the installed one) and ``restart``
    replaces the server process (default: ``server.restart_process``). ``limits_source``
    reads the subscription limits (default: a ``LimitsSource`` with the real readers).
    ``allowed_hosts`` are the accepted Host headers (``server.allowed_hosts``).
    """
    root = repo.resolve()
    ctx = RepoContext(None, root, LiveHub(root, interval=live_interval))

    async def fixed(scope: Scope) -> RepoContext:
        return ctx

    api = Mount(
        "/api",
        app=RepoScope(
            Router(
                routes=[
                    Route("/health", health, methods=["GET"]),
                    Route("/code", code_state, methods=["GET"]),
                    Route("/restart", restart_dashboard, methods=["POST"]),
                    Route("/updates", updates_check, methods=["GET"]),
                    Route("/updates/install", updates_install, methods=["POST"]),
                    Route("/library/repos-plan", library_repos_plan, methods=["POST"]),
                    *_repo_routes(),
                ]
            ),
            fixed,
        ),
    )

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await run_in_threadpool(app.state.workflow_advice.close)
            await run_in_threadpool(app.state.task_advice.close)
            await app.state.live.aclose()

    app = _starlette(api, static_dir, lifespan, allowed_hosts)
    app.state.workflow_advice = AdviceManager()
    app.state.task_advice = AdviceManager(task_parameters=True)
    app.state.home = haifa_home()
    app.state.library = machine.GlobalState()
    app.state.repo = root
    app.state.live = ctx.live
    _shared_state(app, launcher, code_watch, restart, limits_source)
    return app


# ── more repositories ────────────────────────────────────────────────────────────────


def _registry(request: Request) -> Registry:
    registry: Registry = request.app.state.registry
    return registry


async def multi_health(request: Request) -> JSONResponse:
    data = {"app": APP_NAME, "version": __version__, "home": str(request.app.state.home)}
    return JSONResponse(envelope_ok(data))


async def repos_list(request: Request) -> JSONResponse:
    """The registered repositories with their status and factory state."""
    registry = _registry(request)

    def build() -> tuple[list[dict[str, Any]], list[str]]:
        state, warnings = registry.snapshot()
        return [repo_status(entry) for entry in state.repos], warnings

    items, warnings = await run_in_threadpool(build)
    data = {"repos": items, "home": str(request.app.state.home)}
    return JSONResponse(envelope_ok(data, warnings))


def _path_body(body: dict[str, Any]) -> object:
    unknown = sorted(set(body) - {"path"})
    if unknown:
        raise backlog.UsageError(f"unknown keys: {', '.join(unknown)}")
    return body.get("path")


async def repos_add(request: Request) -> JSONResponse:
    """Add a repository: register it and install factory from the library in one commit
    (``web.repos.add_repo``). HTTP 201 when newly registered, 200 when it was there."""
    registry = _registry(request)

    def work(raw: object) -> tuple[dict[str, Any], bool, dict[str, Any], list[str]]:
        entry, created, install, warnings = add_repo(
            registry, raw, library.environment(request.app.state.home)
        )
        return repo_status(entry), created, install, warnings

    try:
        raw = _path_body(await _json_body(request))
        item, created, install, warnings = await run_in_threadpool(work, raw)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except RepoError as exc:
        return _repo_error(exc)
    body = envelope_ok({"repo": item, "created": created, "install": install}, warnings)
    return JSONResponse(body, status_code=201 if created else 200)


async def repos_removal(request: Request) -> JSONResponse:
    """What removing the repository commits, and its own items the library could keep."""
    registry = _registry(request)
    repo_id: str = request.path_params["repo_id"]

    def work() -> dict[str, Any]:
        from aifactory.library.store import LibraryStoreError
        from aifactory.library.uninstall import plan_uninstall

        entry = registry.snapshot()[0].by_id(repo_id)
        if entry is None:
            raise RepoError("unknown_repo", f"no registered repository {repo_id!r}")
        try:
            return plan_uninstall(
                Path(entry.path), library.environment(request.app.state.home)
            ).to_json()
        except LibraryStoreError as exc:
            raise RepoError(exc.code, exc.message) from exc

    try:
        data = await run_in_threadpool(work)
    except RepoError as exc:
        return _repo_error(exc)
    return JSONResponse(envelope_ok(data))


async def repos_inspect(request: Request) -> JSONResponse:
    """What adding a folder would do; reads only, writes nothing anywhere."""
    registry = _registry(request)

    def work(raw: object) -> tuple[dict[str, Any], list[str]]:
        state, warnings = registry.snapshot()
        return inspect_repo(raw, state), warnings

    try:
        raw = _path_body(await _json_body(request))
        data, warnings = await run_in_threadpool(work, raw)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    return JSONResponse(envelope_ok(data, warnings))


async def repos_remove(request: Request) -> JSONResponse:
    """Remove a repository: export the chosen items (``export: [{type, name}]``) to the
    library, commit the removal of ``.factory/`` (``uninstall: false`` skips it), drop the
    registry entry and close its live hub."""
    registry = _registry(request)
    repo_id: str = request.path_params["repo_id"]
    contexts: RepoContexts = request.app.state.repos
    try:
        payload = await _json_body(request) if await request.body() else {}
        uninstall = payload.get("uninstall", True)
        raw_export = payload.get("export") or []
        if not isinstance(uninstall, bool):
            raise backlog.UsageError("uninstall must be a boolean")
        if not isinstance(raw_export, list) or not all(
            isinstance(e, dict) and all(isinstance(e.get(k), str) for k in ("type", "name"))
            for e in raw_export
        ):
            raise backlog.UsageError("export must be a list of {type, name}")
        export = [(str(e["type"]), str(e["name"])) for e in raw_export]
        environ = library.environment(request.app.state.home)
        entry, done = await run_in_threadpool(
            lambda: remove_repo(
                registry, repo_id, export=export, uninstall=uninstall, environ=environ
            )
        )
        await contexts.drop(repo_id)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except RepoError as exc:
        return _repo_error(exc)
    return JSONResponse(envelope_ok({"removed": entry.to_json(), "uninstall": done}))


async def fs_dirs(request: Request) -> JSONResponse:
    """The visible subdirectories of ``?path=`` under the user's home; reads only."""
    home: Path = request.app.state.user_home
    try:
        data = await run_in_threadpool(list_dirs, request.query_params.get("path"), home)
    except RepoError as exc:
        return _repo_error(exc)
    return JSONResponse(envelope_ok(data))


async def fs_pick_status(request: Request) -> JSONResponse:
    """Whether ``POST /api/fs/pick`` can open a dialog; opens nothing."""
    picker: FolderPicker = request.app.state.picker
    return JSONResponse(envelope_ok({"available": picker.available()}))


async def fs_pick(request: Request) -> JSONResponse:
    """Open the native folder dialog on a worker thread: ``{path}`` or ``{cancelled}``."""
    picker: FolderPicker = request.app.state.picker
    try:
        data = await run_in_threadpool(picker.pick)
    except RepoError as exc:
        return _repo_error(exc)
    return JSONResponse(envelope_ok(data))


def _dashboard_settings(request: Request, port: int) -> dict[str, Any]:
    served: int | None = request.app.state.served_port
    return {
        "port": port,
        "home": str(request.app.state.home),
        "registry": str(_registry(request).path),
        "restart_required": served is not None and port != served,
    }


async def dashboard_settings_get(request: Request) -> JSONResponse:
    """The dashboard port from the registry and whether a restart would change it."""
    state, warnings = await run_in_threadpool(_registry(request).snapshot)
    return JSONResponse(envelope_ok(_dashboard_settings(request, state.port), warnings))


def _port_value(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise RepoError(
            "invalid_value",
            f"port must be an integer from 1 to 65535, got {value!r}",
        )
    return value


async def dashboard_settings_save(request: Request) -> JSONResponse:
    """Store the dashboard port (``{port}``); it applies from the next start."""
    registry = _registry(request)
    try:
        body = await _json_body(request)
        unknown = sorted(set(body) - {"port"})
        if unknown:
            raise backlog.UsageError(f"unknown keys: {', '.join(unknown)}")
        if "port" in body:
            state = await run_in_threadpool(registry.set_port, _port_value(body["port"]))
            warnings: list[str] = []
        else:
            state, warnings = await run_in_threadpool(registry.snapshot)
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except RepoError as exc:
        if exc.code == "invalid_value":
            issues = [{"code": "invalid_value", "message": exc.message, "path": None, "id": "port"}]
            body = envelope_fail(exc.code, exc.message, issues=issues)
            return JSONResponse(body, status_code=422)
        return _repo_error(exc)
    return JSONResponse(envelope_ok(_dashboard_settings(request, state.port), warnings))


async def overview_get(request: Request) -> JSONResponse:
    """What runs, waits for review and failed in every registered repository (reads only)."""
    ov: Overview = request.app.state.overview
    data, warnings = await ov.collect()
    return JSONResponse(envelope_ok(data, warnings))


async def machine_check(request: Request) -> JSONResponse:
    offline, fresh = _flag(request, "offline"), _flag(request, "fresh")
    data, ok, message = await run_in_threadpool(
        machine.check_view,
        request.app.state.home,
        request.app.state.library,
        offline=offline,
        fresh=fresh,
        machine=request.app.state.check_machine,
    )
    return JSONResponse(
        envelope_ok(data)
        if ok
        else envelope_fail(
            "checks_failed",
            message,
            data=data,
        )
    )


async def library_get(request: Request) -> JSONResponse:
    try:
        items = "items" not in request.query_params or _flag(request, "items")
        data, warnings = await run_in_threadpool(
            library.status, request.app.state.home, items=items
        )
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def library_item(request: Request) -> JSONResponse:
    try:
        data = await run_in_threadpool(
            library.detail,
            request.app.state.home,
            request.path_params["type"],
            request.path_params["name"],
            request.query_params.get("version"),
        )
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data))


async def library_plan(request: Request) -> JSONResponse:
    try:
        req = library.parse_body(await _json_body(request))
        data, warnings = await run_in_threadpool(
            library.plan,
            request.app.state.home,
            request.app.state.user_home,
            req,
        )
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def library_apply(request: Request) -> JSONResponse:
    try:
        req = library.parse_body(await _json_body(request), apply=True)
        data, warnings = await run_in_threadpool(
            library.apply,
            request.app.state.home,
            request.app.state.user_home,
            req,
            request.app.state.library,
        )
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data, warnings))


async def library_sync(request: Request) -> JSONResponse:
    try:
        body = await _json_body(request) if await request.body() else {}
        if body:
            raise backlog.UsageError("pull and push accept no options")
        data = await run_in_threadpool(
            library.sync,
            request.app.state.home,
            request.app.state.library,
            push=request.url.path.endswith("/push"),
        )
    except backlog.UsageError as exc:
        return _usage_error(exc.message)
    except factory.Failure as exc:
        return _failure(exc)
    return JSONResponse(envelope_ok(data))


def create_multi_app(
    *,
    home: Path | None = None,
    port: int | None = None,
    static_dir: Path | None = None,
    live_interval: float = 0.5,
    launcher: Launcher | None = None,
    code_watch: CodeWatch | None = None,
    restart: Callable[[], None] | None = None,
    limits_source: LimitsSource | None = None,
    user_home: Path | None = None,
    picker: FolderPicker | None = None,
    allowed_hosts: Sequence[str] = ALLOWED_HOSTS,
    background_checks: bool = False,
) -> Starlette:
    """The dashboard for every repository in the registry of ``home`` (default: HAIFA home).

    ``port`` is the port the server listens on (``restart_required`` compares it with the
    registry). Each repository's API is under ``/api/repos/{repo_id}/`` with the same paths
    as ``create_app`` serves under ``/api/``. ``user_home`` (default: the user's home) bounds
    ``/api/fs/dirs`` and ``picker`` opens the folder dialog of ``/api/fs/pick``; the other
    arguments are as in ``create_app``.
    """
    home_dir = haifa_home() if home is None else home
    registry = Registry(home_dir)
    contexts = RepoContexts(registry, live_interval)

    async def resolve(scope: Scope) -> RepoContext:
        return await contexts.resolve(scope["path_params"]["repo_id"])

    api = Mount(
        "/api",
        routes=[
            Route("/health", multi_health, methods=["GET"]),
            Route("/machine/check", machine_check, methods=["GET"]),
            Route("/machine/harnesses", machine_harnesses, methods=["GET", "POST"]),
            Route("/machine/harnesses/test", machine_harness_test, methods=["POST"]),
            Route("/library", library_get, methods=["GET"]),
            Route("/library/items/{type}/{name}", library_item, methods=["GET"]),
            Route("/library/repos-plan", library_repos_plan, methods=["POST"]),
            Route("/library/plan", library_plan, methods=["POST"]),
            Route("/library/apply", library_apply, methods=["POST"]),
            Route("/library/pull", library_sync, methods=["POST"]),
            Route("/library/push", library_sync, methods=["POST"]),
            Route("/code", code_state, methods=["GET"]),
            Route("/restart", restart_dashboard, methods=["POST"]),
            Route("/updates", updates_check, methods=["GET"]),
            Route("/updates/install", updates_install, methods=["POST"]),
            Route("/limits", global_limits, methods=["GET"]),
            Route("/repos", repos_list, methods=["GET"]),
            Route("/repos", repos_add, methods=["POST"]),
            Route("/repos/inspect", repos_inspect, methods=["POST"]),
            Route("/repos/{repo_id}", repos_remove, methods=["DELETE"]),
            Route("/repos/{repo_id}/removal", repos_removal, methods=["GET"]),
            Route("/dashboard/settings", dashboard_settings_get, methods=["GET"]),
            Route("/dashboard/settings", dashboard_settings_save, methods=["POST"]),
            Route("/fs/dirs", fs_dirs, methods=["GET"]),
            Route("/fs/pick", fs_pick_status, methods=["GET"]),
            Route("/fs/pick", fs_pick, methods=["POST"]),
            Route("/overview", overview_get, methods=["GET"]),
            Mount("/repos/{repo_id}", app=RepoScope(Router(routes=_repo_routes()), resolve)),
        ],
    )

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        from aifactory.web.monitoring import once, periodic

        checks: list[asyncio.Task[None]] = []
        if background_checks:
            checks = [
                asyncio.create_task(
                    once(
                        lambda: machine.check_view(
                            app.state.home,
                            app.state.library,
                            offline=False,
                            fresh=True,
                            machine=app.state.check_machine,
                        )
                    )
                ),
                asyncio.create_task(periodic(app.state.updates.check, 60)),
                asyncio.create_task(periodic(lambda: app.state.limits.get(None), 60)),
                asyncio.create_task(
                    periodic(
                        lambda: app.state.library.harnesses(
                            app.state.home,
                            fresh=True,
                        ),
                        300,
                    )
                ),
            ]
        try:
            yield
        finally:
            for check in checks:
                check.cancel()
            await asyncio.gather(*checks, return_exceptions=True)
            await run_in_threadpool(app.state.workflow_advice.close)
            await run_in_threadpool(app.state.task_advice.close)
            await contexts.aclose()

    app = _starlette(api, static_dir, lifespan, allowed_hosts)
    app.state.workflow_advice = AdviceManager()
    app.state.task_advice = AdviceManager(task_parameters=True)
    app.state.library = machine.GlobalState()
    app.state.home = home_dir
    app.state.served_port = port
    app.state.registry = registry
    app.state.overview = Overview(registry)
    app.state.repos = contexts
    app.state.user_home = Path.home() if user_home is None else user_home
    app.state.picker = FolderPicker() if picker is None else picker
    _shared_state(app, launcher, code_watch, restart, limits_source)
    return app
