"""``factory check`` in an installed repo: item states (AR23) and the other repo findings."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from factory_check_repo import GIT_IDENTITY, FakeMachine, commit_all, make_check_repo, write

from aifactory.check import CheckReport, Finding, run_check
from aifactory.config import MANIFEST_FILE
from aifactory.library import workflow_version

V1 = "name: w\ndescription: one\nsteps: [plan, build]\n"
V2 = "name: w\ndescription: two\nsteps: [plan, build]\n"
OWN = "name: w\ndescription: own\nsteps: [plan, build]\n"
FOREIGN = "sha256:" + "0" * 64


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        capture_output=True,
        check=True,
    )


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """A library with workflow ``w`` at V1 then V2 and workflow ``stay`` only at V1."""
    root = tmp_path / "library"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    write(root, "library.yaml", "format: 1\nid: x\nname: test\n")
    write(root, "workflows/w.yaml", V1)
    write(root, "workflows/stay.yaml", V1)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "v1")
    write(root, "workflows/w.yaml", V2)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "v2")
    return root


def _machine(library: Path) -> FakeMachine:
    return FakeMachine(environ={**GIT_IDENTITY, "HAIFA_LIBRARY": str(library)})


def _manifest(entries: dict[str, tuple[str, str]]) -> str:
    data = {
        "format": 1,
        "written_by": "0.2.0",
        "library": None,
        "items": {
            "workflows": {slot: {"item": item, "version": v} for slot, (item, v) in entries.items()}
        },
    }
    return yaml.safe_dump(data)


def _installed(tmp_path: Path) -> Path:
    repo = make_check_repo(tmp_path / "repo")
    v1, v2 = workflow_version(V1.encode()), workflow_version(V2.encode())
    workflows = {
        "synced": V2,
        "outdated": V1,
        "modified": OWN,
        "diverged": OWN,
        "unknown": OWN,
        "own": OWN,
    }
    for name, text in workflows.items():
        write(repo, f".factory/workflows/{name}.yaml", text)
    entries = {
        "synced": ("w", v2),
        "outdated": ("w", v1),
        "modified": ("stay", v1),
        "diverged": ("w", v1),
        "unknown": ("w", FOREIGN),
        "missing": ("w", v1),
    }
    write(repo, MANIFEST_FILE, _manifest(entries))
    commit_all(repo, "installed")
    return repo


def _by_name(report: CheckReport) -> dict[str, Finding]:
    found: dict[str, Finding] = {}
    for finding in report.findings:
        if finding.code.startswith("item_") and finding.message.startswith("workflow "):
            found[finding.message.split()[1]] = finding
    return found


def test_item_states(tmp_path: Path, library: Path) -> None:
    repo = _installed(tmp_path)
    report = run_check(repo, machine=_machine(library))
    assert report.state == "installed"
    found = _by_name(report)
    expected = {
        "own": ("item_local", "info", "export"),
        "plan-build": ("item_local", "info", "export"),
        "missing": ("item_missing", "warning", "update"),
        "unknown": ("item_unknown", "warning", "export"),
        "outdated": ("item_outdated", "info", "update"),
        "modified": ("item_modified", "info", "export"),
        "diverged": ("item_diverged", "warning", "update"),
    }
    for name, (code, severity, action) in expected.items():
        finding = found[name]
        assert (finding.code, finding.scope, finding.severity, finding.action) == (
            code,
            "repo",
            severity,
            action,
        ), name
    assert "synced" not in found
    assert "is outdated (repo " in found["outdated"].message


def test_items_only_for_installed_repos(tmp_path: Path, library: Path) -> None:
    repo = make_check_repo(tmp_path / "repo")
    report = run_check(repo, machine=_machine(library))
    assert report.state == "unsupported"
    assert not [f for f in report.findings if f.code.startswith("item_")]


def test_workflow_not_in_repo(tmp_path: Path, library: Path) -> None:
    repo = _installed(tmp_path)
    write(
        repo,
        "backlog/M01-core/S01-model/M01-S01-T02-other.md",
        "---\nid: M01-S01-T02\ntitle: Other\nstatus: todo\nworkflow: nowhere\n---\n\n"
        "## Zadání\nJiné.\n",
    )
    commit_all(repo, "task with an unknown workflow")
    report = run_check(repo, machine=_machine(library))
    finding = next(f for f in report.findings if f.code == "workflow_not_in_repo")
    assert (finding.scope, finding.severity) == ("repo", "error")
    assert "'nowhere'" in finding.message and "M01-S01-T02" in finding.message
    assert "workflow_unknown" not in {f.code for f in report.findings}


def test_workflow_unknown_without_manifest(tmp_path: Path) -> None:
    repo = make_check_repo(tmp_path / "repo")
    write(repo, "backlog/M01-core/index.md", "---\nid: M01\ntitle: Core\nworkflow: nowhere\n---\n")
    commit_all(repo, "unknown workflow")
    codes = {f.code for f in run_check(repo, machine=FakeMachine()).findings}
    assert "workflow_unknown" in codes and "workflow_not_in_repo" not in codes


def test_roles_full_copy(tmp_path: Path) -> None:
    repo = make_check_repo(tmp_path / "repo")
    write(repo, ".factory/roles.yaml", "roles:\n  plan:\n    agent: planner\n")
    commit_all(repo, "overlay")
    codes = {f.code for f in run_check(repo, machine=FakeMachine()).findings}
    assert "roles_full_copy" not in codes
    write(repo, ".factory/roles.yaml", "roles: {}\ncode_steps: {}\n")
    commit_all(repo, "full copy")
    report = run_check(repo, machine=FakeMachine())
    finding = next(f for f in report.findings if f.code == "roles_full_copy")
    assert (finding.scope, finding.severity) == ("repo", "info")


def test_unknown_thinking(tmp_path: Path) -> None:
    repo = make_check_repo(tmp_path / "repo")
    report = run_check(repo, machine=FakeMachine())
    assert "unknown_thinking" not in {f.code for f in report.findings}
    agents = (repo / ".factory/agents.yaml").read_text(encoding="utf-8")
    write(
        repo,
        ".factory/agents.yaml",
        agents.replace("    model: opus\n", "    model: opus\n    thinking: auto\n"),
    )
    commit_all(repo, "thinking auto")
    report = run_check(repo, machine=FakeMachine())
    found = [f for f in report.findings if f.code == "unknown_thinking"]
    assert len(found) == 1
    assert (found[0].scope, found[0].severity) == ("repo", "warning")
    assert "planner" in found[0].message and "'auto'" in found[0].message


def test_installed_repo_with_adws_has_no_sssf_finding(tmp_path: Path, library: Path) -> None:
    repo = _installed(tmp_path)
    write(repo, "adws/adw_sssf_config/factory.config.yaml", "agents: []\n")
    commit_all(repo, "leftover")
    report = run_check(repo, machine=_machine(library))
    assert (report.state, report.action) == ("installed", None)
    finding = next(f for f in report.findings if f.code == "repo_installed")
    assert (finding.scope, finding.severity, finding.action) == ("repo", "info", None)
    assert not [f for f in report.findings if "sssf" in f.code or f.code == "repo_unsupported"]
