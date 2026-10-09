"""``justfile_recipes``: the recipe names ``factory check`` looks for in base."""

from __future__ import annotations

from pathlib import Path

import pytest

from aifactory.check import justfile_recipes

JUSTFILE = """\
# comment: not a recipe
set positional-arguments
set shell := ["bash", "-c"]
export FOO := "bar"
config := env_var_or_default("X", "a:b")

[private]
default:
    @just --list

test *ARGS: web-test
    pytest "$@"

@demo:
    echo demo

web-test:
    npm test

build target="x":
    echo {{target}}

alias t := test
"""


def test_recipes() -> None:
    assert justfile_recipes(JUSTFILE) == {"default", "test", "demo", "web-test", "build", "t"}


def test_no_recipes() -> None:
    assert justfile_recipes("x := 1\n# test:\n    test:\n") == set()


def test_full_check_preparation_failure_preserves_stamp(tmp_path: Path) -> None:
    import os
    import subprocess
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    root = Path(__file__).resolve().parents[3]
    recipe = (root / "justfile").read_text().split('full-check step="HAIFA-S03":\n', 1)[1]
    script = "\n".join(
        line[4:] if line.startswith("    ") else line for line in recipe.splitlines()
    )
    state = tmp_path / "state"
    (state / "haifa").mkdir(parents=True)
    stamp = state / "haifa/full-check-green"
    stamp.write_text("old-green\n")
    binary = tmp_path / "bin"
    binary.mkdir()
    fake = binary / "git"
    fake.write_text(f"""#!/bin/bash
if [ "$1" = rev-parse ] && [ "$2" = --path-format=absolute ]; then
    echo '{state}'
elif [ "$1" = rev-parse ]; then
    echo deadbeef
else
    exit 3
fi
""")
    fake.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}"},
    )
    assert result.returncode == 1
    assert stamp.read_text() == "old-green\n"
    assert b"cannot prepare checkout" in result.stderr


@pytest.mark.parametrize("failed_check", ["", "tests", "typecheck", "lint"])
def test_full_check_stamps_only_after_all_checks_succeed(tmp_path: Path, failed_check: str) -> None:
    import os
    import subprocess

    root = Path(__file__).resolve().parents[3]
    recipe = (root / "justfile").read_text().split('full-check step="HAIFA-S03":\n', 1)[1]
    script = "\n".join(
        line[4:] if line.startswith("    ") else line for line in recipe.splitlines()
    )
    state = tmp_path / "state"
    (state / "haifa").mkdir(parents=True)
    stamp = state / "haifa/full-check-green"
    stamp.write_text("old-green\n")
    binary = tmp_path / "bin"
    binary.mkdir()
    fake_git = binary / "git"
    fake_git.write_text("""#!/bin/bash
if [ "$1" = rev-parse ] && [ "$2" = --path-format=absolute ]; then
    echo "$TEST_STATE"
elif [ "$1" = rev-parse ]; then
    echo deadbeef
elif [ "$1" = worktree ] && [ "$2" = add ]; then
    mkdir -p "$5"
elif [ "$1" = log ]; then
    echo 'deadbeef test commit'
fi
""")
    fake_just = binary / "just"
    fake_just.write_text("""#!/bin/bash
if [ "$1" = check ]; then
    for check in tests typecheck lint; do
        echo "$check" >> "$TEST_CHECK_LOG"
        if [ "$check" = "$TEST_FAIL_CHECK" ]; then exit 7; fi
    done
else
    echo "$*" >> "$TEST_FIX_LOG"
fi
""")
    fake_git.chmod(0o755)
    fake_just.chmod(0o755)
    log = tmp_path / "checks.log"
    fixes = tmp_path / "fixes.log"
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{binary}:{os.environ['PATH']}",
            "TMPDIR": str(tmp_path),
            "TEST_STATE": str(state),
            "TEST_CHECK_LOG": str(log),
            "TEST_FIX_LOG": str(fixes),
            "TEST_FAIL_CHECK": failed_check,
        },
    )
    if failed_check:
        assert result.returncode == 1
        assert stamp.read_text() == "old-green\n"
        assert "factory task add" in fixes.read_text()
    else:
        assert result.returncode == 0
        assert stamp.read_text() == "deadbeef\n"
        assert log.read_text().splitlines() == ["tests", "typecheck", "lint"]
        assert not fixes.exists()
