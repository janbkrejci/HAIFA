---
id: HAIFA-TODO-T25
title: Vrátit uložené thinking v API vláken průvodce
status: done
archived: true
depends_on: []
related: [HAIFA-REFINEMENT-T73]
writes: [aifactory/src/aifactory/web/assistant.py, aifactory/tests/web/test_web_assistant.py]
---

## Zadání
Přidat uložené thinking do API seznamu, detailu a vytvoření vlákna prostřednictvím Thread.summary(); doplnit regresní testy. Frontend T73 již volitelné thinking podporuje.

### Původ

Vznikl při běhu `6d276272` tasku `HAIFA-REFINEMENT-T73` (Průvodce z topbaru vždy otevře nové vlákno s kontextem obrazovky, minulá jsou v historii), v kroku `build` (agent builder).
Důvod: Thread.stored() thinking obsahuje, ale Thread.summary() ani detail() v aifactory/src/aifactory/web/assistant.py jej nevracejí. Backend je výslovně mimo rozsah T73.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T73 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-24 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/153 · náklady $0.00
