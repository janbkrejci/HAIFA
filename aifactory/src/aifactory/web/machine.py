"""Global machine checks: read-only views, startup and explicit refreshes.

The view keeps only actionable findings (see ``web.factory.actionable_findings``) and
drops the info ``harness_missing`` of a harness no registered repository uses;
``missing_harnesses`` still names every missing harness.

One check runs as a ``CheckJob`` in its own thread with one time budget
(``CHECK_BUDGET``): every probe and git call of the check gets only the time left
(``procrun.budget``) and a timed-out probe is stopped with its process tree, never
another process. Requests never wait on a lock held during a check: a request joins
a valid running job of the same mode (repeated clicks and other
dashboards share it); only ``fresh`` starts a new job. Otherwise reads return the last
known result (stale after invalidation), or ``checked=False`` when none exists.
Requests joining a job wait at most until the job's
deadline (plus ``RESULT_GRACE``). Past it the view is the last known result, marked
``stale`` with its ``checked_at``, plus ``timed_out`` and the step the check was at; a
timeout is never a success and its partial result is never cached. A job's result
replaces the cache only when no newer job's result is there and the cache was not
invalidated (a library write) since the job started.

The library rules read only local git (no fetch), so a cached read evaluates them again
(``LIBRARY_BUDGET``): a library changed by the CLI or git outside the dashboard never
shows old ahead/behind as current. The expensive probes (harness CLIs, logins, hosting)
run only at server start and for ``fresh``.
"""

from __future__ import annotations

import copy
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aifactory import procrun
from aifactory.check import RULE_GROUPS, Machine, Probe, SystemMachine, run_check
from aifactory.check.context import CheckContext
from aifactory.config.errors import ConfigError
from aifactory.harness import CLI_BINARIES, HARNESSES
from aifactory.harness.check import HarnessStatus, harnesses_in_config
from aifactory.harness.settings import read as read_harness_settings
from aifactory.harness.settings import test_failed
from aifactory.providers import git
from aifactory.web.factory import actionable_findings, is_actionable

_clock = time.monotonic

# Seconds for one whole check. Measured about 1.5 s on macOS (each probe under 0.5 s);
# one probe may take up to its own limit, 15 s (``pi --list-models`` 30 s).
CHECK_BUDGET = 60.0
# Seconds a request waits past the deadline for the job to hand over its result.
RESULT_GRACE = 2.0
# Seconds for the library rules on a cached read (local git only).
LIBRARY_BUDGET = 10.0
# Seconds for the registry part of the view (the roster of each registered repository).
REGISTRY_BUDGET = 10.0


@dataclass
class CachedCheck:
    """A finished check: the report without findings, its findings by part, and when."""

    seq: int
    stamp: float
    report: dict[str, Any]
    findings: list[dict[str, Any]]
    library: list[dict[str, Any]]


@dataclass
class CheckJob:
    """One running check of one mode (``offline``); requests join it instead of queuing."""

    offline: bool
    seq: int
    epoch: int
    budget: float
    started: float
    started_at: str
    step: str = "příprava"
    detail: str | None = None
    done: threading.Event = field(default_factory=threading.Event)
    result: CachedCheck | None = None
    exhausted: bool = False
    error: BaseException | None = None

    @property
    def deadline(self) -> float:
        return self.started + self.budget

    def expired(self) -> bool:
        return _clock() >= self.deadline

    def at(self, step: str) -> None:
        self.step, self.detail = step, None

    def note(self, detail: str) -> None:
        self.detail = detail

    def progress(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "offline": self.offline,
            "step": self.step,
            "detail": self.detail,
            "started_at": self.started_at,
            "elapsed": round(_clock() - self.started, 1),
            "budget": self.budget,
            "running": not self.done.is_set(),
        }


@dataclass
class GlobalState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    checks: dict[bool, CachedCheck] = field(default_factory=dict)
    last_checks: dict[bool, CachedCheck] = field(default_factory=dict)
    # Held only to read or swap ``checks`` and ``jobs``, never while a check runs.
    cache_lock: threading.Lock = field(default_factory=threading.Lock)
    jobs: dict[bool, CheckJob] = field(default_factory=dict)
    seq: int = 0
    epoch: int = 0
    # Per-repository roster results, keyed by freshly read configuration inputs.
    roster_counts: dict[str, tuple[tuple[Any, ...], frozenset[str]]] = field(default_factory=dict)
    roster_lock: threading.Lock = field(default_factory=threading.Lock)
    harness_catalog: dict[str, Any] | None = None
    harness_lock: threading.Lock = field(default_factory=threading.Lock)

    def invalidate(self) -> None:
        with self.cache_lock:
            self.last_checks.update(self.checks)
            self.checks.clear()
            # A job started before this change must not put its result in the cache.
            self.epoch += 1
        with self.harness_lock:
            self.harness_catalog = None

    def progress(self, offline: bool) -> dict[str, Any]:
        """The running check of ``offline`` and when the cached one was made."""
        with self.cache_lock:
            job = self.jobs.get(offline)
            entry = self.checks.get(offline) or self.last_checks.get(offline)
            return {
                "job": job.progress() if job is not None and not job.done.is_set() else None,
                "checked_at": entry.report.get("checked_at") if entry is not None else None,
            }

    def harnesses(self, home: Path, *, fresh: bool = False) -> dict[str, Any]:
        from aifactory.harness.settings import catalog

        with self.harness_lock:
            if self.harness_catalog is None or fresh:
                self.harness_catalog = catalog(home)
            return copy.deepcopy(self.harness_catalog)


