---
id: HAIFA-REFINEMENT-T13
title: Obrázek na pozadí dashboardu
status: todo
depends_on: []
related: [HAIFA-S01-T39]
writes: [aifactory/web/, aifactory/src/aifactory/web/static/, aifactory/THIRD_PARTY_NOTICES, THIRD_PARTY_NOTICES]
---

## Zadání
## Zadání
Chci přes celé okno webového dashboardu obrázek na pozadí, aby to bylo hezčí. Motiv: koťátka.

Kde: `aifactory/web/src/style.css` a `aifactory/web/src/App.vue`. Nový obrázek patří do `aifactory/web/src/assets/` nebo do `aifactory/web/public/`. Vygenerovaný výstup v `aifactory/src/aifactory/web/static/` se obnoví příkazem `just web-build`.

## Hotovo znamená
- Obrázek s koťátky pokrývá celé okno na všech stránkách dashboardu (`background-size: cover`, při scrollu zůstává na místě). Na úzkém ani širokém okně se nedeformuje a nevznikne vodorovný scroll.
- Obsah zůstává čitelný ve světlém i tmavém tématu (`lib/theme.ts`). Panely a karty mají dost neprůhledné pozadí, nebo je přes obrázek překryv. Kontrast textu se nezhorší.
- Obrázek je součástí balíčku, ne odkaz na externí URL. Je rozumně komprimovaný, nejvýš asi 300 kB. Jeho licence dovoluje distribuci, například vlastní ilustrace nebo CC0. Pokud jde o cizí dílo, zapíše se do `THIRD_PARTY_NOTICES`.
- `just web-build` obnoví `web/static`. `just check` i `just e2e` projdou.

## Mimo rozsah
- Výběr obrázku uživatelem v nastavení.
- Jiný obrázek pro každou stránku.
- Redesign komponent.

## Tvrdá omezení
- Neměnit backend API ani Python. Výjimkou je jen vygenerovaný `web/static`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
