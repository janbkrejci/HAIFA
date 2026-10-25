---
id: HAIFA-LEARN-T04
title: "Lekce: Select only tests that exercise the changed behavior: drop whole files or director…"
status: todo
workflow: build-review
depends_on: []
related: [HAIFA-REFINEMENT-T69, HAIFA-S01-T46, HAIFA-REFINEMENT-T71, HAIFA-REFINEMENT-T72, HAIFA-S01-T47, HAIFA-REFINEMENT-T75, HAIFA-REFINEMENT-T74]
writes: [AGENTS.md]
---

## Zadání
Zapiš do `AGENTS.md` pravidlo z lekce `L0981b3f2`, kterou factory našla ve výtkách opakovaných v bězích:

> Select only tests that exercise the changed behavior: drop whole files or directories that merely import a changed module, and add browser or unrelated layout tests only for a changed screen.

Pravidlo formuluj stručně, zařaď ho tam, kam v souboru patří, a nenech ho odporovat tomu, co tam už je. Jiné soubory neměň.

Hotovo znamená:
- Pravidlo je v `AGENTS.md`.

### Důkazy

Výtky z 8 běhů, ze kterých lekce vznikla:

- běh `535e4acc`, task `HAIFA-REFINEMENT-T69` (test_review): Remove tests/harness/test_harness_probe.py, tests/web/test_web_assistant.py, tests/web/test_web_phase_prompts.py and tests/test_failure.py from inheritance-and-advisor-regressions.
- běh `535e4acc`, task `HAIFA-REFINEMENT-T69` (test_review): nothing needless runs: test_harness_probe.py, test_web_assistant.py, test_web_phase_prompts.py and test_failure.py exercise unchanged behavior without reaching the changed helpers or advice selection. Import relationships alone do not justify them.
- běh `56c040a1`, task `HAIFA-S01-T46` (test_review): Remove tests/learn/test_learn_store.py from adjacent-callers; it tests an independent store and schema.
- běh `56c040a1`, task `HAIFA-S01-T46` (test_review): Remove tests/review/test_merged_at.py from adjacent-callers; its mocked store bypasses the changed implementation.
- běh `56c040a1`, task `HAIFA-S01-T46` (test_review): Remove tests/workflow/test_workflow_advice.py from adjacent-callers; its backlog imports and tested behavior are unchanged.
- běh `56c040a1`, task `HAIFA-S01-T46` (test_review): nothing needless runs: The adjacent-callers check includes independent LessonStore migration, mocked merge timestamp handling, and workflow advice tests that do not exercise the changed behavior.
- běh `9e8e190e`, task `HAIFA-REFINEMENT-T71` (test_review): Remove needless direct-callers selections: tests/test_failure.py, tests/backlog/test_backlog_harness_values.py, tests/backlog/test_task_follow_up.py, tests/workflow/test_workflow_advice.py, tests/web/test_web_phase_prompts.py and tests/web/test_web_workflow_advice.py.
- běh `9e8e190e`, task `HAIFA-REFINEMENT-T71` (test_review): Remove the full tests/run/test_parallel_chain.py selection or narrow it to a specifically justified integration test exercising the affected behavior.
- běh `9e8e190e`, task `HAIFA-REFINEMENT-T71` (test_review): nothing needless runs: Several direct-callers selections exercise only unchanged helpers; the full parallel-chain file includes fake-runner scheduling tests that bypass changed behavior.
- běh `40bdba00`, task `HAIFA-REFINEMENT-T72` (test_review): Replace web-tests argv with ["just", "pytest", "tests/web/test_web_assistant.py"].
- běh `40bdba00`, task `HAIFA-REFINEMENT-T72` (test_review): Remove assistant-browser: ["just", "pytest", "tests/e2e/test_assistant_browser.py", "-n0"].
- běh `40bdba00`, task `HAIFA-REFINEMENT-T72` (test_review): nothing needless runs: tests/web includes unrelated APIs, and assistant-browser adds unnecessary browser coverage; the task spec explicitly requests focused assistant tests without browser checks.
- běh `80c3e61b`, task `HAIFA-S01-T47` (test_review): Remove backlog-intent-browser: just pytest tests/e2e/test_intent_browser.py -n0.
- běh `80c3e61b`, task `HAIFA-S01-T47` (test_review): nothing needless runs: backlog-intent-browser exercises intent proposal, refinement, application and graph navigation without opening Kanban or exercising archive behavior. No changed intent path justifies this additional workflow.
- běh `d9d82e0b`, task `HAIFA-REFINEMENT-T75` (test_review): Needless check: remove dashboard-layout (just pytest tests/e2e/test_limits_layout.py -n0).
- běh `d9d82e0b`, task `HAIFA-REFINEMENT-T75` (test_review): Needless breadth: remove static-serving or narrow it to just pytest tests/web/test_web_app.py::test_packaged_build_is_served -n0.
- běh `d9d82e0b`, task `HAIFA-REFINEMENT-T75` (test_review): nothing needless runs: dashboard-layout tests unchanged limits geometry and tabbar scrolling. Most static-serving tests cover unchanged API envelopes, host validation, and synthetic static directories.
- běh `1606bc57`, task `HAIFA-REFINEMENT-T75` (test_review): Replace library-tests argv ["just", "pytest", "tests/library"] with ["just", "pytest", "tests/library/test_library_seed.py"] to remove unrelated library coverage.
- běh `1606bc57`, task `HAIFA-REFINEMENT-T75` (test_review): nothing needless runs: The entire tests/library directory includes remote URL detection, synthetic version hashes, and substituted-seed tests that cannot be affected by this prompt wording change.
- běh `8ef80af0`, task `HAIFA-REFINEMENT-T74` (test_review): Replace tests/test_skill.py with tests/test_skill.py::test_guide_leaves_check_fixes_to_factory_check, tests/test_skill.py::test_guide_covers_setup_library_repos_and_upgrades and tests/test_skill.py::test_factory_commands_exist_in_parser.
- běh `8ef80af0`, task `HAIFA-REFINEMENT-T74` (test_review): Replace tests/web/test_web_assistant.py with tests/web/test_web_assistant.py::test_second_message_continues_the_session, which exercises guide chapter loading into the prompt.
- běh `8ef80af0`, task `HAIFA-REFINEMENT-T74` (test_review): nothing needless runs: Whole-file selections of test_skill.py and test_web_assistant.py include unrelated skill generation, command gates, SQL access, action execution and thread deletion tests.

<!-- factory: lesson=L0981b3f2 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
