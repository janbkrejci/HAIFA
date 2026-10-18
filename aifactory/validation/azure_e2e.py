"""``just validate-azure-e2e``: HAIFA end to end on a new, temporary Azure DevOps repo.

The operator runs it by hand, never CI. The repo is created for this run only
(``HAIFA-E2E-<date>-<time>-<hex>``) in the given project; ``main`` gets a branch
policy "minimum 1 reviewer, the author's own vote counts" (``creatorVoteCounts``),
so the only way into base is a pull request with an approval. The scenario then:

1. creates the repo with an initial commit on ``main``;
2. sets the policy and checks that a direct push to ``main`` is refused;
3. clones it and adds it to HAIFA the way ``POST /api/repos`` does (``add_repo``)
   with ``base_changes: pr`` and ``base_pr_merge: auto``: the install goes through
   ``factory-init/<n>``, which factory approves with its own vote and merges;
4. writes a backlog of two dependent tasks with ``auto_continue`` and ``auto_merge``
   (workflow ``build-review``) and runs ``factory backlog commit``: PR
   ``factory-backlog/<n>``, approved and merged by factory;
5. runs ``factory task run <first> --auto`` over the fake harness
   (``validation.fake``, no model is called): each task gets a PR that factory
   approves with its own vote (``reviewed: true``) and that Azure completes under the
   policy without a bypass; the second task starts by itself (``auto-continue``);
6. compares local ``main`` with the remote and reads ``status: done`` and the runs
   of both tasks in the remote base.

Every PR is also read back from Azure (``az repos pr show``): state, merge commit,
the reviewers' votes, the creator's vote and whether a policy bypass was used.

Cleanup runs in ``finally``, also after a failure or Ctrl+C: the repo is removed
from the dashboard registry, its policies are deleted, the repo is deleted and purged
from the project's recycle bin, and the local workdir (clone, worktrees, HAIFA home)
is deleted unless ``--keep-workdir``. Then the repo and the policies are looked up
again; anything left makes the cleanup (and the run) fail. Only the repo this run
created (by its id) is ever deleted, and the name must start with ``HAIFA-E2E-``.

Without ``az``, the ``azure-devops`` extension or a login (``az account show`` or
``AZURE_DEVOPS_EXT_PAT``) the run stops before anything on Azure is touched (exit 2).

The result is ``results/<date>/azure-e2e-<time>/azure-e2e.json``: every step with
ok/failed, its detail, PR URLs, votes and SHAs, the cleanup and the outcome. Exit
codes: 0 passed, 1 failed (a step or the cleanup), 2 preflight.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from validation import results as results_mod
from validation.context import parse_stdout
from validation.results import now_iso, write_json
from validation.safety import Owned, safe_rmtree
from validation.sandbox import (
    AIFACTORY_DIR,
    GIT_EMAIL,
    GIT_NAME,
    VALIDATION_DIR,
    SetupError,
    az_executable,
    azure_credential_helper,
    git,
    git_auth_args,
)
from validation.worker import FAKE_ENV

EXIT_OK, EXIT_FAILED, EXIT_SETUP = 0, 1, 2
DEFAULT_ORG = "https://asolcz.visualstudio.com"
DEFAULT_PROJECT = "NEO_HEF"
NAME_PREFIX = "HAIFA-E2E-"
# repos of the project the scenario must never touch, whatever --name says
PROTECTED_REPOS = frozenset({"neo_hef", "haifa-azure-sandbox"})
BASE = "main"
APPROVED = 10  # Azure DevOps vote "approved"
POLICY_SETTLE_S = 5.0

PROJECT_ID = "E2E"
STEP_ID = "E2E-S01"
TASKS: tuple[tuple[str, str, str, str], ...] = (
    # id, slug, title, file the fake builder writes
    ("E2E-S01-T01", "first", "First file", "src/e2e/first.txt"),
    ("E2E-S01-T02", "second", "Second file", "src/e2e/second.txt"),
)


class Stop(RuntimeError):
    """A step failed in a way the following steps cannot build on."""


# ── report ───────────────────────────────────────────────────────────────────


@dataclass
class Step:
    name: str
    ok: bool
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail, **self.data}


@dataclass
class Report:
    organization: str
    project: str
    repository: str
    started_at: str = field(default_factory=now_iso)
    steps: list[Step] = field(default_factory=list)
    cleanup: list[Step] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    web_url: str | None = None

    def step(self, name: str, ok: bool, detail: str = "", **data: Any) -> bool:
        self.steps.append(Step(name, ok, detail, data))
        mark = "ok" if ok else "FAILED"
        print(f"[azure-e2e] {name}: {mark} {detail}".rstrip(), file=sys.stderr, flush=True)
        return ok

    def clean(self, name: str, ok: bool, detail: str = "") -> None:
        self.cleanup.append(Step(name, ok, detail))
        mark = "ok" if ok else "FAILED"
        print(f"[azure-e2e] cleanup {name}: {mark} {detail}".rstrip(), file=sys.stderr)

    @property
    def steps_ok(self) -> bool:
        return bool(self.steps) and all(s.ok for s in self.steps)

    @property
    def cleanup_ok(self) -> bool:
        return all(s.ok for s in self.cleanup)

    @property
    def outcome(self) -> str:
        return "passed" if self.steps_ok and self.cleanup_ok else "failed"

    def to_json(self) -> dict[str, Any]:
        return {
            "scenario": "azure-e2e",
            "outcome": self.outcome,
            "organization": self.organization,
            "project": self.project,
            "repository": self.repository,
            "web_url": self.web_url,
            "started_at": self.started_at,
            "ended_at": now_iso(),
            "steps": [s.to_json() for s in self.steps],
            "cleanup": {"ok": self.cleanup_ok, "steps": [s.to_json() for s in self.cleanup]},
            "commands": self.commands,
        }


# ── az ───────────────────────────────────────────────────────────────────────


class AzFailed(RuntimeError):
    def __init__(self, argv: list[str], code: int, stderr: str) -> None:
        super().__init__(f"az {' '.join(argv)} failed ({code}): {stderr.strip()}")
        self.stderr = stderr


@dataclass
class Azure:
    organization: str
    project: str
    cwd: Path
    log: list[dict[str, Any]] = field(default_factory=list)

    def raw(self, *args: str, project: bool = True) -> subprocess.CompletedProcess[str]:
        argv = [*args, "--org", self.organization, "--detect", "false"]
        if project:
            argv += ["--project", self.project]
        argv += ["--output", "json", "--only-show-errors"]
        proc = subprocess.run(
            [az_executable(), *argv],
            cwd=self.cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.log.append({"az": argv, "exit": proc.returncode})
        return proc

    def json(self, *args: str, project: bool = True) -> Any:
        proc = self.raw(*args, project=project)
        if proc.returncode != 0:
            raise AzFailed(list(args), proc.returncode, proc.stderr or proc.stdout)
        text = (proc.stdout or "").strip()
        return json.loads(text) if text else None


def _az_ok(*args: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [az_executable(), *args], capture_output=True, text=True, encoding="utf-8"
        )
    except OSError as exc:
        return False, str(exc)
    return proc.returncode == 0, (proc.stderr or proc.stdout).strip()


def preflight(organization: str, project: str, name: str) -> None:
    """az, its extension, the login, the project and git; nothing on Azure is changed."""
    if not name.startswith(NAME_PREFIX) or name.casefold() in PROTECTED_REPOS:
        raise SetupError(f"--name must start with {NAME_PREFIX!r} (got {name!r})")
    if shutil.which("git") is None:
        raise SetupError("git is not on PATH")
    ok, detail = _az_ok("--version")
    if not ok:
        raise SetupError(f"az (Azure CLI) is not installed or does not run: {detail}")
    ok, detail = _az_ok("extension", "show", "--name", "azure-devops", "--output", "json")
    if not ok:
        raise SetupError(
            "the azure-devops extension of az is missing; run: "
            f"az extension add --name azure-devops ({detail})"
        )
    if not os.environ.get("AZURE_DEVOPS_EXT_PAT"):
        ok, detail = _az_ok("account", "show", "--output", "json")
        if not ok:
            raise SetupError(
                "az is not logged in; run 'az login --allow-no-subscriptions' "
                f"or set AZURE_DEVOPS_EXT_PAT ({detail})"
            )
    ok, detail = _az_ok(
        "devops",
        "project",
        "show",
        "--project",
        project,
        "--org",
        organization,
        "--detect",
        "false",
        "--output",
        "json",
    )
    if not ok:
        raise SetupError(f"project {project} of {organization} is not reachable: {detail}")


def repo_name(when: datetime.datetime) -> str:
    return f"{NAME_PREFIX}{when:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


# ── PR evidence ──────────────────────────────────────────────────────────────


def pr_evidence(data: dict[str, Any]) -> dict[str, Any]:
    """What a completed PR proves, from ``az repos pr show``: votes, SHAs, bypass."""
    creator = data.get("createdBy") if isinstance(data.get("createdBy"), dict) else {}
    creator_id = str((creator or {}).get("id") or "")
    reviewers = [r for r in data.get("reviewers") or [] if isinstance(r, dict)]
    votes = [
        {
            "reviewer": r.get("uniqueName") or r.get("displayName"),
            "vote": r.get("vote"),
            "is_creator": str(r.get("id") or "") == creator_id,
        }
        for r in reviewers
    ]
    options = data.get("completionOptions")
    options = options if isinstance(options, dict) else {}
    merge = data.get("lastMergeCommit")
    source = data.get("lastMergeSourceCommit")
    return {
        "pr_id": data.get("pullRequestId"),
        "status": data.get("status"),
        "source_branch": str(data.get("sourceRefName") or "").removeprefix("refs/heads/"),
        "target_branch": str(data.get("targetRefName") or "").removeprefix("refs/heads/"),
        "created_by": (creator or {}).get("uniqueName"),
        "votes": votes,
        "creator_approved": any(v["is_creator"] and v["vote"] == APPROVED for v in votes),
        "bypass_policy": options.get("bypassPolicy") is True,
        "head_sha": source.get("commitId") if isinstance(source, dict) else None,
        "merge_sha": merge.get("commitId") if isinstance(merge, dict) else None,
    }


def pr_accepted(ev: dict[str, Any]) -> tuple[bool, str]:
    """A PR merged into base under the policy: completed, creator vote approve, no bypass."""
    ok = (
        ev.get("status") == "completed"
        and ev.get("target_branch") == BASE
        and ev.get("creator_approved") is True
        and ev.get("bypass_policy") is False
        and bool(ev.get("merge_sha"))
    )
    votes = ", ".join(f"{v['reviewer']}={v['vote']}" for v in ev.get("votes") or []) or "none"
    detail = (
        f"PR {ev.get('pr_id')} {ev.get('status')} into {ev.get('target_branch')}, "
        f"votes [{votes}], bypass {ev.get('bypass_policy')}, merge {ev.get('merge_sha')}"
    )
    return ok, detail


# ── the run ──────────────────────────────────────────────────────────────────


def isolated_home(workdir: Path) -> Path:
    """A HAIFA home with the operator's library, without dashboard and harness choices.

    The dashboard registry (``dashboard.yaml``) is the run's own, so registering and
    unregistering the temporary repo never touches the operator's dashboard.
    """
    from aifactory.web.registry import LOCK_FILE, REGISTRY_FILE
    from validation.runner import isolated_haifa_home

    home = isolated_haifa_home(workdir)
    for name in (REGISTRY_FILE, LOCK_FILE):
        link = home / name
        if link.is_symlink() or link.is_file():
            link.unlink()
    return home


def fake_script() -> dict[str, Any]:
    """Builder and reviewer of ``build-review`` for both tasks of the chain, in order."""
    builds: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    for task_id, _slug, title, path in TASKS:
        builds.append(
            {
                "envelope": {
                    "status": "success",
                    "summary": f"wrote {path}",
                    "changed_files": [path],
                    "commit_message": f"{task_id}: {title}",
                },
                "edits": [{"path": path, "write": f"{task_id}: {title}\n"}],
            }
        )
        reviews.append(
            {
                "envelope": {
                    "status": "success",
                    "summary": f"{task_id}: 1 of 1 requirements met",
                    "approved": True,
                    "blocking": [],
                    "findings": [{"requirement": f"write {path}", "met": True, "evidence": path}],
                },
                "edits": [],
            }
        )
    return {"task": TASKS[0][0], "agents": {"builder": builds, "reviewer": reviews}}


def backlog_files(docs_root: str) -> dict[str, str]:
    """The E2E backlog: one project, one step, two dependent tasks."""
    root = f"{docs_root.rstrip('/')}/backlog/{PROJECT_ID}-azure-e2e"
    step = f"{root}/S01-chain"
    files = {
        f"{root}/index.md": (
            "---\n"
            f"id: {PROJECT_ID}\n"
            "title: Azure E2E\n"
            "workflow: build-review\n"
            "writes: [src/e2e/]\n"
            "auto_continue: true\n"
            "auto_merge: true\n"
            "---\n\n"
            "Temporary backlog of the Azure DevOps end-to-end validation.\n"
        ),
        f"{step}/index.md": f"---\nid: {STEP_ID}\ntitle: Chain\n---\n\nTwo dependent tasks.\n",
    }
    previous: str | None = None
    for task_id, slug, title, path in TASKS:
        depends = f"depends_on: [{previous}]\n" if previous else ""
        files[f"{step}/{task_id}-{slug}.md"] = (
            "---\n"
            f"id: {task_id}\n"
            f"title: {title}\n"
            "status: todo\n"
            f"{depends}"
            "---\n\n"
            f"## Zadání\nCreate `{path}` with one line `{task_id}: {title}`.\n"
        )
        previous = task_id
    return files


def task_path(docs_root: str, task_id: str) -> str:
    return next(p for p in backlog_files(docs_root) if Path(p).name.startswith(f"{task_id}-"))


def front_matter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    loaded = yaml.safe_load(text.split("\n---", 1)[0].removeprefix("---"))
    return loaded if isinstance(loaded, dict) else {}


@dataclass
class Cmd:
    argv: list[str]
    code: int
    data: dict[str, Any]
    log: Path

    @property
    def ok(self) -> bool:
        return self.code == 0 and self.data.get("ok") is True

    @property
    def payload(self) -> dict[str, Any]:
        value = self.data.get("data")
        return value if isinstance(value, dict) else {}

    def brief(self) -> str:
        err = self.data.get("error")
        if isinstance(err, dict):
            return f"exit {self.code}: {err.get('code')}: {err.get('message')}"
        warnings = self.data.get("warnings") or []
        return f"exit {self.code}" + (f", warnings {warnings}" if warnings else "")


@dataclass
class E2E:
    azure: Azure
    report: Report
    workdir: Path
    owned: Owned
    home: Path
    name: str
    repo_id: str | None = None
    remote_url: str | None = None
    policy_ids: list[int] = field(default_factory=list)
    registry_id: str | None = None
    docs_root: str = "factory"
    _n: int = 0

    @property
    def clone(self) -> Path:
        return self.workdir / "repo"

    @property
    def logs(self) -> Path:
        path = self.workdir / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -- helpers --

    def factory(self, *argv: str, script: dict[str, Any] | None = None) -> Cmd:
        """One ``factory`` command through ``validation.worker`` (fake harness with `script`)."""
        self._n += 1
        label = f"{self._n:02d}-" + "-".join(a for a in argv[:2] if not a.startswith("-"))
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(AIFACTORY_DIR), env.get("PYTHONPATH", "")) if p
        )
        env.pop(FAKE_ENV, None)
        if script is not None:
            path = self.logs / f"{label}.script.json"
            path.write_text(json.dumps(script, indent=2), encoding="utf-8", newline="\n")
            env[FAKE_ENV] = str(path)
        full = [*argv, "--repo", str(self.clone), "--json"]
        proc = subprocess.run(
            [sys.executable, "-m", "validation.worker", *full],
            cwd=self.clone,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        log = self.logs / f"{label}.log"
        log.write_text(proc.stderr or "", encoding="utf-8", newline="\n")
        cmd = Cmd(full, proc.returncode, parse_stdout(proc.stdout or ""), log)
        self.report.commands.append({"argv": full, "exit": cmd.code, "brief": cmd.brief()})
        return cmd

    def remote_main(self) -> str:
        out = git(self.clone, *git_auth_args(), "ls-remote", "origin", f"refs/heads/{BASE}")
        return out.split()[0] if out else ""

    def local_main(self) -> str:
        return git(self.clone, "rev-parse", f"refs/heads/{BASE}")

    def pr_by_branch(self, branch: str) -> dict[str, Any]:
        found = self.azure.json(
            "repos",
            "pr",
            "list",
            "--repository",
            self.name,
            "--source-branch",
            branch,
            "--status",
            "all",
        )
        items = [p for p in found or [] if isinstance(p, dict)]
        if not items:
            raise Stop(f"no PR from {branch} on Azure")
        return self.pr_show(int(items[0]["pullRequestId"]))

    def pr_show(self, pr_id: int) -> dict[str, Any]:
        data = self.azure.json("repos", "pr", "show", "--id", str(pr_id), project=False)
        return pr_evidence(data if isinstance(data, dict) else {})

    def pr_url(self, pr_id: object) -> str:
        return f"{self.report.web_url}/pullrequest/{pr_id}"

    def mains_agree(self, name: str) -> bool:
        git(self.clone, "fetch", "-q", "origin", BASE, check=False)
        local, remote = self.local_main(), self.remote_main()
        return self.report.step(
            name,
            bool(local) and local == remote,
            f"local {local}, remote {remote}",
            local_main=local,
            remote_main=remote,
        )

    # -- steps --

    def create_repo(self) -> None:
        data = self.azure.json("repos", "create", "--name", self.name)
        self.repo_id = str(data["id"])
        self.remote_url = str(data["remoteUrl"])
        self.report.web_url = str(data.get("webUrl") or "") or None
        seed = self.workdir / "seed"
        git(self.workdir, "init", "-q", "-b", BASE, str(seed))
        self._identity(seed)
        (seed / "README.md").write_text(
            f"# {self.name}\n\nTemporary repo of the HAIFA Azure E2E validation.\n",
            encoding="utf-8",
            newline="\n",
        )
        git(seed, "add", "-A")
        git(seed, "commit", "-q", "-m", "initial commit")
        git(seed, *git_auth_args(), "push", "-q", self.remote_url, f"HEAD:refs/heads/{BASE}")
        sha = git(seed, "rev-parse", "HEAD")
        remote = git(seed, *git_auth_args(), "ls-remote", self.remote_url, f"refs/heads/{BASE}")
        ok = remote.split()[0] == sha if remote else False
        if not self.report.step(
            "create_repo",
            ok,
            f"{self.name} ({self.repo_id}), main {sha}",
            repo_id=self.repo_id,
            web_url=self.report.web_url,
            main_sha=sha,
        ):
            raise Stop("the initial commit is not on main")

    def set_policy(self) -> None:
        assert self.repo_id is not None and self.remote_url is not None
        data = self.azure.json(
            "repos",
            "policy",
            "approver-count",
            "create",
            "--blocking",
            "true",
            "--enabled",
            "true",
            "--branch",
            BASE,
            "--repository-id",
            self.repo_id,
            "--minimum-approver-count",
            "1",
            "--creator-vote-counts",
            "true",
            "--allow-downvotes",
            "false",
            "--reset-on-source-push",
            "false",
        )
        policy_id = int(data["id"])
        self.policy_ids.append(policy_id)
        settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
        settings = settings or {}
        ok = settings.get("minimumApproverCount") == 1 and settings.get("creatorVoteCounts") is True
        self.report.step(
            "policy_created",
            ok and data.get("isBlocking") is True,
            f"policy {policy_id}: minimumApproverCount {settings.get('minimumApproverCount')}, "
            f"creatorVoteCounts {settings.get('creatorVoteCounts')}",
            policy_id=policy_id,
        )
        time.sleep(POLICY_SETTLE_S)
        seed = self.workdir / "seed"
        (seed / "direct.txt").write_text("a direct push must be refused\n", encoding="utf-8")
        git(seed, "add", "-A")
        git(seed, "commit", "-q", "-m", "direct push")
        proc = subprocess.run(
            ["git", *git_auth_args(), "push", self.remote_url, f"HEAD:refs/heads/{BASE}"],
            cwd=seed,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        lines = [line for line in (proc.stderr or "").splitlines() if line.strip()]
        reason = next(
            (line for line in lines if "TF402455" in line or "policy" in line.lower()),
            lines[-1] if lines else "",
        )
        if not self.report.step(
            "direct_push_refused", proc.returncode != 0, f"exit {proc.returncode}: {reason}"
        ):
            raise Stop("main accepts direct pushes; the policy does not protect it")

    def install(self) -> None:
        from aifactory.web.registry import Registry
        from aifactory.web.repos import add_repo

        assert self.remote_url is not None
        proc = subprocess.run(
            ["git", *git_auth_args(), "clone", "-q", self.remote_url, str(self.clone)],
            cwd=self.workdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            raise Stop(f"git clone: {proc.stderr.strip()}")
        git(self.clone, "config", "credential.helper", "")
        git(self.clone, "config", "--add", "credential.helper", azure_credential_helper())
        self._identity(self.clone)
        before = self.local_main()
        entry, _created, install, warnings = add_repo(
            Registry(self.home), str(self.clone), base_changes="pr", base_pr_merge="auto"
        )
        self.registry_id = entry.id
        pr = install.get("pr") if isinstance(install.get("pr"), dict) else None
        branch = str((pr or {}).get("branch") or "")
        self.report.step(
            "install_pr_opened",
            branch.startswith("factory-init/"),
            f"branch {branch or '-'}, url {(pr or {}).get('url')}, merged {install.get('merged')}, "
            f"warnings {warnings}",
            registry_id=entry.id,
            pr_url=(pr or {}).get("url"),
            branch=branch,
            merged=install.get("merged"),
            commit=install.get("commit"),
        )
        if not branch:
            raise Stop("the install opened no factory-init PR")
        ev = self.pr_by_branch(branch)
        ok, detail = pr_accepted(ev)
        self.report.step(
            "install_pr_self_approved_and_merged",
            ok and install.get("merged") is True,
            detail,
            pr_url=self.pr_url(ev["pr_id"]),
            **ev,
        )
        after = self.local_main()
        config = git(self.clone, "show", f"{BASE}:.factory/config.yaml", check=False)
        settings = yaml.safe_load(config) if config else None
        settings = settings if isinstance(settings, dict) else {}
        self.docs_root = str(settings.get("docs_root") or "factory")
        self.report.step(
            "install_in_local_main",
            after != before
            and after == ev.get("merge_sha")
            and settings.get("base_changes") == "pr"
            and settings.get("base_pr_merge") == "auto"
            and settings.get("git_provider") == "azure",
            f"main {before[:12]} -> {after[:12]}, config base_changes "
            f"{settings.get('base_changes')}, base_pr_merge {settings.get('base_pr_merge')}, "
            f"git_provider {settings.get('git_provider')}",
            local_main=after,
        )
        if not self.mains_agree("install_main_matches_remote"):
            raise Stop("local main does not match the remote after the install")

    def backlog(self) -> None:
        for rel, text in backlog_files(self.docs_root).items():
            path = self.clone / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        check = self.factory("backlog", "check")
        self.report.step("backlog_check", check.ok, check.brief())
        cmd = self.factory("backlog", "commit")
        pr = cmd.payload.get("pr") if isinstance(cmd.payload.get("pr"), dict) else None
        branch = str((pr or {}).get("branch") or "")
        self.report.step(
            "backlog_pr_opened",
            cmd.ok and branch.startswith("factory-backlog/"),
            f"{cmd.brief()}; branch {branch or '-'}, merged {cmd.payload.get('merged')}",
            pr_url=(pr or {}).get("url"),
            branch=branch,
            merged=cmd.payload.get("merged"),
        )
        if not branch:
            raise Stop("backlog commit opened no factory-backlog PR")
        ev = self.pr_by_branch(branch)
        ok, detail = pr_accepted(ev)
        self.report.step(
            "backlog_pr_self_approved_and_merged",
            ok and cmd.payload.get("merged") is True,
            detail,
            pr_url=self.pr_url(ev["pr_id"]),
            **ev,
        )
        files = backlog_files(self.docs_root)
        in_base = [rel for rel in files if _exists(self.clone, f"{BASE}:{rel}")]
        self.report.step(
            "backlog_in_local_main",
            len(in_base) == len(files),
            f"{len(in_base)} of {len(files)} backlog files in main",
        )
        if not self.mains_agree("backlog_main_matches_remote"):
            raise Stop("local main does not match the remote after the backlog commit")

    def chain(self) -> None:
        first = TASKS[0][0]
        cmd = self.factory("task", "run", first, "--auto", script=fake_script())
        chain = cmd.payload.get("chain") if isinstance(cmd.payload.get("chain"), dict) else {}
        chain = chain or {}
        runs = [r for r in chain.get("runs") or [] if isinstance(r, dict)]
        tasks = [str(_d(r.get("run")).get("task_id") or "") for r in runs]
        self.report.step(
            "chain_ran_both_tasks",
            cmd.ok and tasks == [t[0] for t in TASKS] and chain.get("stop") == "exhausted",
            f"{cmd.brief()}; tasks {tasks}; stop {chain.get('stop')}; "
            f"waiting {chain.get('waiting')}",
            chain_id=chain.get("chain_id"),
        )
        rows = _task_runs(self.clone)
        for entry in runs:
            run, pr, merge = _d(entry.get("run")), _d(entry.get("pr")), _d(entry.get("auto_merge"))
            task_id = str(run.get("task_id") or "")
            run_id = str(run.get("run_id") or "")
            self.report.step(
                f"run_{task_id}",
                entry.get("ok") is True and run.get("state") == "succeeded" and bool(pr.get("url")),
                f"run {run_id} {run.get('state')}, PR {pr.get('url')}",
                run_id=run_id,
                pr_url=pr.get("url"),
                branch=pr.get("branch"),
                started_by=rows.get(run_id, {}).get("started_by"),
            )
            self.report.step(
                f"auto_merge_{task_id}",
                merge.get("merged") is True and merge.get("reviewed") is True,
                f"merged {merge.get('merged')}, reviewed {merge.get('reviewed')}, "
                f"code {merge.get('code')}: {merge.get('reason')}",
                merge_sha=merge.get("merge_sha"),
                reviewed=merge.get("reviewed"),
            )
            branch = str(pr.get("branch") or "")
            if branch:
                ev = self.pr_by_branch(branch)
                ok, detail = pr_accepted(ev)
                self.report.step(
                    f"pr_{task_id}_merged_under_policy",
                    ok,
                    detail,
                    pr_url=self.pr_url(ev["pr_id"]),
                    **ev,
                )
        if len(runs) > 1:
            second = str(_d(runs[1].get("run")).get("run_id") or "")
            started_by = rows.get(second, {}).get("started_by")
            self.report.step(
                "second_task_started_by_itself",
                started_by == "auto-continue",
                f"run {second} started_by {started_by}",
            )

    def final_state(self) -> None:
        self.mains_agree("final_main_matches_remote")
        git(self.clone, "fetch", "-q", "origin", BASE, check=False)
        rows = _task_runs(self.clone)
        prs = _task_prs(self.clone)
        for task_id, _slug, _title, _path in TASKS:
            rel = task_path(self.docs_root, task_id)
            text = git(self.clone, "show", f"origin/{BASE}:{rel}", check=False)
            header = front_matter(text)
            runs_section = text.split("## Běhy", 1)[1] if "## Běhy" in text else ""
            pr_url = prs.get(task_id, {}).get("url")
            succeeded = [
                r for r in rows.values() if r["task_id"] == task_id and r["state"] == "succeeded"
            ]
            self.report.step(
                f"backlog_{task_id}_done",
                header.get("status") == "done"
                and bool(pr_url)
                and str(pr_url) in runs_section
                and bool(succeeded)
                and prs.get(task_id, {}).get("state") == "merged",
                f"status {header.get('status')}, PR {pr_url} under '## Běhy' "
                f"{bool(pr_url) and str(pr_url) in runs_section}, succeeded runs {len(succeeded)}, "
                f"task_prs {prs.get(task_id, {}).get('state')}",
            )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.clone,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        dirty = [line for line in status.stdout.splitlines() if line.strip()]
        self.report.step(
            "main_checkout_clean", not dirty, f"{len(dirty)} changed paths: {dirty[:5]}"
        )

    def run(self) -> None:
        self.create_repo()
        self.set_policy()
        self.install()
        self.backlog()
        self.chain()
        self.final_state()

    # -- cleanup --

    def cleanup(self, keep_workdir: bool) -> None:
        report = self.report
        if self.registry_id is not None:
            try:
                from aifactory.web.registry import Registry
                from aifactory.web.repos import remove_repo

                remove_repo(Registry(self.home), self.registry_id)
                report.clean("unregister", True, f"dashboard entry {self.registry_id} removed")
            except Exception as exc:
                report.clean("unregister", False, str(exc))
        for policy_id in self.policy_ids:
            proc = self.azure.raw("repos", "policy", "delete", "--id", str(policy_id), "--yes")
            report.clean(
                f"delete_policy_{policy_id}", proc.returncode == 0, _tail(proc) or "deleted"
            )
        if self.repo_id is not None:
            proc = self.azure.raw("repos", "delete", "--id", self.repo_id, "--yes")
            report.clean("delete_repo", proc.returncode == 0, _tail(proc) or self.name)
            purge = self.azure.raw(
                "devops",
                "invoke",
                "--area",
                "git",
                "--resource",
                "recycleBinRepositories",
                "--route-parameters",
                f"project={self.azure.project}",
                f"repositoryId={self.repo_id}",
                "--http-method",
                "DELETE",
                "--api-version",
                "7.1",
                project=False,
            )
            report.clean("purge_recycle_bin", purge.returncode == 0, _tail(purge) or "purged")
            self._verify_gone()
        if keep_workdir:
            report.clean("local_workdir", True, f"kept {self.workdir}")
        else:
            try:
                safe_rmtree(self.workdir, self.workdir, self.owned)
                report.clean("local_workdir", True, f"deleted {self.workdir}")
            except Exception as exc:
                report.clean("local_workdir", False, f"{self.workdir}: {exc}")

    def _verify_gone(self) -> None:
        try:
            repos = self.azure.json("repos", "list")
        except AzFailed as exc:
            self.report.clean("repo_gone", False, f"cannot list repos: {exc}")
        else:
            left = [r.get("name") for r in repos or [] if str(r.get("id")) == self.repo_id]
            self.report.clean("repo_gone", not left, f"left: {left}" if left else self.name)
        for policy_id in self.policy_ids:
            proc = self.azure.raw("repos", "policy", "show", "--id", str(policy_id))
            gone, detail = policy_gone(proc)
            self.report.clean(f"policy_{policy_id}_gone", gone, detail)

    @staticmethod
    def _identity(repo: Path) -> None:
        git(repo, "config", "user.name", GIT_NAME)
        git(repo, "config", "user.email", GIT_EMAIL)
        git(repo, "config", "commit.gpgsign", "false")


def policy_gone(proc: subprocess.CompletedProcess[str]) -> tuple[bool, str]:
    """``az repos policy show`` of a deleted policy: not found, or kept with ``isDeleted``.

    Azure DevOps still returns a deleted policy by its id (``isDeleted: true``); it no
    longer applies and ``az repos policy list`` leaves it out.
    """
    if proc.returncode != 0:
        return True, "not found"
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return False, "unreadable answer of az repos policy show"
    if isinstance(data, dict) and data.get("isDeleted") is True:
        return True, "deleted (isDeleted: true)"
    return False, "the policy still exists"


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tail(proc: subprocess.CompletedProcess[str]) -> str:
    lines = [line for line in (proc.stderr or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _exists(repo: Path, spec: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", spec], cwd=repo).returncode == 0


def _rows(repo: Path, sql: str) -> list[dict[str, Any]]:
    import sqlite3

    db = repo / ".factory" / "trace.db"
    if not db.is_file():
        return []
    conn = sqlite3.connect(str(db), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql).fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _task_runs(repo: Path) -> dict[str, dict[str, Any]]:
    rows = _rows(repo, "SELECT run_id, task_id, state, started_by FROM task_runs")
    return {str(r["run_id"]): r for r in rows}


def _task_prs(repo: Path) -> dict[str, dict[str, Any]]:
    rows = _rows(repo, "SELECT task_id, url, state, merged_by FROM task_prs")
    return {str(r["task_id"]): r for r in rows}


# ── main ─────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="just validate-azure-e2e",
        description="HAIFA end to end on a new temporary Azure DevOps repo with a required "
        "reviewer policy: own approval, merge, base changes by PR, auto-continue; the repo "
        "is deleted at the end.",
    )
    parser.add_argument("--org", default=DEFAULT_ORG, help=f"organization (default {DEFAULT_ORG})")
    parser.add_argument(
        "--project", default=DEFAULT_PROJECT, help=f"project (default {DEFAULT_PROJECT})"
    )
    parser.add_argument(
        "--name", default=None, help=f"repo name (default {NAME_PREFIX}<date>-<time>-<hex>)"
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=VALIDATION_DIR / "results",
        help="where <date>/azure-e2e-<time>/ goes (default: aifactory/validation/results)",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="keep the local workdir (clone, logs); the Azure repo is deleted anyway",
    )
    return parser


def main(argv: list[str] | None = None, *, steps: Callable[[E2E], None] | None = None) -> int:
    args = build_parser().parse_args(argv)
    moment = datetime.datetime.now()
    name = args.name or repo_name(moment)
    organization = str(args.org).rstrip("/")
    try:
        preflight(organization, args.project, name)
    except SetupError as exc:
        print(f"validate-azure-e2e: {exc}", file=sys.stderr)
        return EXIT_SETUP

    owned = Owned()
    workdir = owned.add(Path(tempfile.mkdtemp(prefix="haifa-azure-e2e-")))
    out = results_mod.output_dir(args.results_dir.resolve(), "azure-e2e", moment)
    report = Report(organization, args.project, name)
    previous_home = os.environ.get("HAIFA_HOME")
    os.environ["HAIFA_HOME"] = str(isolated_home(workdir))
    e2e = E2E(
        Azure(organization, args.project, workdir, report.commands),
        report,
        workdir,
        owned,
        Path(os.environ["HAIFA_HOME"]),
        name,
    )
    print(f"[azure-e2e] {organization}/{args.project}: repo {name}", file=sys.stderr)
    try:
        (steps or E2E.run)(e2e)
    except Stop as exc:
        report.step("stopped", False, str(exc))
    except BaseException as exc:  # Ctrl+C too: the cleanup below still runs
        report.step("exception", False, "".join(traceback.format_exception(exc)))
        if not isinstance(exc, Exception):
            _finish(e2e, out, args.keep_workdir, previous_home)
            raise
    return _finish(e2e, out, args.keep_workdir, previous_home)


def _finish(e2e: E2E, out: Path, keep_workdir: bool, previous_home: str | None) -> int:
    try:
        logs = e2e.workdir / "logs"
        if logs.is_dir():
            shutil.copytree(logs, out / "logs", dirs_exist_ok=True)
        e2e.cleanup(keep_workdir)
    finally:
        if previous_home is None:
            os.environ.pop("HAIFA_HOME", None)
        else:
            os.environ["HAIFA_HOME"] = previous_home
        report = e2e.report
        write_json(out / "azure-e2e.json", report.to_json())
        for step in report.steps:
            print(f"{'ok' if step.ok else 'FAILED':>6}  {step.name}", file=sys.stderr)
        print(f"cleanup {'ok' if report.cleanup_ok else 'FAILED'}", file=sys.stderr)
        print(f"{report.outcome}; results: {out / 'azure-e2e.json'}", file=sys.stderr)
    return EXIT_OK if e2e.report.outcome == "passed" else EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
