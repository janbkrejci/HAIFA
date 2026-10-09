"""A fake `gh` executable on PATH: logs argv and stdin, answers from a script."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from fake_exe import make_executable

_SCRIPT = """\
import json, os, sys
here = os.environ["AIFACTORY_FAKE_GH_STATE"]
args = sys.argv[1:]
stdin = sys.stdin.read()
with open(os.path.join(here, "calls.jsonl"), "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": args, "stdin": stdin, "cwd": os.getcwd()}) + "\\n")
path = os.path.join(here, "responses.json")
with open(path, encoding="utf-8") as f:
    responses = json.load(f)
key = " ".join(args[:2])
answer = responses.get(key, {"stdout": "", "exit": 0})
if isinstance(answer, list):
    current = answer[0] if len(answer) == 1 else answer.pop(0)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(responses, f)
    answer = current
sys.stdout.write(answer.get("stdout", ""))
sys.stderr.write(answer.get("stderr", ""))
sys.exit(int(answer.get("exit", 0)))
"""


_shared_bin: Path | None = None


def write_fake_gh(bin_dir: Path) -> Path:
    """Write the `gh` script into `bin_dir`; per-test state lives in $AIFACTORY_FAKE_GH_STATE."""
    global _shared_bin
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh = bin_dir / "gh"
    body = f"#!{sys.executable}\n{_SCRIPT}"
    # Windows: make_executable moves the script to gh.script beside gh.exe
    script = bin_dir / "gh.script" if sys.platform == "win32" else gh
    if not script.is_file() or script.read_text(encoding="utf-8") != body:
        tmp = bin_dir / f".gh.{os.getpid()}"
        tmp.write_text(body, encoding="utf-8", newline="\n")
        tmp.chmod(0o755)
        os.replace(tmp, gh)  # atomic: xdist workers may race on the shared path
        if sys.platform == "win32":
            make_executable(gh)
    _shared_bin = bin_dir
    return gh


def _user() -> str:
    return str(os.getuid()) if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")


def shared_bin_dir() -> Path:
    """A stable per-user directory for the fake `gh`, keyed by its content.

    macOS checks the first exec of every new executable file, which costs seconds
    (much more under load); reusing the same file across sessions pays that once.
    """
    key = hashlib.sha256(f"{sys.executable}\n{_SCRIPT}".encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"aifactory-fake-gh-{_user()}-{key}"


@dataclass
class GhLog:
    state_dir: Path

    def calls(self) -> list[dict[str, Any]]:
        log = self.state_dir / "calls.jsonl"
        if not log.is_file():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    def argvs(self) -> list[list[str]]:
        return [c["argv"] for c in self.calls()]

    def respond(self, key: str, answer: dict[str, Any] | list[dict[str, Any]]) -> None:
        path = self.state_dir / "responses.json"
        responses = json.loads(path.read_text(encoding="utf-8"))
        responses[key] = answer
        path.write_text(json.dumps(responses), encoding="utf-8", newline="\n")

    def clear(self) -> None:
        (self.state_dir / "calls.jsonl").unlink(missing_ok=True)


def reply(stdout: object = "", exit: int = 0, stderr: str = "") -> dict[str, Any]:
    text = stdout if isinstance(stdout, str) else json.dumps(stdout)
    return {"stdout": text, "exit": exit, "stderr": stderr}


def install_fake_gh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, dict[str, Any] | list[dict[str, Any]]] | None = None,
) -> GhLog:
    bin_dir = _shared_bin
    if bin_dir is None:
        write_fake_gh(tmp_path / "bin")
        bin_dir = tmp_path / "bin"
    state_dir = tmp_path / "gh_state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "responses.json").write_text(
        json.dumps(responses or {}), encoding="utf-8", newline="\n"
    )
    monkeypatch.setenv("AIFACTORY_FAKE_GH_STATE", str(state_dir))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.delenv("AIFACTORY_GH", raising=False)
    return GhLog(state_dir)


def prepare_shared_gh(tmp_dir: Path) -> None:
    """Write the fake `gh` once to the shared directory and run it once.

    If the script is new, macOS checks its first exec (slow); pay that here, not in a test.
    """
    gh = write_fake_gh(shared_bin_dir())
    (tmp_dir / "responses.json").write_text("{}", encoding="utf-8", newline="\n")
    subprocess.run(
        [str(gh), "--version"],
        env={**os.environ, "AIFACTORY_FAKE_GH_STATE": str(tmp_dir)},
        capture_output=True,
        check=False,
    )
