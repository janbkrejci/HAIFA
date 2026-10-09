"""The fake harness takes the task outputs from the rendered prompt.

A planner prompt that names the spec by adw_id makes the local validation fail
the way the real run fails against the write guard (``run_failed``); the
prompt with ``{{spec_path}}`` passes. No model is called: the fake harness
serves every agent and a tripwire stands in for the real CLIs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from validation.context import parse_stdout
from validation.sandbox import AIFACTORY_DIR, git

from fake_exe import make_executable
from validation import fake_scripts, sandbox

TASK = "M01-S01-T01"
STEM = fake_scripts.TASK_STEMS[TASK]


def _tripwire(directory: Path, marker: Path) -> Path:
    script = directory / "tripwire"
    script.write_text(
        f'#!/bin/sh\necho "$0 $*" >> "{marker}"\nexit 97\n', encoding="utf-8", newline="\n"
    )
    return make_executable(script)


def _calls(script: Path) -> list[dict[str, object]]:
    log = script.with_name(script.name + ".calls.jsonl")
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


@pytest.mark.skipif(shutil.which("just") is None, reason="just is not on PATH")
@pytest.mark.parametrize("naming", ["spec_path", "adw_id"])
def test_prompt_output_naming_meets_the_write_guard(tmp_path: Path, naming: str) -> None:
    work = tmp_path / "work"
    work.mkdir()
    sb = sandbox.setup_local(work)
    repo = sb.repo
    planner = repo / ".factory" / "prompts" / "planner" / "user.md"
    if naming == "adw_id":
        text = planner.read_text(encoding="utf-8")
        assert "{{spec_path}}" in text
        planner.write_text(
            text.replace("{{spec_path}}", "specs/<adw_id>_<slug>.md"), "utf-8", newline="\n"
        )
        # a task run reads its prompts from the base commit
        git(repo, "commit", "-q", "-am", "name the spec by adw_id")
        git(repo, "push", "-q", "origin", "main")

    marker = tmp_path / "real-harness-reached"
    tripwire = _tripwire(tmp_path, marker)
    script = tmp_path / "script.json"
    script.write_text(
        json.dumps(fake_scripts.script_for(TASK, repo=repo)), encoding="utf-8", newline="\n"
    )
    env = dict(os.environ)
    for key in ("HAIFA_SANDBOX_REPO", "HAIFA_VALIDATE_HIDDEN"):
        env.pop(key, None)
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(
                p for p in (str(AIFACTORY_DIR), env.get("PYTHONPATH", "")) if p
            ),
            "HAIFA_VALIDATE_FAKE": str(script),
            "AIFACTORY_GH": str(tripwire),
            "CODEX_PATH": str(tripwire),
            "CLAUDE_CODE_PATH": str(tripwire),
            "PI_PATH": str(tripwire),
            "UV_NO_SYNC": "1",
        }
    )
    proc = subprocess.run(
        [sys.executable, "-m", "validation.worker", "task", "run", TASK]
        + ["--repo", str(repo), "--json"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        encoding="utf-8",
    )
    data = parse_stdout(proc.stdout)
    calls = _calls(script)
    agents = [c["agent"] for c in calls]

    if naming == "adw_id":
        assert proc.returncode == 1, (proc.stdout[-2000:], proc.stderr[-2000:])
        assert data["error"]["code"] == "run_failed"
        assert "outside its task run" in json.dumps(data), data
        assert "documenter" not in agents
        planned = next(c for c in calls if c["agent"] == "planner")
        assert str(planned["output"]).startswith("specs/") and "_slug.md" in str(planned["output"])
    else:
        assert proc.returncode == 0, (proc.stdout[-2000:], proc.stderr[-2000:])
        assert data["ok"] is True
        outputs = {c["agent"]: c["output"] for c in calls if c.get("output")}
        assert outputs == {"planner": f"specs/{STEM}.md", "documenter": f"app_docs/{STEM}.md"}
    assert not marker.exists(), marker.read_text(encoding="utf-8")
