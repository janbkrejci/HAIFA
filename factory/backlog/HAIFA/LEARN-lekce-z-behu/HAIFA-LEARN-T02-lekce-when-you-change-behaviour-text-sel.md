---
id: HAIFA-LEARN-T02
title: "Lekce: When you change behaviour, text, selectors or preconditions, grep the tests for th…"
status: done
archived: true
workflow: build-test-review
depends_on: []
related: [HAIFA-REFINEMENT-T16, HAIFA-REFINEMENT-T22, HAIFA-REFINEMENT-T40, LEARN-S01-T01, HAIFA-REFINEMENT-T61]
writes: [aifactory/src/aifactory/seed/agents/builder/]
---

## Zadání
Zapiš do promptu role builder (`aifactory/src/aifactory/seed/agents/builder/`) pravidlo z lekce `Ldcb5b512`, kterou factory našla ve výtkách opakovaných v bězích:

> When you change behaviour, text, selectors or preconditions, grep the tests for the old behaviour and update every test or fixture that still expects it in the same change.

Pravidlo formuluj stručně, zařaď ho tam, kam v souboru patří, a nenech ho odporovat tomu, co tam už je. Pravidlo patří do `system.md` seedu role builder, odkud ho dostanou knihovny po upgradu. `.factory/prompts/` je chráněný (`protected_files`) a přepis promptu v repu by odřízl HAIFA od dalších změn knihovny. Jiné soubory neměň.

Hotovo znamená:
- Pravidlo je v promptu role builder (`aifactory/src/aifactory/seed/agents/builder/`).

### Důkazy

Výtky z 5 běhů, ze kterých lekce vznikla:

- běh `fc7284c2`, task `HAIFA-REFINEMENT-T16` (test_triage): [code] The failure comes from code, not the plan. test_f3_browser.py::test_add_and_remove_repo_in_browser ran as intended. make_f3_repo builds a repo whose base already has factory, so the changed InspectCard correctly shows the new note 'Factory už je v main. Přidání repo jen připojí k dashboardu, nic necommitne ani nepushne.' The test, which the builder edited, still expects 'commitne to do main' at line 617, and its docstring still says factory is committed on add. The other checks passed. The plan's scope (changed web package, Vue, and the browser tests of the changed screens within 870 s) is still right.
- běh `501e886b`, task `HAIFA-REFINEMENT-T22` (test_triage): [code] The e2e check ran as intended. test_f3_task_lifecycle_in_browser failed because `[data-test="depends"]` matches two elements: the new IdPicker's button in the task form and the `div.link-group` of the task detail. Both elements, and the test selector the builder edited, belong to this change, so the fault is in the code, not in the plan. The other five checks passed, and so did test_workflow_advice_browser. The plan's scope still fits the change, because only the frontend changed and no backend code did.
- běh `b8b270be`, task `HAIFA-REFINEMENT-T40` (test_triage): [code] Both failures come from the code, not the plan. The web-test failure is the project's own rule against native tooltips, `src/lib/noNativeUi.test.ts`, and it fails in two places. In IdPicker.vue, `<CodePickerDialog :title=...>` passes a prop named `title`, which the rule does not allow. In TaskDetail.vue, `<span class="chip mono" :title=...>` puts a native tooltip on the Writes chips. The browser test showed that the edit-mode 'Závisí na' control is now the button 'Závisí na: přidat'. Clicking it no longer gives the `[data-test=select-list] [role=option][data-value=CODE]` option the test waits for, so no chip appeared. Only Vue code changed, so these checks still cover the change. The full suite is left to CI.
- běh `5bce1c7c`, task `LEARN-S01-T01` (test_triage): [code] The check ran as intended and 358 tests passed. test_subcommands_not_implemented runs main([name]) for every subcommand that is not in its implemented/setup tuples and expects exit code 2 with 'not implemented yet'. The new subcommand `learn` is implemented but missing from the `implemented` tuple, so main(['learn']) raises SystemExit(2) from argparse because its required <command> is missing. The change has to update that test, so this is a code fault. The plan stays the same: lint, typecheck and the scoped pytest over learn, smoke, skill, error codes, library and the roster tests. The whole suite is left to CI.
- běh `fab200e4`, task `HAIFA-REFINEMENT-T61` (review): Upravit test_two_tasks_of_one_repo_run_concurrently tak, aby oba tasky byly nezávislé v commitnuté base, a zachovat ověření souběhu i already_running.
- běh `fab200e4`, task `HAIFA-REFINEMENT-T61` (review): Doplnit regresní testy a upravit testy počítající s force startem blokovaného tasku: Nové regrese existují, ale aifactory/tests/web/test_web_launcher.py:417 stále očekává 202 pro T02 s force při běžícím T01. Fixture aifactory/tests/run/run_repo.py:93–97 definuje T01 jako todo a T02 závislý na T01; nová kontrola vrátí 409 unmet_dependencies.
- běh `fab200e4`, task `HAIFA-REFINEMENT-T61` (test_review): Correct aifactory/tests/web/test_web_launcher.py::test_two_tasks_of_one_repo_run_concurrently: remove T02's dependency on T01 and commit the fixture change to base before starting either task; preserve concurrent-process and 409 already_running assertions and retain the test selector.
- běh `fab200e4`, task `HAIFA-REFINEMENT-T61` (test_review): checks cover the changed code: test_two_tasks_of_one_repo_run_concurrently expects force to start T02 while its dependency T01 remains running; the new guard rejects that request before concurrency assertions execute.
- běh `fab200e4`, task `HAIFA-REFINEMENT-T61` (test_review): Correct aifactory/tests/web/test_web_launcher.py::test_two_tasks_of_one_repo_run_concurrently: make T02 independent of T01 and commit the fixture change to base before either start; preserve concurrency and 409 already_running assertions and retain its selector.
- běh `fab200e4`, task `HAIFA-REFINEMENT-T61` (test_review): checks cover the changed code: test_two_tasks_of_one_repo_run_concurrently still expects force to start dependent T02 while T01 runs, so dependency rejection prevents its concurrency assertions.
- běh `fab200e4`, task `HAIFA-REFINEMENT-T61` (review): V test_two_tasks_of_one_repo_run_concurrently před oběma starty odstraňte závislost T02 na T01 a commitněte změnu fixture do base. Zachovejte kontroly odlišných procesů, dvou běžících tasků, souběhu launcheru, launcher_busy false a 409 already_running.
- běh `fab200e4`, task `HAIFA-REFINEMENT-T61` (review): Doplnit regresní testy a upravit testy počítající s force startem blokovaného tasku: Nové regrese existují, ale aifactory/tests/web/test_web_launcher.py:414–426 zůstává beze změny: očekává 202 při force startu T02 během běhu T01. Fixture aifactory/tests/run/run_repo.py:93–97 definuje T01 todo a T02 depends_on T01; nová kontrola proto vrátí 409 unmet_dependencies.

<!-- factory: lesson=Ldcb5b512 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-20 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/129 · náklady $0.00
