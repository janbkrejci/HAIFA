---
id: HAIFA-S01-T39
title: Celoplošný obrázek na pozadí dashboardu
status: todo
depends_on: []
writes: [aifactory/web/, aifactory/src/aifactory/web/static/, aifactory/THIRD_PARTY_NOTICES, THIRD_PARTY_NOTICES]
---

## Zadání
Přidat celoplošný obrázek na pozadí webového dashboardu (Vue app v `aifactory/web/`).

Kde: `aifactory/web/src/style.css`, `aifactory/web/src/App.vue`, nový obrázek v `aifactory/web/src/assets/` (nebo `aifactory/web/public/`), vygenerovaný `aifactory/src/aifactory/web/static/` přes `just web-build`.

Hotovo znamená:
- Obrázek pokrývá celé okno na všech stránkách dashboardu (`background-size: cover`, fixní vůči scrollu), bez horizontálního scrollu a deformace na úzkém i širokém okně.
- Obsah zůstává čitelný ve světlém i tmavém tématu (`lib/theme.ts`): panely a karty mají dostatečně neprůhledné pozadí nebo je přes obrázek překryv, kontrast textu se nezhorší.
- Obrázek je součástí balíčku (žádné externí URL), rozumně komprimovaný (do ~300 kB) a s licencí, která dovoluje distribuci. Pokud jde o cizí dílo, zapsat ho do THIRD_PARTY_NOTICES.
- `just web-build` aktualizuje `web/static`, `just check` a `just e2e` projdou.

Mimo rozsah: volba obrázku uživatelem v nastavení, různé obrázky pro jednotlivé stránky, redesign komponent.

Tvrdá omezení: neměnit backend API ani Python mimo vygenerovaný `web/static`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
