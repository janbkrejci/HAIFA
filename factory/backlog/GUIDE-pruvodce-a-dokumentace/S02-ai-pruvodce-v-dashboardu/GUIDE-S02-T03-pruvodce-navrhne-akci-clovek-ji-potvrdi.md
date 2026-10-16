---
id: GUIDE-S02-T03
title: "Průvodce navrhne akci, člověk ji potvrdí"
status: todo
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
