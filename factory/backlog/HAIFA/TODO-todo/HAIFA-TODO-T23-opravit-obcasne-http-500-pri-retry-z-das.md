---
id: HAIFA-TODO-T23
title: Opravit občasné HTTP 500 při retry z dashboardu
status: todo
depends_on: []
follows: HAIFA-TODO-T21
writes: [aifactory/src/aifactory/run/store.py, aifactory/src/aifactory/run/members.py, aifactory/src/aifactory/run/retry.py, aifactory/src/aifactory/web/launcher.py, aifactory/src/aifactory/web/runs.py, aifactory/src/aifactory/web/app.py, aifactory/tests/web/test_web_launcher.py, aifactory/tests/web/test_web_runs.py, aifactory/tests/run/test_task_operation_store.py, aifactory/tests/run/test_task_retry.py, aifactory/tests/e2e/test_retry_browser.py]
---

## Zadání
Finální CI main 421d714dc7ef5e2822ab7d8c99c7ad3631460357 selhalo v https://github.com/janbkrejci/HAIFA/actions/runs/39521521254: tests/e2e/test_retry_browser.py::test_retry_from_run_and_task_detail[backlog] řádek 116 dostal HTTP 500 místo 202 při POST /api/repos/repo/runs/{run_id}/retry. Tatáž sada na PR #136 před mergem prošla a varianta runs v neúspěšném CI též prošla. Backend suite i Windows jsou zelené. Podrobný výstup je operátorovi v /tmp/haifa-main-final-failure.log. Místní reprodukce originálního browser testu běží s --basetemp=/tmp/haifa-retry-diagnosis, takže lze číst obs.log a logy subprocessů; první varianta runs uspěla.

Vyšetři a oprav příčinu HTTP 500 při rychlém retry, zejména souběh RunLauncher._launch/_reap, register_operation/finish_operation a claim nového pokusu z T21. Zachovej zobrazení pending operací a odstranění operací po claimu/exitu. Zachovej odpověď 202 při úspěšném retry; chyby skutečně odmítnutého retry zůstávají odpovídající chyby, ne falešný úspěch. Nezakrývej selhání opakováním HTTP požadavku ani vyřazením testu.

Získej konkrétní důvod 500 (JSON odpověď i log procesu) a doplň deterministickou regresi, pokud jde o souběh. Zlepši diagnostiku browser assertion, aby při chybě obsahovala odpověď a server.report, místo samotného statusu. Ověř obě varianty původního retry browser testu a nové unit/integration regrese. Povinné just lint, just typecheck a cílené pytest změněných balíčků/přímých volajících; žádná celá suite uvnitř tasku. Testy nezávislé na živých modelech/službách.

Hotovo znamená: příčina selhání vysvětlená důkazem a opravená; původní browser scénář retry ze seznamu běhů i Backlogu prochází, nové regrese pokrývají nalezený stav. Neoslabuj ochrany tasků ani registraci/úklid operací.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
