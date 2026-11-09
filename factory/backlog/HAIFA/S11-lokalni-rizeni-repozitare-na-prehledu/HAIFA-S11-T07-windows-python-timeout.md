---
id: HAIFA-S11-T07
title: Opravit timeouty testů a chybová okna Pythonu na Windows
status: todo
depends_on: [HAIFA-S11-T02]
writes: [aifactory/]
test_timeout: 1200
---

## Zadání

Vyšetřit a opravit chybová okna python.exe (0xc0000142) při timeoutu testů Factory na Windows. Důkaz: běh HAIFA-S11-T02 c612e428 dne 2026-11-09, System/Application Popup ID 26 v 11:29:30, 11:45:18, 11:47:38 a 11:49:59. Časy přesně odpovídají dokončení timeoutovaných checků 04_merge-approve-publish-retry-and-web-callers, 07_sequential-scope-blockers-and-environment, 07_merge-approve-publish-retry-and-web-callers a 07_merge-publication-and-retry-callers. command.log obsahuje exit 124, node down a limity 130/140/260 s. Lokální důkazy jsou v .factory/data/sessions/c612e428/context_handoff/quality/ a HAIFA_HOME/logs/20261109-103132-4888-run-HAIFA-S11-T01-c447c596.log; nejsou verzované a mohou být později uklizeny. Necommitovat transcript, DB ani lokální logy.

Časová shoda potvrzuje vazbu na timeout, nikoli konkrétní příčinu selhání inicializace. Ověřit malým izolovaným reproduktorem na Windows: rodič spouští Python potomky během timeoutu. Prozkoumat engine/quality.py::_run, oscompat.py::_taskkill/kill_group a testing/executor.py. Rozlišit, zda test čeká na dialog, visí na locku/potomku, nebo pouze potřebuje více času. Využít průběžný výstup a stack dump před timeoutem; reprodukce musí mít vlastní omezený dohled a nesmí zasáhnout aktivní Factory či cizí procesy.

Opravit zjištěnou příčinu. U legitimně pomalých testů nastavit cílené limity s rezervou v rámci test_timeout; neprodlužovat globálně všechny limity a nezakrýt deadlock delším čekáním. Ukončení musí pokrýt i potomka vznikajícího při timeoutu a nenechat orphan procesy; zvolit podložené řešení pro Windows po ověření skutečného mechanismu. Pokud je nutné vypnout interaktivní systémový dialog pro řízené child procesy, nesmí tím zmizet chyba: zachovat návratový kód, důvod a diagnostiku v command.log. Neměnit globální registry Windows ani uživatelský Python. Zachovat normální úspěšný běh a POSIX chování.

Přidat regresi skutečného timeoutu, potomka při ukončování, rodiče ukončeného dříve než child, již neexistujícího procesu a běžného dokončení. Ověřit ohraničené dokončení bez kliknutí, žádné pozůstalé procesy ani ovlivnění nesouvisejícího procesu, exit 124 a zachovaný výstup. Pouhé zamockování taskkill není dostatečný důkaz odstranění Windows problému; doplnit izolovaný Windows integrační test a doložit, zda se Application Popup neopakuje.

Před změnou vyhledat přímé volající v celém aifactory/tests/. Kandidáti jsou run/test_task_test_timeout.py, workflow/test_workflow_test_timeout.py a testy ostatních skutečně ovlivněných volajících quality/oscompat. Spustit just lint, just typecheck, všechny editované testové soubory a jen relevantní přímé volající přes just pytest. Bez celé sady, browser testů a živých modelů/služeb. Opravu držet odděleně od funkčního rozšiřování auto continue. Hotovo znamená reprodukovanou a ověřenou opravu, ne jen potlačené okno nebo přidaný timeout.

## Běhy

<!-- doplňuje HAIFA při schválení PR -->

