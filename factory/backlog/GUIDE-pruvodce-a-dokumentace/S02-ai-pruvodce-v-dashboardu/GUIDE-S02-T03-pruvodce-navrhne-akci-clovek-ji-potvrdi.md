---
id: GUIDE-S02-T03
title: "Průvodce navrhne akci, člověk ji potvrdí"
status: done
depends_on: [GUIDE-S02-T02]
---

## Zadání
Zadání:
1. Průvodce smí místo provedení vrátit typovaný návrh akce: založit task, upravit task (writes, workflow, zadání), spustit nebo zopakovat běh, schválit PR, zrušit task.
2. Panel návrh ukáže jako kartu s náhledem změny a tlačítkem Provést. Provedení jde přes stávající zápisové API dashboardu se stejnou ochranou jako ruční akce.
3. Výsledek akce se vrátí do vlákna.

Hotovo znamená:
- Test, že bez potvrzení se nic nezapíše, a browser test potvrzení návrhu.
- `just web-test`, `just web-build`, dotčené testy podle AGENTS.md.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/80 · náklady $3.69