@dataclass
class HomeMachine:
    """Delegate probes while binding both environment APIs to the dashboard home."""

    delegate: Machine
    home_dir: Path
    # Told the command or harness a check is about to wait for (the job's progress).
    note: Callable[[str], None] | None = None

    def _waiting(self, what: str) -> float | None:
        """Report ``what``; the seconds left of the check's budget (None: no budget)."""
        if self.note is not None:
            self.note(what)
        return procrun.remaining()

    def environment(self) -> Mapping[str, str]:
        return {**self.delegate.environment(), "HAIFA_HOME": str(self.home_dir)}

    def env(self, name: str) -> str | None:
        return str(self.home_dir) if name == "HAIFA_HOME" else self.delegate.env(name)

    def which(self, program: str) -> str | None:
        choices = read_harness_settings(self.home_dir)
        if choices and any(
            not choices.harnesses[name].enabled and program == (self.delegate.env(env) or binary)
            for name, (env, binary) in CLI_BINARIES.items()
        ):
            return None
        return self.delegate.which(program)

    def run(
        self, argv: Sequence[str], timeout: float = 15, cwd: Path | None = None
    ) -> Probe | None:
        left = self._waiting(" ".join(argv))
        if left is not None and left <= 0:
            return None
        return self.delegate.run(argv, timeout if left is None else min(timeout, left), cwd)

    def harness(self, name: str, agents: Iterable[str]) -> HarnessStatus:
        choices = read_harness_settings(self.home_dir)
        if choices and not choices.harnesses[name].enabled:
            return HarnessStatus(name, CLI_BINARIES[name][1], error="disabled on this computer")
        left = self._waiting(f"{name} --version")
        if left is not None and left <= 0:
            return HarnessStatus(
                name, CLI_BINARIES[name][1], error="the check ran out of time before it"
            )
        return self.delegate.harness(name, agents)

    def home(self) -> Path:
        return self.delegate.home()

    def platform(self) -> str:
        return self.delegate.platform()

    def file_mode(self, path: Path) -> int | None:
        return self.delegate.file_mode(path)


def _registered(home: Path) -> list[Any]:
    """The registered repositories of ``home``; none when the registry is missing or bad."""
    from aifactory.web.registry import RepoError, parse_registry, registry_path

    path = registry_path(home)
    try:
        return list(parse_registry(path.read_text(encoding="utf-8"), str(path))[0].repos)
    except (OSError, UnicodeError, RepoError):
        return []


def outside_repo() -> Path:
    """Find an existing path outside git, even when HAIFA_HOME is in a repo.

    The process's working directory is never used: it may have been deleted since the
    dashboard started (``os.getcwd()`` then fails without naming any file).
    """
    temp = Path(tempfile.gettempdir())
    for path in (temp, Path(temp.anchor)):
        if git.run_bytes(path, ["rev-parse", "--show-toplevel"]).returncode != 0:
            return path
    raise RuntimeError("no outside-repository path available for machine check")


def _library_groups() -> tuple[list[Any], list[Any]]:
    """``RULE_GROUPS`` at call time: (the groups with probes, the library groups)."""
    groups = list(RULE_GROUPS)
    return (
        [g for g in groups if g.scope != "library"],
        [g for g in groups if g.scope == "library"],
    )


def _findings(report: Any) -> list[dict[str, Any]]:
    return [f.to_dict() for f in report.findings]


