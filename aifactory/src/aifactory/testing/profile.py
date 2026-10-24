"""Local, advisory testing knowledge shared by runs of the same backlog project."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

MAX_PROFILE_LENGTH = 12_000
CONFIG_NAMES = frozenset(
    {
        "AGENTS.md",
        "CLAUDE.md",
        "justfile",
        "Justfile",
        "Makefile",
        "makefile",
        "package.json",
        "pyproject.toml",
        "pytest.ini",
        "tox.ini",
        "setup.cfg",
        "conftest.py",
        "Cargo.toml",
        "go.mod",
        "go.work",
        "Gemfile",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "Directory.Build.props",
        "global.json",
        "uv.lock",
        "bun.lock",
        "bun.lockb",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "Cargo.lock",
        "go.sum",
        "requirements.txt",
    }
)


class _StoredProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str
    knowledge: str = Field(max_length=MAX_PROFILE_LENGTH)
    durations: dict[str, float] = Field(default_factory=dict)


def fingerprint(root: Path) -> str:
    """Notice runner/config changes and test layout changes, including untracked files."""
    files = (
        subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        .stdout.decode("utf-8", errors="surrogateescape")
        .split("\0")
    )
    digest = hashlib.sha256()
    for name in sorted(set(files) - {""}):
        path = Path(name)
        config = (
            path.name in CONFIG_NAMES
            or name.startswith(".github/workflows/")
            or path.suffix in {".csproj", ".sln", ".slnx"}
            or path.name.startswith(
                ("vitest.config.", "vite.config.", "tsconfig", "playwright.config.")
            )
        )
        test = (
            path.name.startswith("test_")
            or ".test." in path.name
            or ".spec." in path.name
            or path.name.endswith(("_test.go", "Tests.cs", "Test.java"))
            or any(part.casefold() in {"test", "tests", "__tests__"} for part in path.parts[:-1])
        )
        if not (config or test):
            continue
        digest.update(name.encode("utf-8", errors="surrogateescape") + b"\0")
        if not (root / path).exists():
            digest.update(b"deleted\0")
            continue
        if config:
            try:
                digest.update((root / path).read_bytes())
            except FileNotFoundError:
                digest.update(b"deleted")
        digest.update(b"\0")
    return digest.hexdigest()


@dataclass(frozen=True)
class ProfileCache:
    directory: Path
    project: str

    @property
    def path(self) -> Path:
        key = hashlib.sha256(self.project.encode()).hexdigest()
        return self.directory / f"{key}.json"

    def load(self) -> _StoredProfile | None:
        try:
            return _StoredProfile.model_validate_json(self.path.read_bytes())
        except (OSError, ValueError):
            return None

    def context(self, root: Path) -> str:
        """A stale profile is still useful, but must be checked against this checkout."""
        stored = self.load()
        return json.dumps(
            {
                "project": self.project,
                "state": "missing"
                if stored is None
                else ("current" if stored.fingerprint == fingerprint(root) else "stale"),
                "knowledge": stored.knowledge if stored else "",
                "observed_seconds": stored.durations if stored else {},
            },
            ensure_ascii=False,
        )

    def save(self, root: Path, knowledge: str, durations: dict[str, float] | None = None) -> None:
        """Atomic replacement: concurrent runs may share hints, never partial JSON."""
        previous = self.load()
        if not knowledge.strip():
            return
        observed = {**(previous.durations if previous else {}), **(durations or {})}
        stored = _StoredProfile(
            fingerprint=fingerprint(root),
            knowledge=knowledge,
            durations=dict(list(observed.items())[-32:]),
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=self.directory, delete=False) as output:
            temporary = Path(output.name)
            output.write(stored.model_dump_json(indent=2).encode())
        try:
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
