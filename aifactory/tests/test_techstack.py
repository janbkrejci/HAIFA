"""Suggest ``test_command`` from the files in the repo root (HAIFA-S04-T03)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aifactory.techstack import suggest_test_commands


def _uv(name: str) -> str | None:
    return "/bin/uv" if name == "uv" else None


def _no_uv(name: str) -> str | None:
    return None


def write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return root


def commands(root: Path, *, has_uv: bool = True) -> list[str]:
    return [c.command for c in suggest_test_commands(root, which=_uv if has_uv else _no_uv)]


def package(test: str | None = "vitest") -> str:
    scripts = {"build": "tsc"} | ({"test": test} if test else {})
    return json.dumps({"name": "x", "scripts": scripts})


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"justfile": "lint:\n\truff\n\ntest *ARGS:\n\tpytest\n"}, "just test"),
        ({"Justfile": "@test:\n\tcargo test\n"}, "just test"),
        ({"pyproject.toml": "[project]\nname='x'\n"}, "uv run pytest"),
        ({"pytest.ini": "[pytest]\n"}, "uv run pytest"),
        ({"package.json": package()}, "npm test"),
        ({"package.json": package(), "package-lock.json": "{}"}, "npm test"),
        ({"package.json": package(), "pnpm-lock.yaml": ""}, "pnpm test"),
        ({"package.json": package(), "yarn.lock": ""}, "yarn test"),
        ({"package.json": package(), "bun.lockb": ""}, "bun test"),
        ({"package.json": package(), "bun.lock": ""}, "bun test"),
        ({"App.sln": ""}, "dotnet test"),
        ({"App.csproj": "<Project/>"}, "dotnet test"),
        ({"Cargo.toml": "[package]\n"}, "cargo test"),
        ({"go.mod": "module x\n"}, "go test ./..."),
        ({"Makefile": ".PHONY: test\nbuild:\n\tcc\ntest: build\n\t./run\n"}, "make test"),
        ({"makefile": "lint test:\n\t./run\n"}, "make test"),
    ],
)
def test_each_technology(tmp_path: Path, files: dict[str, str], expected: str) -> None:
    assert commands(write(tmp_path, files)) == [expected]


def test_python_without_uv(tmp_path: Path) -> None:
    assert commands(write(tmp_path, {"pyproject.toml": ""}), has_uv=False) == ["pytest"]


@pytest.mark.parametrize(
    "files",
    [
        {"justfile": "build:\n\tcc\ntest := 'x'\ntest-unit:\n\tpytest\n"},
        {"package.json": package(None)},
        {"package.json": "not json"},
        {"Makefile": "test-unit:\n\t./run\nTEST := 1\nfoo:\n\ttest -f x\n"},
        {"sub/Cargo.toml": "", "sub/go.mod": "", "README.md": "test:\n"},
    ],
)
def test_no_match(tmp_path: Path, files: dict[str, str]) -> None:
    assert commands(write(tmp_path, files)) == []


def test_empty_repo(tmp_path: Path) -> None:
    assert suggest_test_commands(tmp_path) == []


def test_several_matches_justfile_first(tmp_path: Path) -> None:
    write(
        tmp_path,
        {
            "Makefile": "test:\n\t./run\n",
            "go.mod": "",
            "Cargo.toml": "",
            "App.sln": "",
            "package.json": package(),
            "yarn.lock": "",
            "pyproject.toml": "",
            "pytest.ini": "",
            "justfile": "test:\n\tpytest\n",
        },
    )
    found = suggest_test_commands(tmp_path, which=_uv)
    assert [c.command for c in found] == [
        "just test",
        "uv run pytest",
        "yarn test",
        "dotnet test",
        "cargo test",
        "go test ./...",
        "make test",
    ]
    assert [c.tech for c in found] == ["just", "python", "node", "dotnet", "rust", "go", "make"]
    assert found[0].to_json() == {
        "tech": "just",
        "command": "just test",
        "reason": "justfile has a test recipe",
    }
