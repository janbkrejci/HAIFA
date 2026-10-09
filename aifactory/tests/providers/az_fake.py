"""A fake `az` executable on PATH: logs argv (and ``--in-file`` content), answers from a script.

Answers are keyed by the argv words before the first ``--option`` (``"repos pr show"``,
``"devops invoke"``, ``"account show"``); ``"--version"`` when there are none. The
JSON helpers follow the ``az repos pr`` docs (a camelCase GitPullRequest object).
"""

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
here = os.environ["AIFACTORY_FAKE_AZ_STATE"]
args = sys.argv[1:]
stdin = sys.stdin.read()
in_file = None
if "--in-file" in args:
    idx = args.index("--in-file") + 1
    if idx < len(args):
        with open(args[idx], encoding="utf-8") as f:
            text = f.read()
        try:
            in_file = json.loads(text)
        except ValueError:
            in_file = text
entry = {"argv": args, "stdin": stdin, "cwd": os.getcwd(), "in_file": in_file}
with open(os.path.join(here, "calls.jsonl"), "a", encoding="utf-8") as log:
    log.write(json.dumps(entry) + "\\n")
path = os.path.join(here, "responses.json")
with open(path, encoding="utf-8") as f:
    responses = json.load(f)
words = []
for arg in args:
    if arg.startswith("--"):
        break
    words.append(arg)
key = " ".join(words) or (args[0] if args else "")
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

HEAD = "a" * 40
MERGE_SHA = "b" * 40
TARGET_SHA = "c" * 40
ORG_URL = "https://dev.azure.com/contoso"
WEB_URL = f"{ORG_URL}/Fab%20Rikam/_git/app"

_shared_bin: Path | None = None


def write_fake_az(bin_dir: Path) -> Path:
    """Write the `az` script into `bin_dir`; per-test state lives in $AIFACTORY_FAKE_AZ_STATE."""
    global _shared_bin
    bin_dir.mkdir(parents=True, exist_ok=True)
    az = bin_dir / "az"
    body = f"#!{sys.executable}\n{_SCRIPT}"
    # Windows: make_executable moves the script to az.script beside az.exe
    script = bin_dir / "az.script" if sys.platform == "win32" else az
    executable = bin_dir / "az.exe" if sys.platform == "win32" else az
    if (
        not script.is_file()
        or script.read_text(encoding="utf-8") != body
        or not executable.is_file()
    ):
        tmp = bin_dir / f".az.{os.getpid()}"
        tmp.write_text(body, encoding="utf-8", newline="\n")
        tmp.chmod(0o755)
        os.replace(tmp, az)  # atomic: xdist workers may race on the shared path
        if sys.platform == "win32":
            make_executable(az)
    _shared_bin = bin_dir
    return executable


def _user() -> str:
    return str(os.getuid()) if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")


def shared_bin_dir() -> Path:
    """Cache fake `az` by content; isolate Windows workers' launcher creation."""
    key = hashlib.sha256(f"{sys.executable}\n{_SCRIPT}".encode()).hexdigest()[:16]
    # make_executable renames az to az.script: concurrent creators cannot share
    # that intermediate file on Windows. Each worker still warms its fake once.
    if sys.platform == "win32":
        key += f"-{os.getpid()}"
    return Path(tempfile.gettempdir()) / f"aifactory-fake-az-{_user()}-{key}"


@dataclass
class AzLog:
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


def call_key(argv: list[str]) -> str:
    words: list[str] = []
    for arg in argv:
        if arg.startswith("--"):
            break
        words.append(arg)
    return " ".join(words) or (argv[0] if argv else "")


def reply(stdout: object = "", exit: int = 0, stderr: str = "") -> dict[str, Any]:
    text = stdout if isinstance(stdout, str) else json.dumps(stdout)
    return {"stdout": text, "exit": exit, "stderr": stderr}


def pr_json(
    id: int = 7,
    status: str = "active",
    merge_status: str = "succeeded",
    head: str = HEAD,
    merge: str | None = None,
    web_url: str | None = WEB_URL,
    source: str = "factory/T01-1",
    target: str = "main",
) -> dict[str, Any]:
    """A PR object as ``az repos pr create/show/update`` prints it."""
    repository: dict[str, Any] = {
        "id": "3411ebc1-d5aa-464f-9615-0b527bc66719",
        "name": "app",
        "url": f"{ORG_URL}/_apis/git/repositories/3411ebc1-d5aa-464f-9615-0b527bc66719",
        "project": {"id": "a7573007-bbb3-4341-b726-0c4148a07853", "name": "Fab Rikam"},
    }
    if web_url is not None:
        repository["webUrl"] = web_url
    data: dict[str, Any] = {
        "pullRequestId": id,
        "codeReviewId": id,
        "status": status,
        "mergeStatus": merge_status,
        "isDraft": False,
        "title": "T01: title",
        "description": "the body",
        "sourceRefName": f"refs/heads/{source}",
        "targetRefName": f"refs/heads/{target}",
        "lastMergeSourceCommit": {
            "commitId": head,
            "url": f"{repository['url']}/commits/{head}",
        },
        "lastMergeTargetCommit": {
            "commitId": TARGET_SHA,
            "url": f"{repository['url']}/commits/{TARGET_SHA}",
        },
        "repository": repository,
        "createdBy": {"displayName": "Factory Bot", "uniqueName": "bot@contoso.com"},
        "creationDate": "2026-09-27T10:00:00.000000+00:00",
        "closedDate": "2026-09-27T11:00:00.000000+00:00" if status != "active" else None,
        "mergeId": "f5fc8381-3fb2-49fe-8a0d-27dcc2d6ef82",
        "url": f"{repository['url']}/pullRequests/{id}",
        "completionOptions": None,
    }
    if merge is not None:
        data["lastMergeCommit"] = {"commitId": merge, "url": f"{repository['url']}/commits/{merge}"}
    return data


def thread_json(content: str = "hello") -> dict[str, Any]:
    """A thread as ``az devops invoke ... pullRequestThreads POST`` prints it."""
    return {
        "id": 1,
        "status": "active",
        "publishedDate": "2026-09-27T10:05:00.000Z",
        "lastUpdatedDate": "2026-09-27T10:05:00.000Z",
        "comments": [
            {
                "id": 1,
                "parentCommentId": 0,
                "content": content,
                "commentType": "text",
                "author": {"displayName": "Factory Bot"},
            }
        ],
    }


def install_fake_az(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, dict[str, Any] | list[dict[str, Any]]] | None = None,
) -> AzLog:
    bin_dir = _shared_bin
    if bin_dir is None:
        write_fake_az(tmp_path / "bin")
        bin_dir = tmp_path / "bin"
    state_dir = tmp_path / "az_state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "responses.json").write_text(
        json.dumps(responses or {}), encoding="utf-8", newline="\n"
    )
    monkeypatch.setenv("AIFACTORY_FAKE_AZ_STATE", str(state_dir))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.delenv("AIFACTORY_AZ", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_EXT_PAT", raising=False)
    return AzLog(state_dir)


def prepare_shared_az(tmp_dir: Path) -> None:
    """Write the fake `az` once to the shared directory and run it once (see gh_fake)."""
    az = write_fake_az(shared_bin_dir())
    (tmp_dir / "responses.json").write_text("{}", encoding="utf-8", newline="\n")
    subprocess.run(
        [str(az), "--version"],
        env={**os.environ, "AIFACTORY_FAKE_AZ_STATE": str(tmp_dir)},
        capture_output=True,
        check=False,
    )
