---
id: HAIFA-REFINEMENT-T61
title: "API: běžící task nejde upravit ani měnit jeho vazby, blokovaný task nejde spustit"
status: todo
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/web/backlog.py, aifactory/src/aifactory/web/app.py, aifactory/src/aifactory/web/workflow_advice.py, aifactory/tests/web/test_web_task_running_guard.py, aifactory/tests/web/test_web_task_run.py, aifactory/tests/web/test_web_launcher.py, aifactory/src/aifactory/skill/codes.py]
---

## Zadání
Dnes API dashboardu dovolí upravit task, který právě běží (`board_state == 'running'`, tj. v trace DB je běh ve stavu `running`). Jde o endpointy `backlog_edit` a `backlog_link` v `aifactory/src/aifactory/web/app.py`, které volají `edit` a `link` v `aifactory/src/aifactory/web/backlog.py`. Patří sem i uložení návrhu agenta přes `workflow_advice_id` a spuštění návrhu (`task_advice_start`, `aifactory/src/aifactory/web/workflow_advice.py`). Spuštění ani retry běžícího tasku řešit nemusíš, ty už vracejí `already_running` (409).

Druhá díra: blokovaný task (nesplněné závislosti v base, `unmet_dependencies`) jde z dashboardu spustit přes `force: true` v `POST /api/backlog/tasks/{task_id}/run`. Dialog spuštění k tomu má tlačítko „Spustit i tak“.

Co udělat:
- Ve webové vrstvě (`web/backlog.py`, případně `web/workflow_advice.py`) před zápisem zjisti, jestli task právě běží. Použij stejný zdroj jako `board_state`/`_Runtime` (běh ve stavu `running` v trace DB) nebo `TaskRunStore.running(task_id)`, jako to dělá `run_check`. Pokud běží, vyhoď `TaskRunError` s kódem `task_running` a českou zprávou s id běhu, třeba „Task X právě běží (běh R), upravit ho jde až po doběhnutí.“
- Kód `task_running` zařaď do mapy chybových kódů v `web/app.py` na HTTP 409. Mapa je u `already_running`, a pokud je na řádku ~1444 druhá, tak do obou.
- Kontrola platí pro `edit` (všechna pole včetně `status`, `workflow`, `writes`, `body`), pro `link` a pro start i uložení návrhu agenta (`task advice`).
- Výjimka: zrušení přes `status: cancelled` u běžícího tasku také odmítni. Zastavit běh jde na stránce běhu.
- Spuštění tasku z dashboardu: `force` už nesmí obejít nesplněné závislosti. Když má task v base nesplněné závislosti a běh se nemá skládat na jejich otevřené PR (`stack` z `run_check` je prázdný), endpoint vrátí 409 `unmet_dependencies` i s `force: true`. Ostatní, co `force` dnes obchází, zůstává beze změny. Skládaný start (stacked PRs) dál funguje bez `force`. Stejně se chová start z follow-upu s `run`, pokud tam závislosti hrají roli.

Tvrdá omezení:
- Neměň `aifactory.backlog` core (`core.edit_task`, `core.link_task`), `factory task run --force` v CLI ani launcher. Factory sama upravuje backlog během běhu (HAIFA-S03-T09, allow_writes, follow_ups) a to musí dál fungovat. Kontroly patří jen do API dashboardu.
- Neměň frontend, ten řeší HAIFA-REFINEMENT-T62.

Mimo rozsah: úpravy tasků ve stavu `in review` a `awaiting merge` na backendu neblokuj, protože tam se writes rozšiřují záměrně.

Hotovo znamená:
- Nový test `aifactory/tests/web/test_web_task_running_guard.py` (s fixturami z `tests/web/`, např. `backlog_fixture.py`, `trace_fixture.py` a `launch_stub.py`) ověří:
  - `POST` edit, link a advice start na task s běžícím během vrací 409 s kódem `task_running` a soubor tasku se nezmění.
  - `POST` run s `force: true` na task s nesplněnou závislostí vrací 409 `unmet_dependencies` a žádný proces se nespustí.
  - Stejné požadavky na task, který neběží a není blokovaný, projdou jako dřív.
- Projdou stávající testy `tests/web/test_web_backlog*.py`, `test_web_task_run.py`, `test_web_task_advice.py` a `test_web_workflow_advice.py`. Testy, které počítaly s force startem blokovaného tasku, uprav podle nového chování.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
