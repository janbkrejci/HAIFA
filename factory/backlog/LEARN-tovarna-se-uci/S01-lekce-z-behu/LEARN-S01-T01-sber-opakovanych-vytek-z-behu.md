---
id: LEARN-S01-T01
title: Sběr opakovaných výtek z běhů
status: todo
depends_on: []
---

## Zadání
Zadání:
1. `factory learn scan [--since DATUM]` projde envelopy review, triáže testů a revize ze všech běhů repa v trace DB.
2. Agent seskupí podobné výtky do lekcí. Lekce má krátké pravidlo, počet výskytů, odkazy na běhy a úryvky výtek a návrh, kam pravidlo patří (CLAUDE.md, AGENTS.md, skill repa, prompt role).
3. Lekce s jedním výskytem se nenavrhují. Lekce, kterou člověk zamítl, se znovu nenabídne (uloženo v trace DB).
4. Výstup jako text i `--json`.

Hotovo znamená:
- Test nad fixture trace DB s opakovanou výtkou a fake harnessem.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