def _work(job: CheckJob, home: Path, state: GlobalState, machine: Machine | None) -> None:
    """Run the check of ``job`` within its budget and hand the result over."""
    try:
        with procrun.budget(job.deadline - _clock()):
            adapter = HomeMachine(machine or SystemMachine(), home, note=job.note)
            where = outside_repo()
            probes, libraries = _library_groups()
            kwargs: dict[str, Any] = {
                "offline": job.offline,
                "require_repo": False,
                "machine": adapter,
                "progress": job.at,
            }
            report = run_check(where, groups=probes, **kwargs)
            library = run_check(where, groups=libraries, **kwargs)
        job.at("dokončení")
        data = report.to_json()
        data["groups"] = [*data["groups"], *(g.name for g in libraries)]
        data["checked_at"] = datetime.now(UTC).isoformat()
        result = CachedCheck(job.seq, _clock(), data, _findings(report), _findings(library))
        exhausted = job.expired()
    except procrun.BudgetExceeded:
        result, exhausted = None, True
    except BaseException as exc:  # handed to the waiting requests, raised there
        job.error = exc
        result, exhausted = None, False
    with state.cache_lock:
        job.result, job.exhausted = result, exhausted
        # A probe cut short by the spent budget looks like a failure: never cache it.
        if result is not None and not exhausted and job.epoch == state.epoch:
            current = state.checks.get(job.offline)
            if current is None or current.seq < job.seq:
                state.checks[job.offline] = result
        if state.jobs.get(job.offline) is job:
            del state.jobs[job.offline]
        job.done.set()


def _start(
    home: Path, state: GlobalState, offline: bool, machine: Machine | None, budget: float
) -> CheckJob:
    """A new job of ``offline`` (caller holds ``cache_lock``), running in its own thread."""
    state.seq += 1
    job = CheckJob(
        offline=offline,
        seq=state.seq,
        epoch=state.epoch,
        budget=budget,
        started=_clock(),
        started_at=datetime.now(UTC).isoformat(),
    )
    state.jobs[offline] = job
    threading.Thread(
        target=_work, args=(job, home, state, machine), name="machine-check", daemon=True
    ).start()
    return job


