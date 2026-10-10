# HAIFA-S03-T10: Task bez workflow se nespustí

## Co se změnilo a proč
Task **bez workflow** je task, jehož efektivní `workflow` chybí nebo je `null`. Dřív ho auto-continue vybralo jako další připravený task (`select_next` workflow nekontroloval) a kontrola v `run_task` přišla až po kontrole závislostí a `writes`, takže `--force` ji obešel nebo se ozvala jiná chyba. Teď se takový task nespustí nikde: v CLI, v auto-continue, v API ani v dashboardu.

Platí pravidlo „rozhoduje nejbližší úroveň“ (task → step → projekt). `workflow: null` na stepu nebo tasku tedy znamená „bez workflow“, i když vyšší úroveň workflow má. Pravidlo už platilo v `effective()`, nově ho pokrývá test a pojmenovaný helper.

## Kde to je
- `aifactory/src/aifactory/backlog/derived.py`: nový `has_workflow(task)` (`effective_workflow(task) is not None`), re-export v `backlog/__init__.py`.
- `aifactory/src/aifactory/run/task.py`: `no_workflow_error(task)` vrací `TaskRunError("no_workflow", …)`. `run_task` ho vyhodí hned po kontrole `already_running`, tedy před kontrolou závislostí (kterou `--force` přeskakuje), před `no_writes` a před založením záznamu běhu, větve a worktree. Výjimka: kontrola se neprovádí při `resolve_onto` (řešení konfliktu existující větve). `resolve_workflow` si původní kontrolu ponechává.
- `aifactory/src/aifactory/run/queue.py`: `SKIP_REASONS` rozšířeno o `"no_workflow"`, konstanta `NO_WORKFLOW_DETAIL = "bez workflow"`. `select_next` takový task zapíše jako `Skip(id, "no_workflow", "bez workflow")` a pokračuje dalším kandidátem.
- `aifactory/web/src/components/backlog/TaskDetail.vue`: tlačítko Spustit je obalené komponentou `Tooltip` a při `!task.workflow` je zakázané. Tooltip ukáže „Task nemá workflow – nastav ho na tasku, stepu nebo projektu.“ Zakázané tlačítko dostane `pointer-events: none` (třída `no-workflow`), aby hover zachytil anchor tooltipu.

CLI ani API logiku měnit nebylo potřeba. Kód `no_workflow` už existoval s exitem 2 a v API se mapuje na HTTP 422. Chyba z `run_task` se k nim dostane stávající cestou.

## Chování navenek
- `factory task run <id>` (i s `--force` a `--auto`) skončí s exitem 2 a `error.code == "no_workflow"`. Nevznikne worktree, větev `factory/*` ani řádek v `task_runs`.
- Auto-continue task přeskočí a v textovém výstupu vypíše `waiting: <id> no_workflow: bez workflow`. Řetěz pokračuje dalším taskem.
- `POST /api/backlog/tasks/{id}/run` vrátí 422 s kódem `no_workflow`, a to i s `{"force": true}`.

## Jak ověřit
`just test`, `just typecheck`, `just lint`. Relevantní testy:
- `aifactory/tests/backlog/test_backlog_workflow_null.py`: parametrizovaná kombinace `workflow` na projektu, stepu a tasku (včetně `null`) pro `effective_workflow` a `has_workflow`.
- `aifactory/tests/run/test_task_run.py`: případy `task_workflow_null` a `step_workflow_null` v `test_checks_before_start`, `test_no_workflow_even_with_force` (task s nesplněnou závislostí a bez `writes`) a `test_cli_run_without_workflow_fails` (kombinace `--force` a `--auto`). Všechny ověřují, že nic nevzniklo.
- `aifactory/tests/run/test_auto_continue.py`: `test_task_without_workflow_is_skipped`, `test_step_without_workflow_is_skipped`, rozšířený `test_select_next_rules` a `test_cli_auto_text_reports_task_without_workflow`.
- `aifactory/tests/web/test_web_launcher.py` (`("no_workflow", 422)`) a `aifactory/tests/web/test_web_task_run.py::test_task_without_workflow_does_not_start`.
- `aifactory/web/src/components/backlog/TaskDetail.test.ts`: tlačítko s workflow je povolené a bez tooltipu. Bez workflow je zakázané, nemá nativní `title`, klik neemituje `open-run` a tooltip obsahuje „nemá workflow“.
