---
id: HAIFA-REFINEMENT-T99
title: "Auto-continue pokračuje i po sloučení PR mimo factory (GitHub, Azure)"
status: done
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T98]
writes: [aifactory/src/aifactory/web/pr_refresh.py, aifactory/src/aifactory/web/app.py, aifactory/src/aifactory/run/queue.py, aifactory/tests/web/test_web_pr_refresh.py, aifactory/tests/run/test_auto_continue.py, aifactory/tests/run/test_factory_start.py]
---

## Zadání
Navazuje na T98. Když člověk PR, který auto-merge nesloučil, sloučí přímo v hostingu (`gh pr merge`, webové UI GitHubu nebo Azure DevOps), zjistí to jen pozadí dashboardu: aifactory/src/aifactory/web/pr_refresh.py `refresh_registered` volá `review.sync.refresh_prs`, který vrátí `states` se stavem `merged`. Řetěz se ale neobnoví. Navíc takový task zůstává v base ve stavu `todo` (`status: done` dopíše až sync PR z `factory backlog sync`), takže by ho pokračující řetěz nebo „Spustit továrnu“ mohly spustit znovu.

Co udělat:
- Když `refresh_registered` dostane od `refresh_prs` PR ve stavu `merged`, zavolá pro jeho task pokračování z T98 (`continue_after_merge`). Pokračování se rozběhne jen tehdy, když poslední řetěz tasku skončil `not_merged`, a jen jednou. Tasky dashboard spouští stejně jako jinde, tedy jako samostatné procesy `factory task run` přes launcher (web/launcher.py). Pokud k tomu potřebuješ launcher, předej ho z web/app.py, kde se `refresh_registered` plánuje (`periodic(...)`).
- V run/queue.py v `_select` zajisti, že se nespustí task, jehož nejnovější PR je `merged`, i když je v base stále `todo`. Zapiš ho jako Skip s novým důvodem (například `merged_outside`) a detailem s výzvou k `factory backlog sync`. Platí to pro auto-continue i pro `start_factory`.
- Tasky, které na sloučeném tasku závisejí, zůstanou blokované, dokud base nemá `status: done`. To je správně a test to ověří.

Mimo rozsah: automatické vytvoření nebo sloučení sync PR, změny UI.

Hotovo znamená:
- Test v aifactory/tests/web/test_web_pr_refresh.py: refresh, který vrátí sloučený PR tasku se zastaveným řetězem `not_merged`, spustí přes falešný launcher další připravený task. Druhý refresh už nespustí nic.
- Test v aifactory/tests/run/test_auto_continue.py nebo test_factory_start.py: task s PR `merged` a stavem `todo` v base se nespustí a je ve skipped s novým důvodem.
- Stávající testy pr_refresh, factory_start a auto_continue procházejí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-01 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/191 · náklady $0.00
