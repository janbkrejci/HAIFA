---
id: INTENT-S02-T03
title: "Detail hotového tasku: Otevřít navazující task"
status: done
archived: true
depends_on: [INTENT-S02-T01]
---

## Zadání
Zadání:
1. Detail tasku ve stavu hotovo nezobrazuje Spustit, Upravit ani Vylepšit agentem. Místo nich má tlačítko „Otevřít navazující task“.
2. Tlačítko otevře dialog s textovým polem „Co změnit, předělat nebo dodělat“, volitelným titulkem a volbou „Spustit hned“, která je výchozí. Potvrzení založí task přes API z INTENT-S02-T01, commitne backlog, případně spustí běh a otevře detail nového tasku.
3. Detail navazujícího tasku ukazuje odkaz „Navazuje na <ID>“. Původní task ukazuje seznam tasků, které na něj navazují.

Hotovo znamená:
- Vitest detailu hotového tasku a dialogu, browser test celého toku s fake harnessem.
- `just web-test`, `just web-build`, dotčené testy podle AGENTS.md.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/94 · náklady $3.28
