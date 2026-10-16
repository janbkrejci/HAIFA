---
id: INTENT-S01-T02
title: Kontrola kvality navržených tasků
status: todo
depends_on: [INTENT-S01-T01]
---

## Zadání
V backlogu HAIFA je řada tasků, které existují jen proto, aby opravily `writes` jiného tasku (TODO-T05 až T08). Návrh má takové chyby zachytit předem.

Zadání:
1. Deterministická kontrola návrhu: každý task má „Hotovo znamená“, `writes` pokrývají soubory, které zadání jmenuje, `writes` nemíří do `protected_files` ani backlogu, závislosti netvoří cyklus a dva souběžné tasky bez závislosti nemají překryv `writes`.
2. Nálezy kontroly dostane agent k opravě, zbylé uvidí člověk v náhledu.

Hotovo znamená:
- Unit testy každého pravidla.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
