"""The sandbox template of `just validate`: a valid backlog, green base, usable roster.

Also the two forced repair rounds: the hidden test fails the naive slugify and
passes the fixed one, and the reviewer rule lives only in the validation
template, never in the product (``aifactory/src``).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest
import yaml
from validation.sandbox import AIFACTORY_DIR, TEMPLATE_DIR

from aifactory.engine import data_types as dt
from aifactory.engine.gates import verdict_consistent
from cli_json import run_json
from validation import fake_scripts, hidden, sandbox

Capsys = pytest.CaptureFixture[str]
RULE_TAG = "haifa-validate"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("sandbox") / "repo"
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "commit.gpgsign", "false")
    sandbox.materialize(path, "main", "local")
    sandbox.commit_all(path, "sandbox")
    return path


def _cli_json(capsys: Capsys, *argv: str) -> tuple[int, dict[str, Any]]:
    capsys.readouterr()
    code, data = run_json(capsys, [*argv, "--json"])
    assert isinstance(data, dict)
    return code, data


def _walk(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        out.append(item)
        out.extend(_walk(item.get("children", [])))
    return out


def test_backlog_check_passes(repo: Path, capsys: Capsys) -> None:
    code, data = _cli_json(capsys, "backlog", "check", "--repo", str(repo))
    assert code == 0, data
    assert data["ok"] is True
    assert data["warnings"] == []


def test_backlog_shape(repo: Path, capsys: Capsys) -> None:
    code, data = _cli_json(capsys, "backlog", "list", "--repo", str(repo))
    assert code == 0
    nodes = _walk(data["data"]["items"])
    projects = [n for n in nodes if n["kind"] == "container" and n["level"] == "project"]
    steps = [n for n in nodes if n["kind"] == "container" and n["level"] == "step"]
    tasks = [n for n in nodes if n["kind"] == "task"]
    assert (len(projects), len(steps), len(tasks)) == (2, 3, 7)
    assert all(t["status"] == "todo" and t["workflow"] == "simple-sdlc" for t in tasks)
    shared = [t["id"] for t in tasks if "src/sandbox/mathx.py" in t["writes"]]
    assert shared == ["M01-S01-T01", "M01-S01-T02", "M01-S01-T03"]
    sign = next(t for t in tasks if t["id"] == "M01-S01-T03")
    assert sign["writes"] == ["src/sandbox/mathx.py"]
    cross = [
        (t["id"], dep)
        for t in tasks
        for dep in t["depends_on"]
        if dep.split("-")[0] != t["id"].split("-")[0]
    ]
    assert cross == [("M02-S01-T01", "M01-S02-T01")]
    for task in tasks:
        text = (repo / task["path"]).read_text(encoding="utf-8")
        assert "## Zadání" in text, task["id"]
        assert len(text.splitlines()) < 40, task["id"]
        stem = fake_scripts.TASK_STEMS[task["id"]]
        assert Path(task["path"]).stem == stem


def test_workflow_names_three_harnesses(
    repo: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `workflow check` reads the roster of the working tree: the sandbox's, not the one of
    # the repository running the tests (HAIFA's own .factory/ has other models).
    monkeypatch.chdir(repo)
    # pi's catalog comes from `pi --list-models` of this machine; fake it with the models the
    # sandbox names, so the check does not depend on what the operator's pi lists today.
    from aifactory.engine import agent_pi

    texts = [
        (repo / ".factory" / rel).read_text(encoding="utf-8")
        for rel in ("agents.yaml", "workflows/simple-sdlc.yaml")
    ]
    named = re.findall(r"model:\s*['\"]?([^\s'\"]+/[^\s'\"]+)", "\n".join(texts))
    catalog = [(*m.split("/", 1), 128000) for m in named]
    monkeypatch.setattr(agent_pi, "_pi_catalog", lambda: catalog)
    path = repo / ".factory" / "workflows" / "simple-sdlc.yaml"
    code, data = _cli_json(capsys, "workflow", "check", str(path))
    assert code == 0, data
    steps = yaml.safe_load(path.read_text(encoding="utf-8"))["steps"]
    text = json.dumps(steps)
    assert '"plan": {"harness": "claude"}' in text
    assert '"harness": "codex"' in text and '"harness": "pi"' in text


def test_config_is_rendered_and_loads(
    repo: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = yaml.safe_load((repo / ".factory" / "config.yaml").read_text(encoding="utf-8"))
    assert config["base"] == "main"
    assert config["git_provider"] == "local"
    assert not (repo / ".factory" / "config.yaml.tmpl").exists()
    monkeypatch.chdir(repo)
    code, data = _cli_json(capsys, "config", "show")
    assert code == 0, data
    assert data["data"]["agents"] == ["planner", "builder", "reviewer", "documenter"]
    assert data["data"]["settings"]["git_provider"] == "local"
    assert "simple-sdlc" in data["data"]["workflows"]
    assert data["warnings"] == []


def _suite(repo: Path, hidden_dir: Path | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != hidden.HIDDEN_ENV}
    with hidden.placed(repo, hidden_dir) if hidden_dir is not None else nullcontext():
        return subprocess.run(
            ["just", "test"], cwd=repo, capture_output=True, text=True, env=env, encoding="utf-8"
        )


@pytest.mark.skipif(shutil.which("just") is None, reason="just is not on PATH")
def test_base_suite_is_green_with_and_without_the_hidden_test(repo: Path, tmp_path: Path) -> None:
    plain = _suite(repo, None)
    assert plain.returncode == 0, plain.stderr
    assert "skipped" in plain.stderr
    with_hidden = _suite(repo, hidden.write_hidden(tmp_path))
    assert with_hidden.returncode == 0, with_hidden.stderr
    # the hidden test was discovered (one test more) and skipped: slugify is not there yet
    ran = re.compile(r"Ran (\d+) test")
    skipped = re.compile(r"skipped=(\d+)")
    plain_ran, hidden_ran = (int(ran.findall(p.stderr)[0]) for p in (plain, with_hidden))
    plain_skip, hidden_skip = (int(skipped.findall(p.stderr)[0]) for p in (plain, with_hidden))
    assert (hidden_ran, hidden_skip) == (plain_ran + 1, plain_skip + 1), with_hidden.stderr
    assert not (repo / hidden.HIDDEN_TARGET).exists()


def _hidden_result(tmp_path: Path, slugify: str) -> subprocess.CompletedProcess[str]:
    root = tmp_path / "checkout"
    src = root / "src" / "sandbox"
    src.mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8", newline="\n")
    (src / "__init__.py").write_text("", encoding="utf-8", newline="\n")
    text = (TEMPLATE_DIR / "src" / "sandbox" / "text.py").read_text(encoding="utf-8")
    (src / "text.py").write_text(text + slugify, encoding="utf-8", newline="\n")
    directory = hidden.write_hidden(tmp_path / "work")
    env = dict(os.environ, PYTHONPATH=str(root / "src"))
    with hidden.placed(root, directory):
        return subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
            cwd=root,
            capture_output=True,
            text=True,
            env=env,
            encoding="utf-8",
        )


def test_hidden_test_fails_the_first_build_and_passes_the_fix(tmp_path: Path) -> None:
    first = _hidden_result(tmp_path / "first", fake_scripts.SLUGIFY)
    assert first.returncode != 0
    assert hidden.HIDDEN_CLASS in first.stderr
    fixed = fake_scripts.SLUGIFY.replace(
        fake_scripts.SLUGIFY_RETURN, fake_scripts.SLUGIFY_RETURN_FIXED
    )
    assert fixed != fake_scripts.SLUGIFY
    second = _hidden_result(tmp_path / "second", fixed)
    assert second.returncode == 0, second.stderr


def test_justfile_has_no_hidden_hook() -> None:
    assert hidden.HIDDEN_ENV not in (TEMPLATE_DIR / "justfile").read_text(encoding="utf-8")


def test_hidden_test_is_outside_the_template() -> None:
    assert not list(TEMPLATE_DIR.rglob(hidden.HIDDEN_FILE))
    assert hidden.HIDDEN_EXPECTED not in "".join(
        p.read_text(encoding="utf-8") for p in TEMPLATE_DIR.rglob("*.md")
    )


def test_prompts_carry_the_sentinel_and_the_review_rule(repo: Path) -> None:
    for agent in sandbox.PROMPT_AGENTS:
        user = repo / ".factory" / "prompts" / agent / "user.md"
        assert sandbox.SENTINEL_LINE in user.read_text(encoding="utf-8")
        assert (repo / ".factory" / "prompts" / agent / "system.md").is_file()
    reviewer = repo / ".factory" / "prompts" / "reviewer"
    for name in ("user.md", "system.md"):
        assert fake_scripts.REVIEW_RULE_MARKER in (reviewer / name).read_text(encoding="utf-8")
    for agent in ("planner", "builder", "documenter"):
        text = (repo / ".factory" / "prompts" / agent / "user.md").read_text(encoding="utf-8")
        assert fake_scripts.REVIEW_RULE_MARKER not in text


def test_review_rule_is_not_in_the_product() -> None:
    offenders = [
        str(path.relative_to(AIFACTORY_DIR))
        for path in (AIFACTORY_DIR / "src").rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and RULE_TAG in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []


def test_no_prompt_names_outputs_by_adw_id() -> None:
    """Task outputs are named by the task run (`{{spec_path}}`, `{{doc_path}}`), never by adw_id."""
    offenders = [
        str(path.relative_to(AIFACTORY_DIR))
        for root in (AIFACTORY_DIR / "src", AIFACTORY_DIR / "validation")
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and not path.is_relative_to(AIFACTORY_DIR / "validation" / "results")
        # stock sssf prompts: factory onboard merges a repo's sssf prompts against them
        and not path.is_relative_to(AIFACTORY_DIR / "src" / "aifactory" / "onboard" / "sssf_stock")
        and "<adw_id>_" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []
    prompts = TEMPLATE_DIR / ".factory" / "prompts"
    for path in prompts.glob("*/*.md"):
        assert "<adw_id>" not in path.read_text(encoding="utf-8"), path
    assert "{{spec_path}}" in (prompts / "planner" / "user.md").read_text(encoding="utf-8")
    assert "{{doc_path}}" in (prompts / "documenter" / "user.md").read_text(encoding="utf-8")


def test_fake_rejection_passes_the_verdict_gate() -> None:
    rejection = dt.ReviewOutput.model_validate(fake_scripts.rejection("src/sandbox/cli.py"))
    assert rejection.approved is False
    assert fake_scripts.REVIEW_RULE_MARKER in rejection.blocking[0]
    assert verdict_consistent(rejection, None).passed


def test_resolved_mathx_has_both_functions_and_no_markers() -> None:
    text = fake_scripts.resolved_mathx()
    assert "def clamp" in text and "def lerp" in text
    assert '__all__: list[str] = ["clamp", "lerp"]' in text
    assert "<<<<<<<" not in text and ">>>>>>>" not in text
    namespace: dict[str, Any] = {}
    exec(compile(text, "mathx.py", "exec"), namespace)  # our own fixture text
    assert namespace["clamp"](5, 0, 3) == 3 and namespace["lerp"](0, 10, 0.5) == 5.0


def test_every_scripted_run_revises_the_first_written_file(repo: Path) -> None:
    for task_id, variant in (
        ("M01-S01-T01", "happy"),
        ("M01-S02-T01", "slugify_with_repair"),
        ("M02-S01-T02", "happy"),
    ):
        script = fake_scripts.script_for(task_id, variant)
        agents = script["agents"]
        assert [r["envelope"]["approved"] for r in agents["reviewer"]] == [False, True]
        revise = agents["builder"][-1]
        assert revise["edits"] == [fake_scripts.revise_edit(revise["envelope"]["changed_files"][0])]
    breach = fake_scripts.script_for("M01-S01-T03", "breach", repo=repo)
    paths = [e["path"] for e in breach["agents"]["builder"][0]["edits"]]
    assert str(repo / fake_scripts.BREACH_FILE) in paths
    assert "reviewer" not in breach["agents"]
    with pytest.raises(ValueError):
        fake_scripts.script_for("M01-S01-T03", "breach")
