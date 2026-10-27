"""Exercise the actual publication guard against a local Git remote."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.parametrize(
    ("changes", "publish"),
    [
        ([], True),
        (["factory/backlog/task.md"], True),
        (["docs/decisions.md", ".factory/config.yaml", "factory/backlog/task.md"], True),
        (["aifactory/src/aifactory/web/system.py"], False),
        (["factory/backlog/task.md", "aifactory/web/src/App.vue"], False),
        ([".github/workflows/ci.yml"], False),
    ],
)
def test_publication_guard(tmp_path: Path, changes: list[str], publish: bool) -> None:
    bash = shutil.which("bash")
    assert bash is not None, "Git Bash is required"
    remote = tmp_path / "remote"
    git(tmp_path, "init", "--initial-branch=main", str(remote))
    git(remote, "config", "user.name", "Release Test")
    git(remote, "config", "user.email", "release@example.invalid")
    git(remote, "commit", "--allow-empty", "-m", "built product")
    built = git(remote, "rev-parse", "HEAD")
    checkout = tmp_path / "checkout"
    git(tmp_path, "clone", str(remote), str(checkout))
    for name in changes:
        path = remote / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("new change\n", encoding="utf-8")
        git(remote, "add", name)
        git(remote, "commit", "-m", f"change {name}")

    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text()
    )
    steps = workflow["jobs"]["release"]["steps"]
    step = next(s for s in steps if s.get("name") == "Publish completed release")
    guard = step["run"].split('tag="v$VERSION"', 1)[0]
    result = subprocess.run(
        [bash, "-ec", guard + "\necho READY_TO_PUBLISH\n"],
        cwd=checkout,
        env={**os.environ, "GITHUB_SHA": built},
        capture_output=True,
        text=True,
        check=True,
    )
    assert ("READY_TO_PUBLISH" in result.stdout) is publish, result.stdout
