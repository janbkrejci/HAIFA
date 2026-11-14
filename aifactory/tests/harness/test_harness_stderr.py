"""Real pipes must keep flowing even when an agent fills stderr before stdout."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from harness_fakes import MODELS, NAMES, fake_pi_catalog, stream

from aifactory import harness
from aifactory.engine.data_types import AgentRequest
from aifactory.failure import QuotaExhausted
from aifactory.harness import codex


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("outcome", ["success", "failure", "quota", "stop"])
def test_stderr_cannot_block_stdout_or_process_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, outcome: str
) -> None:
    fake_pi_catalog(monkeypatch, tmp_path)
    monkeypatch.setattr(codex, "launch_command", lambda cmd: cmd)
    output = tmp_path / "stdout.jsonl"
    output.write_text(
        stream(name, "done") if outcome == "success" else '{"type":"audit"}\n',
        encoding="utf-8",
    )
    # The quota marker precedes the flood: draining must retain the whole diagnostic.
    child = r"""
import pathlib, sys, time
assert sys.stdin.read() == 'audit prompt'
sys.stderr.write(('usage limit\n' if sys.argv[2] == 'quota' else '') + 'x' * 1048576)
sys.stderr.write('\nstderr diagnostic\n')
sys.stderr.flush()
sys.stdout.write(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
sys.stdout.flush()
if sys.argv[2] == 'stop':
    time.sleep(30)
sys.exit(0 if sys.argv[2] == 'success' else 7)
"""
    real_popen = subprocess.Popen
    children: list[subprocess.Popen[str]] = []
    timers: list[threading.Timer] = []
    expired = threading.Event()

    def spawn(cmd: Any, **kwargs: Any) -> subprocess.Popen[str]:
        process = real_popen([sys.executable, "-c", child, str(output), outcome], **kwargs)
        children.append(process)

        def timeout() -> None:
            expired.set()
            process.kill()

        timer = threading.Timer(10, timeout)
        timers.append(timer)
        timer.start()
        return process

    monkeypatch.setattr(subprocess, "Popen", spawn)
    request = AgentRequest(
        prompt="audit prompt",
        system_prompt="system",
        model=MODELS[name],
        session_id="stderr-test",
        session_dir=str(tmp_path / "sessions"),
        raw_output_path=str(tmp_path / "raw.jsonl"),
        cwd=str(tmp_path),
    )
    events: list[dict[str, Any]] = []
    spawned: list[int] = []
    exited: list[int] = []

    def on_event(event: dict[str, Any]) -> None:
        events.append(event)
        if outcome == "stop":
            children[0].terminate()

    def run() -> Any:
        return harness.load(name).run(
            request, on_event=on_event, on_spawn=spawned.append, on_exit=exited.append
        )

    try:
        if outcome == "success":
            result = run()
            assert result.returncode == 0 and result.text == "done"
        elif outcome == "quota":
            with pytest.raises(QuotaExhausted):
                run()
        else:
            with pytest.raises(RuntimeError, match="stderr diagnostic"):
                run()
        assert not expired.is_set(), "stderr filled its pipe and blocked the child"
        assert events
        assert spawned == exited == [children[0].pid]
        assert (tmp_path / "raw.jsonl").read_text(encoding="utf-8") == output.read_text(
            encoding="utf-8"
        )
    finally:
        for timer in timers:
            timer.cancel()
            timer.join()
        for process in children:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
