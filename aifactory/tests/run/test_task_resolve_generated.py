"""``factory task resolve`` with a generated output in conflict (``generated:`` in config).

Both tasks change the model and the "bundle" built from it (``src/app/static/``).
The resolve agent settles the model only; code rebuilds the bundle with a fake
build command (a Python script in the repo) and commits it with the resolution.
No test calls a model: the harnesses and the suite are scripted.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import SPEC, T01, T02, Script, commit_all, fake_env, git, make_run_repo, ok, write
from workflow_fakes import FakeCodeRunner

from aifactory.config import ProjectSettings
from aifactory.review import approve_task, resolve_task
from aifactory.run import TaskRunResult, run_task
from aifactory.workflow import EngineCodeRunner

MODEL = "src/app/model.py"
STATIC = "src/app/static"
INDEX = f"{STATIC}/index.html"
SPEC2 = "specs/M01-S01-T02-loader.md"
BRANCH2 = f"factory/{T02}-1"
BUILD_LOG = "build.log"

# The fake `just web-build`: empties the output and writes a bundle named by the
# model's content, like vite does with a hashed asset name. It records every
# run in an ignored log so a test can count the builds.
BUILD = """\
import hashlib, pathlib, shutil
root = pathlib.Path.cwd()
source = (root / "src/app/model.py").read_text(encoding="utf-8")
out = root / "src/app/static"
shutil.rmtree(out, ignore_errors=True)
(out / "assets").mkdir(parents=True)
digest = hashlib.sha256(source.encode()).hexdigest()[:8]
(out / "assets" / f"index-{digest}.js").write_text(f"// {source}", encoding="utf-8")
(out / "index.html").write_text(f"<script src=assets/index-{digest}.js>\\n", encoding="utf-8")
with open(root / "build.log", "a", encoding="utf-8") as log:
    log.write("built\\n")
