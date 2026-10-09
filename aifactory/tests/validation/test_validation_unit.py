"""Units of `just validate`: safe deletes, sandbox repo names, results, the fake, ``Cmd``."""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from validation.context import Cmd, parse_stdout
from validation.results import (
    FAILED,
    INCONCLUSIVE,
    PASSED,
    ScenarioResult,
    output_dir,
    write_result,
)
from validation.safety import Owned, UnsafeDelete, safe_rmtree

from aifactory import harness
from aifactory.engine import agents as engine_agents
from validation import fake, runner, sandbox

# ── safety ───────────────────────────────────────────────────────────────────


def test_safe_rmtree_deletes_inside_an_owned_root(tmp_path: Path) -> None:
    owned = Owned()
    root = owned.add(tmp_path / "work")
    (root / "a" / "b").mkdir(parents=True)
    assert safe_rmtree(root / "a", root, owned) is True
    assert not (root / "a").exists()
    assert safe_rmtree(root / "missing", root, owned) is False
    assert safe_rmtree(root, root, owned) is True
    assert not root.exists()


def test_safe_rmtree_refuses_outside_the_root(tmp_path: Path) -> None:
    owned = Owned()
    root = owned.add(tmp_path / "work")
    root.mkdir()
    outside = tmp_path / "keep"
    outside.mkdir()
    with pytest.raises(UnsafeDelete):
        safe_rmtree(outside, root, owned)
    with pytest.raises(UnsafeDelete):
        safe_rmtree(root / ".." / "keep", root, owned)
    with pytest.raises(UnsafeDelete):
        safe_rmtree(tmp_path, root, owned)
    assert outside.is_dir()


def test_safe_rmtree_refuses_a_root_it_does_not_own(tmp_path: Path) -> None:
    root = tmp_path / "work"
    (root / "a").mkdir(parents=True)
    with pytest.raises(UnsafeDelete):
        safe_rmtree(root / "a", root, Owned())
    assert (root / "a").is_dir()


# ── sandbox repo ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "acme/haifa-sandbox",
        "https://github.com/acme/haifa-sandbox",
        "https://github.com/acme/haifa-sandbox.git",
        "git@github.com:acme/haifa-sandbox.git",
        "  acme/haifa-sandbox  ",
    ],
)
def test_normalize_repo(value: str) -> None:
    assert sandbox.normalize_repo(value) == "acme/haifa-sandbox"


@pytest.mark.parametrize("value", [None, "", "just-a-name", "https://gitlab.com/a/b"])
def test_normalize_repo_rejects(value: str | None) -> None:
    with pytest.raises(sandbox.SetupError):
        sandbox.normalize_repo(value)


