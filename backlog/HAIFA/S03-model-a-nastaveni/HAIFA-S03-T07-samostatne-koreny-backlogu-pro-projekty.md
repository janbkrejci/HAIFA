---
id: HAIFA-S03-T07
title: Samostatné kořeny backlogu pro projekty
status: done
depends_on: [HAIFA-S03-T04]
---

## Zadání
Umožni, aby projekty v jednom repu měly backlog v samostatných kořenech, například `moduly/M07/backlog/`, ne jen jako podadresáře jednoho `backlog/` (rozhodnutí Samostatné kořeny backlogu v `docs/decisions.md`).

Where: `aifactory/src/aifactory/config/settings.py`, `aifactory/src/aifactory/backlog/` (`loader.py`, `model.py`, `validate.py`, `edit.py`, `commit.py`), `aifactory/src/aifactory/run/` (čtení backlogu z base), `aifactory/src/aifactory/web/backlog.py`, `aifactory/src/aifactory/skill/skill.md`, testy v `aifactory/tests/`.

Done means:
- `.factory/config.yaml` přijme `backlog_dirs: [cesta, …]` (relativní cesty uvnitř repa, i se vzorem `*`, například `moduly/*/backlog`). `backlog_dir` dál funguje jako jediný kořen. Obě nastavení současně jsou chyba konfigurace.
- Každý kořen obsahuje projekty stejně jako dnes `backlog/`. Id projektů, stepů a tasků musí být jedinečná napříč kořeny a duplicitu hlásí `factory backlog check` s cestami obou souborů.
- Načtení backlogu, `backlog check`, `backlog list`, `task add|edit|link`, běh tasku z base, `backlog commit` (commituje změny ve všech kořenech) i API dashboardu pracují se všemi kořeny. Zakládání projektu umí zvolit kořen.
- `factory --skill` popisuje `backlog_dirs`.
- Testy (pytest) v dočasném repu se dvěma kořeny: načtení, duplicitní id, běh tasku z druhého kořene s falešným harnessem, `backlog commit` změn v obou kořenech, API backlogu.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: úprava nastavení kořenů z dashboardu, přesun existujícího projektu mezi kořeny.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/47 · náklady $2.54