"""


class ResolveCode(FakeCodeRunner):
    """A real ``rebase`` and ``rebuild`` step and a scripted suite."""

    def rebase(self, run: Any) -> Any:
        return EngineCodeRunner().rebase(run)

    def rebuild(self, run: Any, files: list[str]) -> Any:
        self.rebuilds.append(list(files))
        return EngineCodeRunner().rebuild(run, files)


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    repo = make_run_repo(tmp_path / "repo")
    write(repo, MODEL, "VALUE = 0\n")
    write(repo, INDEX, "<script src=assets/index-base.js>\n")
    write(repo, f"{STATIC}/assets/index-base.js", "// base\n")
    write(repo, "tools/build.py", BUILD)
    write(repo, ".gitignore", ".factory/local.yaml\nbuild.log\n")
    command = [sys.executable, "tools/build.py"]
    write(
        repo,
        ".factory/config.yaml",
        f"base: main\ngenerated:\n  - path: {STATIC}/\n    command: {command!r}\n",
    )
    commit_all(repo, "model, bundle and build")
    return repo


def bundle(value: int, name: str) -> dict[str, str]:
    """What a task run writes: the model and a hand-made bundle with its own asset name."""
    return {
        MODEL: f"VALUE = {value}\n",
        INDEX: f"<script src=assets/index-{name}.js>\n",
        f"{STATIC}/assets/index-{name}.js": f"// {value}\n",
    }


def plan(script: Script, spec: str, changes: dict[str, str], *, drop_base: bool = True) -> None:
    def effect(wt: Path) -> None:
        write(wt, spec, "# spec\n")
        for rel, text in changes.items():
            write(wt, rel, text)
        if drop_base and INDEX in changes:
            (wt / STATIC / "assets" / "index-base.js").unlink(missing_ok=True)

    script.on("planner", effect)
    script.add("planner", ok(artifacts=[spec], commit_message=f"Plan {spec}"))


def run_both(repo: Path, script: Script, first: dict[str, str], second: dict[str, str]) -> None:
    plan(script, SPEC, first)
    one = run_task(repo, T01)
    assert one.ok, (one.run.error, one.pr_error)
    plan(script, SPEC2, second)
    two = run_task(repo, T02, force=True)
    assert two.ok, (two.run.error, two.pr_error)
    approve_task(repo, T01)


def resolver(script: Script, *changes: tuple[str, str]) -> None:
    def effect(wt: Path) -> None:
        for rel, text in changes:
            write(wt, rel, text)

    script.on("builder", effect)
    script.add("builder", ok(changed_files=[rel for rel, _ in changes]))


def tip(repo: Path) -> str:
    return git(repo, "rev-parse", f"refs/heads/{BRANCH2}")


def branch_files(repo: Path, folder: str) -> list[str]:
    return git(repo, "ls-tree", "-r", "--name-only", BRANCH2, "--", folder).splitlines()


def builds(result: TaskRunResult) -> int:
    log = Path(result.run.worktree) / BUILD_LOG
    return len(log.read_text(encoding="utf-8").splitlines()) if log.is_file() else 0


def test_config_names_generated_outputs() -> None:
    static = "./aifactory/src/aifactory/web/static/"
    settings = ProjectSettings.model_validate(
        {"generated": [{"path": static, "command": "just web-build"}]}
    )
    (output,) = settings.generated
    assert output.path == "aifactory/src/aifactory/web/static/"
    assert output.command == ("just", "web-build")
    assert output.timeout == 600
    bad_entries = (
        {"path": "../out", "command": "x"},
        {"path": "out", "command": ""},
        {"path": "out"},
    )
    for bad in bad_entries:
        with pytest.raises(ValueError):
            ProjectSettings.model_validate({"generated": [bad]})


def test_conflicted_bundle_is_rebuilt(repo: Path, script: Script) -> None:
    run_both(repo, script, bundle(1, "one"), bundle(2, "two"))
    resolver(script, (MODEL, "VALUE = 3\n"))
    code = ResolveCode([True])

    result = resolve_task(repo, T02, code=code)

    assert result.ok, (result.run.error, result.pr_error)
    builder = [c for c in script.calls if c.agent == "builder"]
    assert len(builder) == 1
    assert STATIC in builder[0].prompt and "code rebuilds them" in builder[0].prompt
    assert INDEX in code.rebuilds[0]
    assert builds(result) == 1
    assert git(repo, "show", f"{BRANCH2}:{MODEL}") == "VALUE = 3"
    assets = branch_files(repo, f"{STATIC}/assets")
    assert len(assets) == 1
    name = assets[0]
    assert git(repo, "show", f"{BRANCH2}:{name}") == "// VALUE = 3"
    assert git(repo, "show", f"{BRANCH2}:{INDEX}") == f"<script src=assets/{Path(name).name}>"
    message = git(repo, "log", "-1", "--format=%s", BRANCH2)
    assert f"rebuild {STATIC}/" in message
    assert git(Path(result.run.worktree), "status", "--porcelain") == ""
    assert "breach" not in (result.run.error or "")


def test_resolver_may_not_touch_the_bundle(repo: Path, script: Script) -> None:
    run_both(repo, script, bundle(1, "one"), bundle(2, "two"))
    before = tip(repo)
    resolver(script, (MODEL, "VALUE = 3\n"), (INDEX, "<script src=assets/index-hand.js>\n"))

    result = resolve_task(repo, T02, code=ResolveCode([True]))

    assert result.run.state == "failed"
    assert result.run.error is not None and INDEX in result.run.error
    assert tip(repo) == before
    assert builds(result) == 0


def test_conflict_only_in_sources_builds_nothing(repo: Path, script: Script) -> None:
    run_both(
        repo,
        script,
        {MODEL: "VALUE = 1\n"},
        {MODEL: "VALUE = 2\n"},
    )
    resolver(script, (MODEL, "VALUE = 3\n"))
    code = ResolveCode([True])

    result = resolve_task(repo, T02, code=code)

    assert result.ok, (result.run.error, result.pr_error)
    assert code.rebuilds == [[MODEL]]
    assert builds(result) == 0
    assert git(repo, "show", f"{BRANCH2}:{MODEL}") == "VALUE = 3"
    assert git(repo, "show", f"{BRANCH2}:{INDEX}") == "<script src=assets/index-base.js>"
    message = git(repo, "log", "-1", "--format=%s", BRANCH2)
    assert "rebuild" not in message
