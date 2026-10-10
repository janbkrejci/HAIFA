"""``run_check`` over temporary repos: install states, repo and machine findings."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pytest
from factory_check_repo import (
    FILES,
    TASK,
    FakeMachine,
    commit_all,
    git,
    init_repo,
    make_check_repo,
    write,
)

from aifactory import check
from aifactory.check import CheckReport, Finding, Rule, RuleGroup, run_check
from aifactory.config import config_changes


def _codes(report: CheckReport) -> list[str]:
    return [f.code for f in report.findings]


def _one(report: CheckReport, code: str) -> Finding:
    found = [f for f in report.findings if f.code == code]
    assert found, (code, _codes(report))
    return found[0]


def _assert(
    report: CheckReport,
    code: str,
    scope: str,
    severity: str,
    action: str | None = None,
) -> Finding:
    finding = _one(report, code)
    assert (finding.scope, finding.severity, finding.action) == (scope, severity, action)
    return finding


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_check_repo(tmp_path / "repo")


def test_healthy_repo(repo: Path) -> None:
    report = run_check(repo, machine=FakeMachine())
    assert (report.state, report.action) == ("pre_library", "onboard")
    assert report.ok, report.findings
    _assert(report, "pre_library_config", "repo", "info", "onboard")
    assert _codes(report) == ["pre_library_config", "library_missing"]
    _assert(report, "library_missing", "library", "warning")
    assert report.commit == git(repo, "rev-parse", "HEAD").strip()
    assert report.groups == ("repo", "machine", "library")
    assert report.backlog == {}
    data = report.to_json()
    assert data["counts"] == {"error": 0, "warning": 1, "info": 1}
    assert data["in_repo"] is True
    assert data["state"] == "pre_library" and data["action"] == "onboard"
    assert data["sssf_leftover"] is False and data["onboarding"] is None
    assert data["ok"] is True


def test_repo_without_factory(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "plain")
    write(repo, "README.md", "readme\n")
    commit_all(repo, "readme")
    report = run_check(repo, machine=FakeMachine())
    assert (report.state, report.action) == ("none", "init")
    _assert(report, "factory_missing", "repo", "error", "init")
    assert [f.code for f in report.findings if f.scope == "repo"] == ["factory_missing"]
    assert not report.ok


def test_config_only_in_working_tree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "wt")
    write(repo, "README.md", "readme\n")
    commit_all(repo, "readme")
    for rel, text in FILES.items():
        if rel.startswith(".factory/"):
            write(repo, rel, text)
    report = run_check(repo, machine=FakeMachine())
    assert (report.state, report.action) == ("working_tree", "config_commit")
    _assert(report, "config_not_committed", "repo", "error", "config_commit")


def test_invalid_config_in_base(repo: Path) -> None:
    write(repo, ".factory/config.yaml", "base: main\ngit_provider: nope\n")
    commit_all(repo, "broken")
    report = run_check(repo, machine=FakeMachine())
    finding = _assert(report, "base_config_invalid", "repo", "error")
    assert "git_provider" in finding.message
    assert not report.ok


def test_missing_prompt_in_base(repo: Path) -> None:
    (repo / ".factory/prompts/builder/user.md").unlink()
    commit_all(repo, "no prompt")
    report = run_check(repo, machine=FakeMachine())
    finding = _assert(report, "base_config_invalid", "repo", "error")
    assert "missing prompt" in finding.message


def test_invalid_base_fixed_in_working_tree_offers_commit(repo: Path) -> None:
    path = repo / ".factory/prompts/builder/user.md"
    text = path.read_text(encoding="utf-8")
    path.unlink()
    commit_all(repo, "no prompt")
    write(repo, ".factory/prompts/builder/user.md", text)
    report = run_check(repo, machine=FakeMachine())
    _assert(report, "base_config_invalid", "repo", "error", "config_commit")
    _assert(report, "config_uncommitted", "repo", "warning", "config_commit")


def test_uncommitted_prompt_change(repo: Path) -> None:
    write(repo, ".factory/prompts/builder/user.md", "Changed: {{prompt}}\n")
    report = run_check(repo, machine=FakeMachine())
    finding = _assert(report, "config_uncommitted", "repo", "warning", "config_commit")
    assert ".factory/prompts/builder/user.md" in finding.message
    assert report.ok


def test_backlog_problems(repo: Path) -> None:
    write(
        repo,
        "backlog/M01-core/S01-model/M01-S01-T01-copy.md",
        f"---\nid: {TASK}\ntitle: Copy\nstatus: todo\n---\n",
    )
    write(
        repo,
        "backlog/M01-core/S01-model/M01-S01-T02-dep.md",
        "---\nid: M01-S01-T02\ntitle: Dep\nstatus: todo\ndepends_on: [NOPE-1]\n---\n",
    )
    commit_all(repo, "bad backlog")
    report = run_check(repo, machine=FakeMachine())
    invalid = [f for f in report.findings if f.code == "backlog_invalid"]
    assert all((f.scope, f.severity, f.action) == ("repo", "error", None) for f in invalid)
    messages = " ".join(f.message for f in invalid)
    assert "duplicate_id" in messages and "unknown_ref" in messages
    assert report.backlog["duplicate_id"] >= 1 and report.backlog["unknown_ref"] == 1


def test_backlog_missing(repo: Path) -> None:
    git(repo, "rm", "-r", "-q", "backlog")
    commit_all(repo, "no backlog")
    report = run_check(repo, machine=FakeMachine())
    _assert(report, "backlog_missing", "repo", "warning")
    assert report.ok


def test_unknown_workflow(repo: Path) -> None:
    write(repo, "backlog/M01-core/index.md", "---\nid: M01\ntitle: Core\nworkflow: nope\n---\n")
    commit_all(repo, "unknown workflow")
    report = run_check(repo, machine=FakeMachine())
    finding = _assert(report, "workflow_unknown", "repo", "error")
    assert "nope" in finding.message and TASK in finding.message


def test_workflow_with_unknown_agent(repo: Path) -> None:
    write(
        repo,
        ".factory/agents.yaml",
        "defaults:\n  harness: claude\n  model: sonnet\nagents:\n  - name: planner\n",
    )
    (repo / ".factory/prompts/builder/user.md").unlink()
    (repo / ".factory/prompts/builder/system.md").unlink()
    commit_all(repo, "no builder")
    report = run_check(repo, machine=FakeMachine())
    finding = _assert(report, "workflow_invalid", "repo", "error")
    assert "builder" in finding.message


def test_workflow_unset(repo: Path) -> None:
    write(repo, "backlog/M01-core/index.md", "---\nid: M01\ntitle: Core\n---\n")
    commit_all(repo, "no workflow key")
    # no level sets workflow: the tasks use the default workflow
    assert "workflow_unset" not in _codes(run_check(repo, machine=FakeMachine()))
    write(repo, "backlog/M01-core/index.md", "---\nid: M01\ntitle: Core\nworkflow: null\n---\n")
    commit_all(repo, "no workflow")
    report = run_check(repo, machine=FakeMachine())
    _assert(report, "workflow_unset", "repo", "warning")


def test_missing_harness(repo: Path) -> None:
    report = run_check(repo, machine=FakeMachine(present={"just", "gh"}))
    finding = _assert(report, "harness_missing", "machine", "error")
    assert "claude" in finding.message and "planner" in finding.message


def _with_remote(repo: Path, tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin")
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(remote), str(other))
    return remote, other


def test_behind_and_ahead_of_remote(repo: Path, tmp_path: Path) -> None:
    _remote, other = _with_remote(repo, tmp_path)
    report = run_check(repo, machine=FakeMachine())
    assert (report.remote, report.ahead, report.behind) == ("origin", 0, 0)
    assert _codes(report) == ["pre_library_config", "library_missing"]

    write(other, "README.md", "remote change\n")
    commit_all(other, "remote change")
    git(other, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin")  # the test fetches; the check never does
    report = run_check(repo, machine=FakeMachine())
    assert report.behind == 1 and report.ahead == 0
    _assert(report, "base_behind_remote", "repo", "warning", "config_pull")

    write(repo, "local.txt", "local\n")
    commit_all(repo, "local change")
    report = run_check(repo, machine=FakeMachine())
    assert (report.ahead, report.behind) == (1, 1)
    _assert(report, "base_ahead_of_remote", "repo", "warning")


def test_remote_without_tracking_ref(repo: Path, tmp_path: Path) -> None:
    git(repo, "remote", "add", "origin", str(tmp_path / "nowhere.git"))
    report = run_check(repo, machine=FakeMachine())
    _assert(report, "remote_base_missing", "repo", "info")
    assert report.ok


def _github(repo: Path) -> None:
    write(repo, ".factory/config.yaml", "base: main\ngit_provider: github\n")
    commit_all(repo, "github")


def test_offline_skips_hosting(repo: Path, tmp_path: Path) -> None:
    _github(repo)
    _with_remote(repo, tmp_path)
    machine = FakeMachine(logged_in=False)
    report = run_check(repo, offline=True, machine=machine)
    assert machine.calls == []
    _assert(report, "hosting_skipped", "machine", "info")
    assert report.ok and report.offline

    machine = FakeMachine(logged_in=False)
    report = run_check(repo, machine=machine)
    assert ("gh", "auth", "status", "--hostname", "github.com") in machine.calls
    _assert(report, "gh_login", "machine", "error")


def test_github_without_remote_and_gh(repo: Path) -> None:
    _github(repo)
    report = run_check(repo, offline=True, machine=FakeMachine(present={"just", "claude"}))
    _assert(report, "remote_missing", "repo", "warning")
    _assert(report, "gh_missing", "machine", "error")


def test_azure_checks(repo: Path) -> None:
    write(
        repo,
        ".factory/config.yaml",
        "base: main\ngit_provider: azure\nazure:\n  organization: o\n  project: p\n"
        "  repository: r\n",
    )
    commit_all(repo, "azure")
    machine = FakeMachine(logged_in=False)
    report = run_check(repo, machine=machine)
    _assert(report, "az_devops_missing", "machine", "error")
    _assert(report, "az_login", "machine", "error")
    machine = FakeMachine(logged_in=False, environ={"AZURE_DEVOPS_EXT_PAT": "x"})
    report = run_check(repo, machine=machine)
    assert "az_login" not in _codes(report)
    assert ("az", "account", "show", "--output", "json") not in machine.calls
    report = run_check(repo, machine=FakeMachine(present={"just", "claude"}))
    _assert(report, "az_missing", "machine", "error")


def test_checkout_not_on_base(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "feature")
    report = run_check(repo, machine=FakeMachine())
    finding = _assert(report, "checkout_not_on_base", "repo", "warning")
    assert "feature" in finding.message


def test_linked_worktree_checks_main_checkout(repo: Path, tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-q", "-b", "side", str(linked))
    report = run_check(linked, machine=FakeMachine())
    assert report.repo == str(repo)
    assert "checkout_not_on_base" not in _codes(report)


def test_gitignore_missing(repo: Path) -> None:
    write(repo, ".gitignore", ".factory/trace.db*\n/.factory/worktrees\n.factory/data/\n")
    commit_all(repo, "gitignore")
    report = run_check(repo, machine=FakeMachine())
    finding = _assert(report, "gitignore_missing", "repo", "warning", "update")
    assert ".factory/local.yaml" in finding.message
    assert [f.code for f in report.findings] == [
        "pre_library_config",
        "gitignore_missing",
        "library_missing",
    ]


def test_base_missing(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "empty")
    for rel, text in FILES.items():
        write(repo, rel, text)
    report = run_check(repo, machine=FakeMachine())
    assert report.state == "working_tree" and report.commit is None
    _assert(report, "base_missing", "repo", "error")


def test_invalid_local_yaml(repo: Path) -> None:
    write(repo, ".factory/local.yaml", "trace_db: ''\n")
    report = run_check(repo, machine=FakeMachine())
    finding = _assert(report, "local_config_invalid", "machine", "warning")
    assert finding.fix == "fix .factory/local.yaml (trace_db)"


@pytest.mark.parametrize("text", ["port: 4811\n", "port: nope\n"])
def test_old_local_port_is_ignored(repo: Path, text: str) -> None:
    write(repo, ".factory/local.yaml", text)
    report = run_check(repo, machine=FakeMachine())
    finding = _assert(report, "local_port_ignored", "machine", "warning")
    assert finding.fix == "smaž řádek port z .factory/local.yaml"
    assert not [f for f in report.findings if f.code == "local_config_invalid"]
    assert report.ok


def test_not_a_repository(tmp_path: Path) -> None:
    with pytest.raises(check.NotARepositoryError):
        run_check(tmp_path / "missing", machine=FakeMachine())


def test_added_rule_group(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def extra(_ctx: check.CheckContext) -> Iterable[Finding]:
        yield Finding("check_failed", "machine", "info", "from an added group")

    def broken(_ctx: check.CheckContext) -> Iterable[Finding]:
        raise OSError("boom")

    group = RuleGroup("extra", (Rule("extra", extra), Rule("broken", broken)), scope="machine")
    monkeypatch.setattr(check, "RULE_GROUPS", [*check.RULE_GROUPS, group])
    report = run_check(repo, machine=FakeMachine())
    assert report.groups == ("repo", "machine", "library", "extra")
    messages = [
        f.message
        for f in report.findings
        if f.code not in ("pre_library_config", "library_missing")
    ]
    assert messages == ["from an added group", "broken: boom"]
    _assert(report, "check_failed", "machine", "info")


# ── the check changes nothing ────────────────────────────────────────────────


def _state(repo: Path) -> dict[str, Any]:
    index = repo / ".git" / "index"
    return {
        "index": index.read_bytes(),
        "index_mtime": index.stat().st_mtime_ns,
        "lock": (repo / ".git" / "index.lock").exists(),
        "files": sorted(str(p.relative_to(repo)) for p in repo.rglob("*")),
        "refs": git(repo, "for-each-ref"),
    }


def _status(repo: Path) -> str:
    return git(repo, "status", "--porcelain=v1", "-uall")


@pytest.mark.parametrize("offline", [False, True])
def test_check_changes_nothing(repo: Path, tmp_path: Path, offline: bool) -> None:
    _with_remote(repo, tmp_path)
    write(repo, ".factory/prompts/builder/user.md", "Changed: {{prompt}}\n")
    committed = repo / ".factory/prompts/planner/user.md"
    os.utime(committed, None)  # the index is stale for this file now
    before = _state(repo)
    report = run_check(repo, offline=offline, machine=FakeMachine())
    assert "config_uncommitted" in _codes(report)
    assert _state(repo) == before
    assert _status(repo) == " M .factory/prompts/builder/user.md\n"
    assert not (repo / ".factory/trace.db").exists()


def test_config_git_reads_without_optional_locks(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, str]] = []
    real: Callable[..., Any] = subprocess.run

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(dict(kwargs.get("env") or {}))
        return real(*args, **kwargs)

    monkeypatch.setattr("aifactory.config.source.subprocess.run", spy)
    config_changes(repo, git(repo, "rev-parse", "HEAD").strip())
    assert seen and all(env.get("GIT_OPTIONAL_LOCKS") == "0" for env in seen)


# -- repo skills mirror and harness isolation (HAIFA-S05-T05) --


def _skill_codes(report: CheckReport) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for f in report.findings:
        if f.code.startswith("skill_mirror_"):
            assert (f.scope, f.severity) == ("repo", "warning")
            found.setdefault(f.code, []).append(f.message)
    return found


def test_skills_mirror_differences(repo: Path) -> None:
    from aifactory.harness.repo_skills import sync

    write(repo, ".claude/skills/a/SKILL.md", "a\n")
    write(repo, ".claude/skills/b/SKILL.md", "b\n")
    write(repo, ".agents/skills/b/SKILL.md", "stale b\n")
    write(repo, ".agents/skills/c/SKILL.md", "c\n")
    commit_all(repo, "skills")

    found = _skill_codes(run_check(repo, machine=FakeMachine()))
    assert set(found) == {"skill_mirror_missing", "skill_mirror_differs", "skill_mirror_extra"}
    assert "'a'" in found["skill_mirror_missing"][0]
    assert "'b'" in found["skill_mirror_differs"][0]
    assert "'c'" in found["skill_mirror_extra"][0]

    sync(repo)
    assert _skill_codes(run_check(repo, machine=FakeMachine())) != {}  # base is what counts
    commit_all(repo, "sync skills")
    assert _skill_codes(run_check(repo, machine=FakeMachine())) == {}


ISOLATION_AGENTS = """\
defaults:
  harness: claude
  model: sonnet
