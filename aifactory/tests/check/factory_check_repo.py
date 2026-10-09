"""Temporary git repos and a fake machine for ``factory check`` tests (helpers, not fixtures).

No helper calls a model, the network, ``gh``, ``az`` or a harness: the check asks the
machine only through ``FakeMachine``.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import repo_templates
from aifactory.check import Probe
from aifactory.harness import CLI_BINARIES
from aifactory.harness.check import HarnessStatus

AGENTS_YAML = """\
defaults:
  harness: claude
  model: sonnet
agents:
  - name: planner
    model: opus
  - name: builder
"""

GITIGNORE = ".factory/local.yaml\n.factory/trace.db*\n.factory/worktrees/\n.factory/data/\n"

TASK = "M01-S01-T01"

FILES = {
    ".gitignore": GITIGNORE,
    ".factory/config.yaml": "base: main\n",
    ".factory/agents.yaml": AGENTS_YAML,
    ".factory/prompts/planner/system.md": "You are the planner.\n",
    ".factory/prompts/planner/user.md": "Plan this: {{prompt}}\n",
    ".factory/prompts/builder/system.md": "You are the builder.\n",
    ".factory/prompts/builder/user.md": "Build this: {{prompt}}\n",
    ".factory/workflows/plan-build.yaml": (
        "name: plan-build\ndescription: Plan the task, then build it\nsteps: [plan, build]\n"
    ),
    "justfile": "# recipes\nset positional-arguments\n\ndefault:\n    @just --list\n\n"
    "test *ARGS:\n    echo test\n",
    "backlog/M01-core/index.md": "---\nid: M01\ntitle: Core\nworkflow: plan-build\n---\n",
    "backlog/M01-core/S01-model/index.md": "---\nid: M01-S01\ntitle: Model\n---\n",
    f"backlog/M01-core/S01-model/{TASK}-schema.md": (
        f"---\nid: {TASK}\ntitle: Schema\nstatus: todo\n---\n\n## Zadání\nSchéma.\n"
    ),
}


def git(repo: Path, *args: str) -> str:
    env = dict(os.environ)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    proc = subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
    )
    return proc.stdout


def write(repo: Path, rel: str, text: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD").strip()


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    return path


def make_check_repo(path: Path) -> Path:
    """A git repo on ``main`` with ``.factory/``, a justfile and a one-task backlog committed."""
    repo_templates.build(path, "factory-check", _build)
    return path.resolve()


def _build(path: Path) -> None:
    init_repo(path)
    for rel, text in FILES.items():
        write(path, rel, text)
    commit_all(path, "factory")


GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


@dataclass
class FakeMachine:
    """A machine where ``present`` programs are on PATH and logins are ``logged_in``.

    ``outputs`` answers exact argv tuples (pi JSON, ``pi --list-models``); ``modes``
    overrides the permission bits of files; ``environment()`` carries the temporary
    ``HAIFA_HOME`` of the test.
    """

    present: set[str] = field(
        default_factory=lambda: {"just", "claude", "gh", "az", "git", "uv", "node"}
    )
    logged_in: bool = True
    environ: dict[str, str] = field(default_factory=lambda: dict(GIT_IDENTITY))
    calls: list[tuple[str, ...]] = field(default_factory=list)
    home_dir: Path = field(default_factory=lambda: Path("/nonexistent/fake-home"))
    platform_name: str = "linux"
    outputs: dict[tuple[str, ...], Probe | None] = field(default_factory=dict)
    modes: dict[Path, int] = field(default_factory=dict)

    def home(self) -> Path:
        return self.home_dir

    def which(self, program: str) -> str | None:
        return f"/fake/bin/{program}" if program in self.present else None

    def run(
        self, argv: Sequence[str], timeout: float = 15, cwd: Path | None = None
    ) -> Probe | None:
        self.calls.append(tuple(argv))
        if tuple(argv) in self.outputs:
            return self.outputs[tuple(argv)]
        if argv[0] not in self.present:
            return None
        return Probe(0 if self.logged_in else 1, "", "")

    def platform(self) -> str:
        return self.platform_name

    def environment(self) -> Mapping[str, str]:
        return {"HAIFA_HOME": os.environ["HAIFA_HOME"], **self.environ}

    def file_mode(self, path: Path) -> int | None:
        if path in self.modes:
            return self.modes[path]
        if not path.is_file():
            return None
        return path.stat().st_mode & 0o777

    def env(self, name: str) -> str | None:
        return self.environ.get(name)

    def harness(self, name: str, agents: Iterable[str]) -> HarnessStatus:
        binary = CLI_BINARIES[name][1]
        status = HarnessStatus(name=name, binary=binary, agents=list(agents))
        if binary in self.present:
            status.path = f"/fake/bin/{binary}"
            status.version = "1.0"
        else:
            status.error = "not on PATH"
        return status