def test_github_without_sandbox_repo_exits_2_before_any_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"subprocess started: {args}")

    monkeypatch.delenv(runner.SANDBOX_ENV, raising=False)
    monkeypatch.setattr(runner, "_load_env", lambda: None)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    code = runner.main(
        [
            "--remote",
            "github",
            "--results-dir",
            str(tmp_path / "results"),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    assert code == runner.EXIT_SETUP
    assert "HAIFA_SANDBOX_REPO" in capsys.readouterr().err
    assert not (tmp_path / "results").exists()
    assert not (tmp_path / "work").exists()


def test_only_rejects_unknown_scenarios(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner, "_load_env", lambda: None)
    code = runner.main(["--only", "R1,R99", "--results-dir", str(tmp_path / "r")])
    assert code == runner.EXIT_SETUP


def test_f2_is_the_last_scenario_and_selectable() -> None:
    from validation.scenarios import ORDER

    assert [n for n, _ in ORDER][-1] == "F2"
    assert runner._selected("f2") == ["F2"]


# ── results ──────────────────────────────────────────────────────────────────


def test_outcome_rule() -> None:
    res = ScenarioResult("R2", "local")
    assert res.outcome == INCONCLUSIVE  # nothing verified
    res.check("a", True)
    assert res.outcome == PASSED
    res.check("b", False, "why")
    assert res.outcome == FAILED
    other = ScenarioResult("R10", "github")
    other.check("a", True)
    other.inconclusive("no repair round")
    assert other.outcome == INCONCLUSIVE
    assert other.observations == ["no repair round"]


def test_result_json_shape(tmp_path: Path) -> None:
    res = ScenarioResult("R2", "local")
    res.check("both_prs_opened", True, "2 PRs")
    res.observe("seen")
    res.add_run("ab12cd34")
    res.trace_sessions.append("trace/sessions/ab12cd34")
    res.measurements["overlap_s"] = 1.5
    res.finish()
    path = write_result(tmp_path, res)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "R2.json"
    assert set(data) == {
        "scenario", "risk", "remote", "outcome", "started_at", "ended_at", "duration_s",
        "checks", "observations", "evidence", "measurements",
    }  # fmt: skip
    assert data["outcome"] == PASSED
    assert data["risk"].startswith("Paralelní běhy")
    assert data["checks"] == [{"name": "both_prs_opened", "ok": True, "detail": "2 PRs"}]
    assert data["evidence"]["run_ids"] == ["ab12cd34"]
    assert data["evidence"]["trace"] == {
        "db": "trace/sssf.db",
        "sessions": ["trace/sessions/ab12cd34"],
        "files": [],
    }
    assert data["measurements"] == {"overlap_s": 1.5}


def test_output_dir() -> None:
    when = datetime.datetime(2026, 9, 27, 8, 5, 9)
    assert output_dir(Path("/r"), "local", when) == Path("/r/2026-09-27/local-080509")


def test_parse_stdout_skips_noise() -> None:
    assert parse_stdout('{"ok": true}') == {"ok": True}
    noisy = 'some child output\n{\n  "ok": false,\n  "error": {"code": "x"}\n}\n'
    assert parse_stdout(noisy) == {"ok": False, "error": {"code": "x"}}
    assert "unparsed_stdout" in parse_stdout("garbage")


# ── fake harness ─────────────────────────────────────────────────────────────


def test_fake_install_guards_the_real_adapters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(engine_agents, "INTERFACES", dict(engine_agents.INTERFACES))
    harness.install()
    for name in fake.HARNESS_NAMES:
        module = harness.load(name)
        # undone after the test, so later tests see the real adapters again
        monkeypatch.setattr(module, "run", module.run)
        monkeypatch.setattr(module, "resolve_model", module.resolve_model)
    script = tmp_path / "script.json"
    script.write_text('{"agents": {}}', encoding="utf-8", newline="\n")
    fakes = fake.install(script)
    for name in fake.HARNESS_NAMES:
        assert id(engine_agents.INTERFACES[name]) == id(fakes[name])
        with pytest.raises(fake.RealHarnessReached, match=fake.REAL_HARNESS_MESSAGE):
            harness.load(name).run(object())
        assert harness.load(name).resolve_model("any") == ("fake", "any")
    assert id(engine_agents.INTERFACES["claude_code"]) == id(fakes["claude"])


class _Request:
    def __init__(self, tmp_path: Path) -> None:
        self.session_dir = str(tmp_path / "data" / "builder" / "codex_sessions")
        self.cwd = str(tmp_path / "wt")
        self.model = "gpt-5.5"
        self.thinking = "low"
        self.session_id = "sssf-x-builder-1"
        self.raw_output_path = str(tmp_path / "data" / "builder" / "raw_output.jsonl")


def test_fake_harness_applies_edits_and_returns_the_envelope(tmp_path: Path) -> None:
    cwd = tmp_path / "wt"
    (cwd / "src").mkdir(parents=True)
    (cwd / "src" / "m.py").write_text("__all__ = []\n", encoding="utf-8", newline="\n")
    outside = tmp_path / "main" / "outside.md"
    entry = {
        "envelope": {"status": "success", "summary": "built", "changed_files": ["src/m.py"]},
        "edits": [
            {"path": "src/m.py", "replace": ["[]", '["f"]']},
            {"path": "src/m.py", "append": "def f(): ...\n"},
            {"path": "specs/x.md", "write": "# x\n"},
            {"path": str(outside), "write": "absolute\n"},
        ],
    }
    script_path = tmp_path / "script.json"
    harness_ = fake.FakeHarness("codex", {"agents": {"builder": [entry]}}, script_path)

    result = harness_.run(_Request(tmp_path))
    assert json.loads(result.text)["summary"] == "built"
    assert (cwd / "src" / "m.py").read_text(encoding="utf-8") == '__all__ = ["f"]\ndef f(): ...\n'
    assert (cwd / "specs" / "x.md").is_file()
    # an absolute path is written exactly there, not under the working directory
    assert outside.read_text(encoding="utf-8") == "absolute\n"
    assert not (cwd / Path(*outside.parts[1:])).exists()
    call = json.loads(
        script_path.with_name("script.json.calls.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert (call["harness"], call["agent"], call["model"]) == ("codex", "builder", "gpt-5.5")
    assert call["changed"][-1] == str(outside)
    raw = (
        (tmp_path / "data" / "builder" / "raw_output.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert json.loads(raw[0])["type"] == "validation.fake"
    with pytest.raises(RuntimeError, match="no scripted entry"):
        harness_.run(_Request(tmp_path))


_TASK_PROMPT = (
    "# Plan\n\n## Variables\n\nsee `docs/readme.md`\n\n## Task\n\n"
    "1. Write `<context_handoff_dir>/plan.md`.\n"
    "2. Copy it as `{spec}`; run `mkdir -p specs`.\n"
    "3. Also mention `app_docs/other.md`.\n"
)


def test_output_path_is_the_first_repo_path_of_the_task_section() -> None:
    prompt = _TASK_PROMPT.format(spec="specs/T1-x.md")
    assert fake.output_path(prompt, "abcd1234") == "specs/T1-x.md"


def test_output_path_fills_placeholders_like_an_agent() -> None:
    prompt = _TASK_PROMPT.format(spec="specs/<adw_id>_<slug>.md")
    assert fake.output_path(prompt, "abcd1234") == "specs/abcd1234_slug.md"


def test_output_path_needs_a_task_section_and_a_path() -> None:
    with pytest.raises(ValueError, match="Task"):
        fake.output_path("no sections here `specs/a.md`", "abcd1234")
    with pytest.raises(ValueError, match="no output path"):
        fake.output_path("## Task\n\nWrite `<context_handoff_dir>/plan.md`.\n", "abcd1234")


def test_fake_harness_writes_the_output_the_prompt_names(tmp_path: Path) -> None:
    (tmp_path / "wt").mkdir()
    request = _Request(tmp_path)
    request.session_dir = str(tmp_path / "sessions" / "abcd1234" / "planner" / "codex_sessions")
    request.prompt = _TASK_PROMPT.format(spec="specs/T1-x.md")  # type: ignore[attr-defined]
    entry = {
        "envelope": {"status": "success", "summary": "planned", "artifacts": [fake.OUTPUT]},
        "edits": [{"path": fake.OUTPUT, "write": "# plan\n"}],
    }
    script_path = tmp_path / "script.json"
    harness_ = fake.FakeHarness("codex", {"agents": {"planner": [entry]}}, script_path)

    result = harness_.run(request)
    assert json.loads(result.text)["artifacts"] == ["specs/T1-x.md"]
    assert (tmp_path / "wt" / "specs" / "T1-x.md").read_text(encoding="utf-8") == "# plan\n"
    call = json.loads(
        script_path.with_name("script.json.calls.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert call["output"] == "specs/T1-x.md"
    assert call["changed"] == ["specs/T1-x.md"]


def test_fake_replace_needs_the_anchor(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="not found"):
        fake.apply_edits(tmp_path, [{"path": "a.py", "replace": ["y = 2", "y = 3"]}])


# ── Cmd ──────────────────────────────────────────────────────────────────────


def test_cmd_reads_the_envelope(tmp_path: Path) -> None:
    run = {"run_id": "ab12", "state": "failed", "error": "boom"}
    data = {
        "ok": False,
        "data": {"run": run, "pr": None, "pr_error": None},
        "error": {"code": "run_failed", "message": "boom"},
        "warnings": ["agents.yaml is modified"],
    }
    cmd = Cmd(["task", "run"], 1, data, tmp_path / "log")
    assert cmd.ok is False
    assert cmd.error_code == "run_failed"
    assert cmd.run == run
    assert cmd.pr == {}
    assert cmd.warnings == ["agents.yaml is modified"]
    assert cmd.brief() == "exit 1: run_failed: boom"

    good = Cmd(
        ["task", "approve"],
        0,
        {"ok": True, "data": {"merge_sha": "f00"}, "error": None, "warnings": []},
        tmp_path / "log",
    )
    assert good.ok is True
    assert good.error_code is None
    assert good.payload == {"merge_sha": "f00"}
    assert good.run == {} and good.warnings == []
    # exit 0 without an ok envelope is not ok
    assert Cmd([], 0, {}, tmp_path / "log").ok is False


@pytest.mark.parametrize("release_mode", ["existing", "during", "timeout"])
def test_fake_wait_for_file(tmp_path: Path, release_mode: str) -> None:
    from concurrent.futures import ThreadPoolExecutor

    (tmp_path / "wt").mkdir()
    release = tmp_path / "release"
    script = tmp_path / "gate.json"
    calls = script.with_name("gate.json.calls.jsonl")
    entry = {
        "wait_for_file": str(release),
        "wait_timeout_s": 2 if release_mode != "timeout" else 0.01,
    }
    harness_ = fake.FakeHarness("codex", {"agents": {"builder": [entry]}}, script)
    if release_mode == "existing":
        release.touch()
        assert harness_.run(_Request(tmp_path)).returncode == 0
    elif release_mode == "timeout":
        with pytest.raises(TimeoutError, match=str(release)):
            harness_.run(_Request(tmp_path))
        assert calls.exists()
    else:
        import time

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(harness_.run, _Request(tmp_path))
            try:
                deadline = time.monotonic() + 1
                while not calls.exists() and time.monotonic() < deadline:
                    time.sleep(0.005)
                assert calls.exists()
                assert not future.done()
            finally:
                release.touch()
            assert future.result(timeout=2).returncode == 0


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_fake_gate_rejects_unbounded_timeout(tmp_path: Path, timeout: float) -> None:
    (tmp_path / "wt").mkdir()
    entry = {"wait_for_file": str(tmp_path / "release"), "wait_timeout_s": timeout}
    harness_ = fake.FakeHarness("codex", {"agents": {"builder": [entry]}}, tmp_path / "fake.json")
    with pytest.raises(ValueError, match="finite timeout"):
        harness_.run(_Request(tmp_path))


def test_isolated_haifa_home_leaves_out_machine_harness_choices(tmp_path: Path) -> None:
    real = tmp_path / "real"
    (real / "library").mkdir(parents=True)
    (real / "env").write_text("KEY=value\n", encoding="utf-8")
    (real / "harnesses.json").write_text('{"default_harness": "codex"}', encoding="utf-8")
    (real / "harness-tests.json").write_text("{}", encoding="utf-8")
    workdir = tmp_path / "work"

    home = runner.isolated_haifa_home(workdir, real)

    assert sorted(p.name for p in home.iterdir()) == ["env", "library"]
    assert (home / "env").read_text(encoding="utf-8") == "KEY=value\n"
    owned = Owned()
    owned.add(workdir)
    safe_rmtree(workdir, workdir, owned)
    assert (real / "env").exists() and (real / "library").is_dir()


def test_isolated_haifa_home_without_a_real_home_is_empty(tmp_path: Path) -> None:
    home = runner.isolated_haifa_home(tmp_path / "work", tmp_path / "missing")
    assert home.is_dir() and not any(home.iterdir())
