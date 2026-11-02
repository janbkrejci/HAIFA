---
id: HAIFA-REFINEMENT-T104
title: "Selhání needs_environment: běh skončí hned a řetěz pokračuje"
status: done
archived: true
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T103]
writes: [aifactory/src/aifactory/seed/agents/builder/system.md, aifactory/src/aifactory/seed/agents/tester/system.md, aifactory/src/aifactory/failure.py, aifactory/src/aifactory/run/queue.py, aifactory/src/aifactory/run/heal.py, aifactory/src/aifactory/run/task.py, aifactory/src/aifactory/engine/agents.py, aifactory/web/src/lib/failure.ts, aifactory/web/src/components/runs/, aifactory/src/aifactory/web/static/, aifactory/tests/test_failure.py, aifactory/tests/run/test_failure_kind.py, aifactory/tests/run/test_auto_continue.py, aifactory/tests/run/test_auto_heal.py]
---

## Zadání
Agent, kterému v běhu chybí prostředí (živé měření GUI v odpojené session, skrytá plocha, která nedoručí klávesy ani myš, sdílený zdroj držený jiným během), dnes buď založí lidský task „změř to ručně“, nebo vrátí `status: fail`. Selhání ale řetěz zastaví: run/queue.py po neúspěšném `_heal_in_chain` vrací `STOP_FAILED` a samoléčení běh zopakuje ve stejném prostředí. NEO_HEF od 2. 11. 2026 v AGENTS.md předepisuje v takovém případě okamžitý konec s `status: fail` a `fail_kind: needs_environment` bez lidského tasku. Factory tento druh zatím nezná.

Co udělat:
- Nový druh selhání `needs_environment` (aifactory/src/aifactory/failure.py) z `fail_kind: needs_environment`. `failure_detail` nese agenta a jeho summary (co prostředí chybělo).
- Řetěz (run/queue.py) se po takovém běhu nezastaví. Task zůstane `todo` bez PR, zapíše se jako Skip s novým důvodem (např. `needs_environment`) a řetěz pokračuje dalším připraveným taskem. Tasky, které na něm závisejí, se nespustí, protože není hotový. Ve stejném řetězu se znovu nespustí.
- Samoléčení (run/heal.py) takový běh neopakuje.
- Dashboard ukáže druh srozumitelně v kartě selhání (aifactory/web/src/lib/failure.ts, FailureCard.vue) s akcí „spustit znovu“, až bude prostředí k dispozici.
- Seed prompty `builder` a `tester` dostanou jednu větu: když práce potřebuje prostředí, které běh nemá, okamžitě vrať `status: fail` s `fail_kind: needs_environment` a v summary napiš, co chybí, místo lidského tasku nebo follow-upu.

Mimo rozsah: zjišťování stavu session nebo plochy samotnou factory.

Hotovo znamená:
- Test v aifactory/tests/run/test_auto_continue.py: řetěz tří tasků, kde druhý skončí `needs_environment`, spustí třetí, druhý zůstane `todo` a je ve skipped s novým důvodem.
- Test v aifactory/tests/run/test_auto_heal.py: `needs_environment` se samoléčením neopakuje.
- Test v aifactory/tests/test_failure.py a aifactory/tests/run/test_failure_kind.py: klasifikace nového druhu.
- Test karty selhání ve FailureCard.test.ts.
- Stávající testy procházejí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-02 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/199 · náklady $0.00
