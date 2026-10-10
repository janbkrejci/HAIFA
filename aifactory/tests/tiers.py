"""Slow and browser test files; tests/conftest.py marks them ``slow`` and ``browser``."""

from __future__ import annotations

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
