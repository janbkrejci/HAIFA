"""HAIFA's adaptive subsystem map and compatibility tier API.

Slow/browser file lists remain shared with conftest; scoped checks include relevant
slow tests explicitly and cap pytest at two workers (browser checks run serially).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

from aifactory.testing.context import docs_only
from aifactory.testing.model import Check, Context, Plan

SLOW_FILES = frozenset(
    {
        "tests/e2e/test_f3_browser.py",
        "tests/e2e/test_multi_repo_browser.py",
        "tests/validation/test_validation_local.py",
        "tests/validation/test_validation_roster.py",
        "tests/validation/test_validation_prompt_paths.py",
        "tests/run/test_auto_continue.py",
        "tests/run/test_auto_merge.py",
        "tests/run/test_task_resolve.py",
        "tests/run/test_task_resolve_generated.py",
        "tests/web/test_web_task_run.py",
        "tests/providers/test_providers_azure.py",
        "tests/review/test_approve_merge_retry.py",
    }
)
BROWSER_FILES = frozenset({"tests/e2e/test_f3_browser.py", "tests/e2e/test_multi_repo_browser.py"})

NEIGHBOURS = {
    "workflow": ("workflow", "run"),
    "run": ("run", "review"),
    "review": ("review", "run"),
    "config": ("config", "check", "onboard"),
    "backlog": ("backlog", "run"),
    "providers": ("providers", "run"),
    "harness": ("harness", "workflow"),
    "library": ("library", "onboard"),
    "web": ("web", "e2e"),
}


def select(ctx: Context) -> Plan:
    """Fail closed for infrastructure, unknown paths and missing test mappings."""
    root = Path(ctx.repo_root)

    def full(reason: str) -> Plan:
        return Plan(
            coverage="full", reason=reason, checks=[Check(name="full", argv=["just", "check"])]
        )

    if ctx.force_full:
        return full("forced full verification")
    if docs_only(ctx.changed_paths):
        return Plan(coverage="none", reason="only documentation or no changes", checks=[])
    tests: set[str] = set()
    web = False
    backend = False
    for path in ctx.changed_paths:
        if docs_only([path]):
            continue
        if path.startswith("aifactory/web/"):
            if path.removeprefix("aifactory/web/") in {
                "package.json",
                "bun.lock",
                "bun.lockb",
                "vite.config.ts",
                "vitest.config.ts",
                "tsconfig.json",
                "tsconfig.app.json",
                "tsconfig.node.json",
            } or path.startswith(("aifactory/web/src/test/", "aifactory/web/tests/")):
                return full(f"frontend infrastructure: {path}")
            web = True
            tests.add("aifactory/tests/e2e")
        elif path.startswith("aifactory/tests/"):
            name = path.rsplit("/", 1)[-1]
            if not name.startswith("test_") or not name.endswith(".py"):
                return full(f"test infrastructure: {path}")
            tests.add(path if (root / path).is_file() else str(Path(path).parent))
            backend = True
        elif path.startswith("aifactory/src/aifactory/"):
            module = path.removeprefix("aifactory/src/aifactory/").split("/")[0]
            if module not in NEIGHBOURS:
                return full(f"unmapped source or engine: {path}")
            tests.update(f"aifactory/tests/{m}" for m in NEIGHBOURS[module])
            backend = True
        else:
            return full(f"unknown path or infrastructure: {path}")
    if backend:
        tests.add("aifactory/tests/engine/test_import.py")
    if any(not (root / p).exists() for p in tests):
        return full("missing mapped test path")
    selected = sorted(p for p in tests if not any(p.startswith(q + "/") for q in tests))
    browser = [p for p in selected if p.startswith("aifactory/tests/e2e")]
    ordinary = [p for p in selected if p not in browser]
    checks: list[Check] = []
    prefix = ["uv", "run", "--project", "aifactory", "pytest"]
    if web:
        checks.append(Check(name="frontend", argv=["just", "web-test"]))
    if ordinary:
        checks.append(Check(name="backend", argv=prefix + ordinary + ["-n", "2", "--maxfail=1"]))
    if browser:
        checks.append(Check(name="browser", argv=prefix + browser + ["-n0", "--maxfail=1"]))
    if backend:
        checks.extend(
            [
                Check(name="typecheck", argv=["just", "typecheck"]),
                Check(name="lint", argv=["just", "lint"]),
            ]
        )
    return Plan(
        coverage="scoped", reason="mapped subsystems and integration neighbours", checks=checks
    )


def tier(paths: Iterable[str]) -> tuple[str, bool, bool, str]:
    """Compatibility view of the same selection policy."""
    values = list(paths)
    root = Path(__file__).resolve().parents[2]
    plan = select(
        Context(
            repo_root=str(root),
            baseline="compat",
            head="compat",
            changed_paths=values,
            force_full=False,
            fallback_argv=["just", "check"],
            test_timeout=600,
        )
    )
    web = any(p.startswith("aifactory/web/") for p in values)
    browser = web or any(
        p.startswith("aifactory/src/aifactory/web/")
        or p.removeprefix("aifactory/") in BROWSER_FILES
        for p in values
    )
    return ("fast" if plan.coverage == "scoped" else plan.coverage, web, browser, plan.reason)


def main() -> None:
    name, web, browser, reason = tier(line.strip() for line in sys.stdin)
    print(name, int(web), int(browser), reason)


if __name__ == "__main__":
    main()
