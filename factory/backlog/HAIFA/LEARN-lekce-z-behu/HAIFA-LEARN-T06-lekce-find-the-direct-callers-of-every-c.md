---
id: HAIFA-LEARN-T06
title: "Lekce: Find the direct callers of every changed function, module, seed file or test helpe…"
status: done
workflow: build-review
depends_on: []
related: [HAIFA-REFINEMENT-T09, HAIFA-S10-T03, HAIFA-S10-T04, HAIFA-REFINEMENT-T69]
writes: [AGENTS.md]
---

## Zadání
Zapiš do `AGENTS.md` pravidlo z lekce `L98bddeb1`, kterou factory našla ve výtkách opakovaných v bězích:

> Find the direct callers of every changed function, module, seed file or test helper by searching all of `aifactory/tests/`, not only the mirrored package directory, and include those test files in the plan.

Pravidlo formuluj stručně, zařaď ho tam, kam v souboru patří, a nenech ho odporovat tomu, co tam už je. Jiné soubory neměň.

Hotovo znamená:
- Pravidlo je v `AGENTS.md`.

### Důkazy

Výtky z 4 běhů, ze kterých lekce vznikla:

- běh `41006510`, task `HAIFA-REFINEMENT-T09` (test_review): Add aifactory/tests/onboard/test_sssf_parts.py, aifactory/tests/onboard/test_sssf.py and aifactory/tests/web/test_web_library.py to the library-config-tests pytest check.
- běh `41006510`, task `HAIFA-REFINEMENT-T09` (test_review): checks cover the changed code: `tests/onboard/test_sssf_parts.py` runs `merge_prompt` on `SEED_DIR/agents/builder/system.md` and asserts the merge kind (stock, union or clean). `tests/onboard/test_sssf.py` merges the seed builder prompt into the jsst builder and compares the result to `golden/sssf_jsst.txt`. `tests/web/test_web_library.py::test_seed_and_local_blockers` computes seed versions from the packaged seed. None of these is in the plan, so the reason's claim that only tests/library and config read the builder text is wrong.
- běh `41006510`, task `HAIFA-REFINEMENT-T09` (test_review): Add aifactory/tests/onboard/test_onboard.py to the seed-consumer-tests pytest argv.
- běh `41006510`, task `HAIFA-REFINEMENT-T09` (test_review): checks cover the changed code: `tests/onboard/test_onboard.py` (the `haifa` fixture with `library_with_versions` from `onboard_repo.py`) copies HAIFA's `.factory/`, where the builder still has the old text, imports every repo copy whose version differs from the seed, and asserts in `test_haifa_copy_dry_run_and_commit` that `agent/builder` is `linked` to `builder`. The builder takes this path only because of this change. The onboard merge tests, the golden test and `test_web_library.py` are now included.
- běh `53703a25`, task `HAIFA-S10-T03` (test_review): Add tests/web/test_web_factory.py, which covers the changed INIT_OPTIONS and _init_kwargs (docs_root) in web/factory.py, to pytest-web-changed.
- běh `53703a25`, task `HAIFA-S10-T03` (test_review): Add tests/web/test_web_live.py, which covers the changed backlog_dirs fallback in web/live.py, to pytest-web-changed.
- běh `53703a25`, task `HAIFA-S10-T03` (test_review): checks cover the changed code: In web/factory.py, INIT_OPTIONS and _init_kwargs now take docs_root, and tests/web/test_web_factory.py is not run. In web/live.py, the fallback backlog dir changed from 'backlog' to ProjectSettings().backlog_dir, and tests/web/test_web_live.py is not run.
- běh `53b4adeb`, task `HAIFA-S10-T04` (test_review): Add tests/run/test_task_run.py, tests/run/test_task_run_cli.py and tests/run/test_trace_db_lock.py to pytest-changed.
- běh `53b4adeb`, task `HAIFA-S10-T04` (test_review): Add tests/test_json_envelope.py and tests/test_smoke.py to pytest-changed.
- běh `53b4adeb`, task `HAIFA-S10-T04` (test_review): Add tests/web/test_obs_cli.py, tests/web/test_web_overview.py, tests/web/test_web_phase_prompts.py, tests/web/test_web_fs.py and tests/web/test_web_registry.py to pytest-changed.
- běh `53b4adeb`, task `HAIFA-S10-T04` (test_review): checks cover changed run code and its callers: run/task.py changes: named_workflow drops the packaged fallback except the internal workflows, _load changed, and copy_library_items is new. run/store.py adds the library_commit column. Only tests/run/test_task_library.py is selected.
- běh `53b4adeb`, task `HAIFA-S10-T04` (test_review): checks cover the CLI rewrite: cli.py loses 574 lines and skill/codes.py changes, but tests/test_json_envelope.py and tests/test_smoke.py are not selected.
- běh `53b4adeb`, task `HAIFA-S10-T04` (test_review): checks cover users of the edited test helper: tests/web/multi_repo.py no longer writes a manifest in install(). Five test files that use it are not selected: test_obs_cli.py, test_web_overview.py, test_web_phase_prompts.py, test_web_fs.py and test_web_registry.py.
- běh `535e4acc`, task `HAIFA-REFINEMENT-T69` (test_review): Add tests/run/test_quota_chain.py::test_project_chain_reads_the_inherited_keys to task-run-and-retry-regressions, or include its entire test file. Update the scope rationale and dropped explanation to acknowledge this third caller.
- běh `535e4acc`, task `HAIFA-REFINEMENT-T69` (test_review): checks cover the changed code and direct callers: quota_chain.primary_harness also calls task_harness_values; the narrowed plan omits tests/run/test_quota_chain.py, including its existing primary-harness regression.
- běh `535e4acc`, task `HAIFA-REFINEMENT-T69` (test_review): dropped checks are justified: Logs confirm timeouts without reported code failures, and deferring unrelated tests to CI is acceptable. However, the run-regressions replacement incorrectly claims to cover all wrapper callers while omitting quota_chain.primary_harness.

<!-- factory: lesson=L98bddeb1 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-25 · workflow build-review · PR https://github.com/janbkrejci/HAIFA/pull/162 · náklady $0.00
