---
id: HEAL-S02-T02
title: Builder bez práce ukončí běh jako hotový bez změn
status: todo
depends_on: [HEAL-S01-T01]
---

## Zadání
V HAIFA šest běhů selhalo, protože builder správně zjistil, že není co dělat (práci už udělal jiný task, nebo zadání žádá jen změnu front matter). Běh pak visí jako selhaný.

Zadání:
1. Builder smí vrátit stav „už hotovo“ s důkazem (commit nebo soubor, kde změna je). Rozšířit `BuildOutput` a prompt buildera v semínku.
2. Takový běh skončí jako úspěšný bez změn podle rozhodnutí „Prázdný commit“ v `docs/decisions.md` (task `done` v base se záznamem „bez změn“ a důkazem).
3. Když builder hlásí, že zadání žádá jen změnu backlogu, běh skončí s druhem `nothing_to_do` a dashboard nabídne Hotovo nebo Zrušit.

Hotovo znamená:
- Testy obou cest s fake harnessem.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