agents:
  - name: planner
    harness: pi
    model: openai/gpt-5.5
  - name: builder
    harness: codex
    model: gpt-5.5
"""


@pytest.mark.parametrize(
    ("code", "rel", "switch"),
    [
        ("codex_not_isolated", ".codex/AGENTS.md", "CODEX_SAFE_MODE"),
        ("codex_not_isolated", ".agents/skills/x/SKILL.md", "CODEX_SAFE_MODE"),
        ("pi_not_isolated", ".pi/agent/AGENTS.md", "PI_SAFE_MODE"),
        ("pi_not_isolated", ".pi/agent/APPEND_SYSTEM.md", "PI_SAFE_MODE"),
    ],
)
def test_harness_isolation(repo: Path, tmp_path: Path, code: str, rel: str, switch: str) -> None:
    write(repo, ".factory/agents.yaml", ISOLATION_AGENTS)
    commit_all(repo, "codex and pi")
    home = tmp_path / "home"
    home.mkdir()
    present = {"just", "claude", "codex", "pi", "gh", "az"}

    report = run_check(repo, machine=FakeMachine(present=present, home_dir=home))
    assert code not in _codes(report)

    write(home, rel, "global\n")
    report = run_check(repo, machine=FakeMachine(present=present, home_dir=home))
    finding = _assert(report, code, "machine", "warning")
    assert str(home / rel.split("/x/")[0]) in finding.message

    machine = FakeMachine(present=present, home_dir=home, environ={switch: "1"})
    assert code not in _codes(run_check(repo, machine=machine))


def test_claude_only_roster_has_no_isolation_warning(repo: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    write(home, ".codex/AGENTS.md", "global\n")
    write(home, ".pi/agent/AGENTS.md", "global\n")
    codes = _codes(run_check(repo, machine=FakeMachine(home_dir=home)))
    assert "codex_not_isolated" not in codes
    assert "pi_not_isolated" not in codes
