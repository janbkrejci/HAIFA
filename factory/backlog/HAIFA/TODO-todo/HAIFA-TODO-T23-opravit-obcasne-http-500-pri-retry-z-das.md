---
id: HAIFA-TODO-T23
title: Zpřesnit diagnostiku retry a pokrýt jeho souběžný životní cyklus
status: done
archived: true
depends_on: []
follows: HAIFA-TODO-T21
writes: [aifactory/src/aifactory/run/store.py, aifactory/src/aifactory/run/members.py, aifactory/src/aifactory/run/retry.py, aifactory/src/aifactory/web/launcher.py, aifactory/src/aifactory/web/runs.py, aifactory/src/aifactory/web/app.py, aifactory/tests/web/test_web_launcher.py, aifactory/tests/web/test_web_runs.py, aifactory/tests/run/test_task_operation_store.py, aifactory/tests/run/test_task_retry.py, aifactory/tests/e2e/test_retry_browser.py]
---

## Zadání

Finální CI main 421d714dc7ef5e2822ab7d8c99c7ad3631460357 jednou selhalo v https://github.com/janbkrejci/HAIFA/actions/runs/39521521254: `test_retry_from_run_and_task_detail[backlog]` dostal HTTP 500 místo 202. Tatáž sada před mergem prošla. CI log neobsahuje JSON odpovědi ani subprocess log. Kompletní lokální gate následně prošel (3145 backendových testů a 23 browser scénářů). Vyšetřovací běh T23 ověřil 94 cílených testů, 22 browser opakování a řízené překryvy; původní HTTP 500 nezachytil. Tato zjištění nedokládají konkrétní produkční opravu.

Dodat konkrétní, již rozpracované zlepšení diagnostiky a regresního pokrytí do Linux CI:
- Při neúspěšném retry vypíše původní browser assertion status, celé tělo odpovědi a server.report včetně dostupných subprocess logů. Očekávaná odpověď 202 a ostatní původní assertions zůstávají zachované.
- Deterministické integrační testy ověří úspěšně claimnutý retry, jehož proces skončí před registrací operace; skutečně odmítnutý retry ve stejném pořadí vrátí původní chybu; úklid starého procesu po claimu nového pokusu nesmí změnit stav/pid/pokus nového běhu. Ověřit úklid task_operations.
- Zachovat produkční ochrany a chybové odpovědi. Nedoplňovat spekulativní produkční změnu bez reprodukce, neopakovat HTTP požadavek kvůli maskování selhání a testy nepřeskakovat.
- Popis PR přesně uvádí diagnostiku a pokrytí, nikoli neprokázanou opravu původní HTTP 500. Nevytvářet další blokující follow-up jen na publikaci či spuštění CI; to zajišťuje workflow a operátor.

Hotovo znamená: just lint, just typecheck, cílené testy přímých volajících a oba původní retry browser scénáře projdou. Nové regrese výše procházejí. Změny projdou Linux CI; případné další selhání poskytne konkrétní diagnostiku k opravě. Celou suite neprovádět uvnitř tasku.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-21 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/137 · náklady $0.00
