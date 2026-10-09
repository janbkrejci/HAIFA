"""Suggest the repo's ``test_command`` from the files in its root.

Used by ``factory init`` and meant for onboarding too: :func:`suggest_test_commands` reads
only the root of the repo (no subdirectories, nothing is run) and returns every matching
candidate in a fixed order, ``justfile`` first. The first candidate is the suggestion.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TEST_COMMAND = "just test"

JUSTFILES = ("justfile", "Justfile", ".justfile", "JUSTFILE")
MAKEFILES = ("GNUmakefile", "makefile", "Makefile")
PYTHON_FILES = ("pyproject.toml", "pytest.ini")
# lockfile -> package manager, in the order they are tried
NODE_LOCKFILES = (
    ("bun.lock", "bun"),
    ("bun.lockb", "bun"),
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
)

# One line per rule, in candidate order; rendered into the skill.
RULES: tuple[tuple[str, str], ...] = (
    ("`justfile` with a `test` recipe", "`just test`"),
    ("`pyproject.toml` or `pytest.ini`", "`uv run pytest` (`pytest` when `uv` is not on PATH)"),
    (
        "`package.json` with a `test` script",
        "by lockfile: `bun.lock`/`bun.lockb` `bun test`, `pnpm-lock.yaml` `pnpm test`, "
        "`yarn.lock` `yarn test`, else `npm test`",
    ),
    ("`*.sln` or `*.csproj`", "`dotnet test`"),
    ("`Cargo.toml`", "`cargo test`"),
    ("`go.mod`", "`go test ./...`"),
    ("`Makefile` with a `test` target", "`make test`"),
)

# `test:` or `test ARGS: deps` or `@test:`, but not the assignment `test := ...`
_JUST_RECIPE = re.compile(r"^@?test(?:\s[^:\n]*)?:(?!=)", re.MULTILINE)
# a rule line whose targets include `test` (`test:`, `lint test:`), not `test := ...`
_MAKE_TARGET = re.compile(r"^(?:[^\s:#=]+[ \t]+)*test(?:[ \t]+[^\s:#=]+)*[ \t]*::?(?!=)", re.M)


@dataclass(frozen=True)
class TestCommandCandidate:
    """One suggested ``test_command``: the technology, the command and the file it came from."""

    __test__ = False  # not a pytest class

    tech: str
    command: str
    reason: str

    def to_json(self) -> dict[str, str]:
        return {"tech": self.tech, "command": self.command, "reason": self.reason}


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _first_file(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = root / name
        if path.is_file():
            return path
    return None


def _just(root: Path) -> TestCommandCandidate | None:
    path = _first_file(root, JUSTFILES)
    text = _read(path) if path else None
    if path is None or text is None or not _JUST_RECIPE.search(text):
        return None
    return TestCommandCandidate("just", "just test", f"{path.name} has a test recipe")


def _python(root: Path, has_uv: bool) -> TestCommandCandidate | None:
    path = _first_file(root, PYTHON_FILES)
    if path is None:
        return None
    command = "uv run pytest" if has_uv else "pytest"
    return TestCommandCandidate("python", command, path.name)


def _node(root: Path) -> TestCommandCandidate | None:
    path = root / "package.json"
    text = _read(path) if path.is_file() else None
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict) or not isinstance(scripts.get("test"), str):
        return None
    for lockfile, manager in NODE_LOCKFILES:
        if (root / lockfile).is_file():
            return TestCommandCandidate(
                "node", f"{manager} test", f"package.json has a test script, {lockfile}"
            )
    return TestCommandCandidate("node", "npm test", "package.json has a test script")


def _dotnet(root: Path) -> TestCommandCandidate | None:
    for pattern in ("*.sln", "*.csproj"):
        found = sorted(p.name for p in root.glob(pattern) if p.is_file())
        if found:
            return TestCommandCandidate("dotnet", "dotnet test", found[0])
    return None


def _marker(root: Path, name: str, tech: str, command: str) -> TestCommandCandidate | None:
    return TestCommandCandidate(tech, command, name) if (root / name).is_file() else None


def _make(root: Path) -> TestCommandCandidate | None:
    path = _first_file(root, MAKEFILES)
    text = _read(path) if path else None
    if path is None or text is None or not _MAKE_TARGET.search(text):
        return None
    return TestCommandCandidate("make", "make test", f"{path.name} has a test target")


def suggest_test_commands(
    root: Path, *, which: Callable[[str], str | None] = shutil.which
) -> list[TestCommandCandidate]:
    """Every ``test_command`` candidate for the repo at ``root``, best first.

    Only files directly in ``root`` count. ``which`` looks up ``uv`` on PATH (injectable for
    tests). An empty list means no technology was recognised.
    """
    found = [
        _just(root),
        _python(root, which("uv") is not None),
        _node(root),
        _dotnet(root),
        _marker(root, "Cargo.toml", "rust", "cargo test"),
        _marker(root, "go.mod", "go", "go test ./..."),
        _make(root),
    ]
    out: list[TestCommandCandidate] = []
    for candidate in found:
        if candidate is not None and all(c.command != candidate.command for c in out):
            out.append(candidate)
    return out
