---
id: HAIFA-REFINEMENT-T18
title: Návrh workflow bez kopie celého repa a bez úniku dočasných adresářů
status: todo
depends_on: []
---

## Zadání
V noci došlo místo na disku C: a selhal běh NEO_HEF ROB-S15-T004 (`No space left on device`). V `%TEMP%` ležely dva adresáře `factory-advice-*` po 4,8 GB z 13. 10. 15:50 a 15:55. `workflow/adaptive.py` (návrh workflow / parametrů tasku) dělá `git clone --no-hardlinks` celého repa do `TemporaryDirectory`: u NEO_HEF (61 tisíc souborů) je to 4,8 GB na jeden návrh, a když proces (dashboard) skončí uprostřed, adresář po sobě nechá.

Zadání:
1. Izolovaná kopie pro návrh nekopíruje objekty repa (např. `git clone --shared`, nebo `git worktree add --detach` s úklidem), checkout jen toho, co plánovač potřebuje, pokud to jde.
2. Při startu návrhu (a dashboardu) se smažou osiřelé `factory-advice-*` adresáře starší než běžící návrhy.
3. Úklid na Windows zvládne read-only soubory gitu.

Hotovo znamená:
- Test: návrh nad repem s historií nevytvoří kopii objektů (velikost dočasného adresáře řádově menší než `.git`), a osiřelý `factory-advice-*` adresář se při dalším návrhu smaže.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