def _compose(entry: CachedCheck, library: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The report of ``entry`` with its findings (``library`` replaces the library part)."""
    findings = [*entry.findings, *(entry.library if library is None else library)]
    data = copy.deepcopy(entry.report)
    data["checked"] = True
    data["findings"] = copy.deepcopy(findings)
    counts = dict.fromkeys(data.get("counts") or {}, 0)
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    data["counts"] = counts
    data["ok"] = not counts.get("error")
    return data


def _current_library(home: Path, offline: bool, machine: Machine | None) -> list[dict[str, Any]]:
    """The library findings now (local git only, ``LIBRARY_BUDGET``)."""
    _, libraries = _library_groups()
    with procrun.budget(LIBRARY_BUDGET):
        report = run_check(
            outside_repo(),
            offline=offline,
            require_repo=False,
            machine=HomeMachine(machine or SystemMachine(), home),
            groups=libraries,
        )
    return _findings(report)


def _empty(offline: bool) -> dict[str, Any]:
    """A report with no completed check yet."""
    return {
        "in_repo": False,
        "repo": None,
        "state": None,
        "action": None,
        "base": None,
        "commit": None,
        "remote": None,
        "ahead": None,
        "behind": None,
        "offline": offline,
        "ok": False,
        "counts": {"error": 0, "warning": 0, "info": 0},
        "groups": [],
        "backlog": {},
        "findings": [],
        "checked_at": None,
        "checked": False,
    }


def _message(findings: Sequence[Mapping[str, Any]]) -> str:
    errors = [f for f in findings if f["severity"] == "error"]
    return f"{len(errors)} error(s): " + ", ".join(dict.fromkeys(f["code"] for f in errors))


def check_view(
    home: Path,
    state: GlobalState,
    *,
    offline: bool,
    fresh: bool,
    machine: Machine | None,
    budget: float | None = None,
) -> tuple[dict[str, Any], bool, str]:
    """The machine check view, ok and the error message.

    ``data["timed_out"]`` says the check did not finish within its budget; the data are
    then the last known result (``stale``) and ``progress`` names the unfinished step.
    """
    with state.cache_lock:
        entry = state.checks.get(offline) or state.last_checks.get(offline)
        stale = offline not in state.checks and entry is not None
        job = state.jobs.get(offline)
        # Reads never replace expired or invalidated jobs. Only an explicit refresh
        # can start another check; all valid concurrent requests share it.
        if job is not None and (job.epoch != state.epoch or job.expired()):
            job = None
        if fresh and job is None:
            job = _start(home, state, offline, machine, budget or CHECK_BUDGET)
    timed_out = False
    progress: dict[str, Any] | None = None
    if job is None:
        if entry is None:
            view = {**_empty(offline), "cached": False}
        else:
            try:
                library = _current_library(home, offline, machine)
            except procrun.BudgetExceeded:
                library = None
            view = {
                **_compose(entry, library),
                "cached": True,
                "library_stale": library is None,
                "stale": stale,
            }
            if stale:
                view["ok"] = False
    else:
        finished = job.done.wait(max(0.0, job.deadline - _clock()) + RESULT_GRACE)
        if finished and job.error is not None:
            raise job.error
        if finished and job.result is not None and not job.exhausted:
            with state.cache_lock:
                stale = job.epoch != state.epoch
            view = {**_compose(job.result), "cached": False, "stale": stale}
            if stale:
                view["ok"] = False
        else:
            timed_out = True
            progress = job.progress()
            with state.cache_lock:
                last = state.checks.get(offline) or state.last_checks.get(offline)
            view = _compose(last) if last is not None else _empty(offline)
            view.update(cached=last is not None, stale=True, ok=False)
            view["timed_out"] = True
            view["progress"] = progress
    ok = bool(view["ok"])
    message = _message(view["findings"])
    # Registry changes must be visible even while the machine probes are cached.
    view["harness_repos"] = counts = _harness_repos(home, machine, state)
    # Which harnesses are missing stays known (the roster editor and getting started use
    # it), even when the info finding of a harness no repository uses is not shown.
    missing = [
        name
        for name in HARNESSES
        if any(
            f["code"] == "harness_missing" and f["message"].startswith(f"harness {name} ")
            for f in view["findings"]
        )
    ]
    view["missing_harnesses"] = missing
    choices = read_harness_settings(home)
    if choices:
        for name, choice in choices.harnesses.items():
            if choice.enabled and test_failed(name, choice.model, home):
                view["findings"].append(
                    {
                        "code": "harness_test_failed",
                        "scope": "machine",
                        "severity": "error",
                        "message": f"{name} / {choice.model}: test harnessu selhal.",
                        "fix": "V nastavení harnessů oprav přihlášení nebo model. "
                        "Spusť Test znovu, případně harness vypni.",
                        "action": None,
                    }
                )
                ok = False
        if not ok:
            view["ok"] = False
            rendered_errors = [f for f in view["findings"] if f["severity"] == "error"]
            message = f"{len(rendered_errors)} error(s): " + ", ".join(
                dict.fromkeys(f["code"] for f in rendered_errors)
            )
    if timed_out:
        assert progress is not None
        step = progress["step"] + (f" ({progress['detail']})" if progress["detail"] else "")
        message = f"the check did not finish within {progress['budget']:g} s; unfinished: {step}"
    return actionable_findings(view, lambda f: _needed(f, counts)), ok, message


def _harness_repos(home: Path, machine: Machine | None, state: GlobalState) -> dict[str, int]:
    """How many registered repositories use each harness (``REGISTRY_BUDGET``)."""
    counts = dict.fromkeys(HARNESSES, 0)
    adapter = HomeMachine(machine or SystemMachine(), home)
    with state.roster_lock:
        previous = dict(state.roster_counts)
    current: dict[str, tuple[tuple[Any, ...], frozenset[str]]] = {}
    with procrun.budget(REGISTRY_BUDGET):
        from aifactory.library.inherit import library_head
        from aifactory.library.store import library_root

        try:
            library_key = (str(library_root()), library_head(library_root()))
        except (ConfigError, OSError, procrun.BudgetExceeded):
            return counts
        for repo in _registered(home):
            try:
                context = CheckContext(
                    Path(repo.path), offline=True, machine=adapter, require_repo=False
                )
                if not context.in_repo:
                    continue
                # Base and its commit are read again on every request. Working-tree
                # bytes cover the fallback for an uncommitted/invalid installation;
                # neither timestamps nor a TTL can hide edits or deletions.
                key = (
                    str(context.main),
                    context.base,
                    context.commit,
                    library_key,
                    _roster_files(context.main),
                )
                cached = previous.get(repo.path)
                if cached is not None and cached[0] == key:
                    names = cached[1]
                else:
                    roster = context.roster
                    names = (
                        frozenset(harnesses_in_config(roster))
                        if roster is not None
                        else frozenset()
                    )
                current[repo.path] = (key, names)
                for name in names:
                    counts[name] += 1
            except (ConfigError, OSError, procrun.BudgetExceeded):
                continue
    with state.roster_lock:
        state.roster_counts = current
    return counts


def _roster_files(root: Path) -> tuple[tuple[str, bytes], ...]:
    """All working-tree inputs of load_config, excluding runtime data."""
    files = [root / ".factory" / name for name in ("config.yaml", "agents.yaml", "roles.yaml")]
    for directory in ("prompts", "workflows"):
        files.extend(p for p in (root / ".factory" / directory).rglob("*") if p.is_file())
    return tuple((str(p.relative_to(root)), p.read_bytes()) for p in sorted(files) if p.is_file())


def _needed(finding: Mapping[str, Any], counts: Mapping[str, int]) -> bool:
    """Actionable, and not the info about a missing harness no registered repo uses."""
    if finding["code"] == "harness_missing" and finding["severity"] == "info":
        if any(
            finding["message"].startswith(f"harness {name} ") and not counts.get(name)
            for name in HARNESSES
        ):
            return False
    return is_actionable(finding)
