"""The test tier of a change (just check-scoped)."""

from __future__ import annotations

import pytest

from tiers import BROWSER_FILES, SLOW_FILES, tier


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        ([], "none"),
        (["backlog/HAIFA/S01-dashboard-ux/HAIFA-S01-T40-x.md", "docs/decisions.md"], "none"),
        (["CLAUDE.md", "specs/HAIFA-S01-T40.md", "app_docs/HAIFA-S01-T40.md"], "none"),
        (["aifactory/src/aifactory/web/review.py"], "fast"),
        (["aifactory/src/aifactory/library/seed.py", "aifactory/tests/library/test_x.py"], "fast"),
        ([".factory/prompts/builder/system.md"], "full"),
        (["aifactory/src/aifactory/run/guard.py"], "fast"),
        (["aifactory/src/aifactory/cli.py"], "full"),
        (["aifactory/uv.lock"], "full"),
        (["justfile"], "full"),
        (["aifactory/tests/run/run_repo.py"], "full"),
        (["aifactory/tests/conftest.py"], "full"),
        (["aifactory/tests/run/test_auto_merge.py"], "fast"),
    ],
)
def test_tier_of_a_change(paths: list[str], expected: str) -> None:
    assert tier(paths)[0] == expected


def test_frontend_change_runs_web_tests_and_the_browser_test() -> None:
    name, web, browser, _ = tier(["aifactory/web/src/App.vue"])
    assert (name, web, browser) == ("fast", True, True)


def test_dashboard_server_change_runs_the_browser_test_only() -> None:
    name, web, browser, _ = tier(["aifactory/src/aifactory/web/app.py"])
    assert (name, web, browser) == ("fast", False, True)


def test_slow_files_exist() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert all((root / rel).is_file() for rel in SLOW_FILES)


def test_multi_repo_acceptance_is_slow_and_browser() -> None:
    path = "tests/e2e/test_multi_repo_browser.py"
    assert path in SLOW_FILES & BROWSER_FILES
    assert tier([f"aifactory/{path}"])[0] == "fast"


def test_selected_commands_show_savings() -> None:
    from pathlib import Path

    from aifactory.testing.model import Context, Plan
    from tiers import select

    root = Path(__file__).resolve().parents[2]

    def chosen(paths: list[str], force: bool = False) -> Plan:
        return select(
            Context(
                repo_root=str(root),
                baseline="base",
                head="head",
                changed_paths=paths,
                force_full=force,
                fallback_argv=["just", "check"],
                test_timeout=600,
            )
        )

    docs = chosen(["specs/task.md"])
    assert docs.coverage == "none"
    wf = chosen(["aifactory/src/aifactory/workflow/parse.py"])
    argv = wf.checks[0].argv
    assert "aifactory/tests/workflow" in argv and "aifactory/tests/run" in argv
    assert not any("providers" in a or "web" in a for a in argv)
    front = chosen(["aifactory/web/src/App.vue"])
    assert [c.name for c in front.checks] == ["frontend", "browser"]
    assert chosen(["unknown.py"]).coverage == "full"
    assert chosen(["README.md"], True).coverage == "full"
    slow = chosen(["aifactory/tests/run/test_auto_merge.py"])
    assert "aifactory/tests/run/test_auto_merge.py" in slow.checks[0].argv


@pytest.mark.parametrize(
    "path",
    [
        "vite.config.ts",
        "vitest.config.ts",
        "src/test/setup.ts",
        "src/test/helpers.ts",
        "tsconfig.json",
    ],
)
def test_frontend_test_infrastructure_is_full(path: str) -> None:
    assert tier([f"aifactory/web/{path}"])[0] == "full"


def test_missing_mapped_path_falls_back_to_full(tmp_path: object) -> None:
    from pathlib import Path

    from aifactory.testing.model import Context
    from tiers import select

    assert isinstance(tmp_path, Path)
    selected = select(
        Context(
            repo_root=str(tmp_path),
            baseline="base",
            head="head",
            changed_paths=["aifactory/src/aifactory/workflow/parse.py"],
            force_full=False,
            fallback_argv=["just", "check"],
            test_timeout=10,
        )
    )
    assert selected.coverage == "full"
    assert selected.checks[0].argv == ["just", "check"]
    assert "missing mapped" in selected.reason
