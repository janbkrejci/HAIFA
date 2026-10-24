---
id: HAIFA-REFINEMENT-T75
title: "Tmavý motiv: žádná bílá textová pole, sjednocený styl formulářových polí"
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/web/src/, aifactory/src/aifactory/web/static/, aifactory/tests/e2e/test_theme_forms_browser.py, aifactory/src/aifactory/seed/agents/tester/user.md]
---

## Zadání
## Cíl
V tmavém motivu dashboardu (výchozí `:root` v `aifactory/web/src/style.css`) jsou některá textová pole bílá: mají bílé pozadí z prohlížeče a v nich světlý nebo nečitelný text. Projdi celé web UI v tmavém motivu a oprav to systémově.

## Co udělat
- V `aifactory/web/src/style.css` doplň globální výchozí styl pro `textarea`, `input` (textové typy: text, search, number, url, password, bez checkbox/radio) a `select`. Použij nízkou specificitu `:where(...)`, stejně jako už má `:where(button)`: pozadí `var(--panel-2)` nebo `var(--panel-3)`, `color: var(--text)`, `border: 1px solid var(--border)`, `border-radius`, `font: inherit`, placeholder v `var(--faint)` a focus-visible obrys v `var(--cyan)`. Nastav i `color-scheme: dark` pro `:root` a `color-scheme: light` pro `[data-theme="light"]`, aby měly i nativní části (scrollbar, autofill, číselné šipky, datalist) správný motiv.
- Projdi komponenty a view s formulářovými poli v adresáři `aifactory/web/src/`. Najdi pole, která nemají vlastní styl nebo mají natvrdo světlé barvy (`#fff`, `white`, `background: white`, světlé hex barvy), a sjednoť je na proměnné motivu. Zkontroluj hlavně `aifactory/web/src/components/setup/RepoLibraryItems.vue`, `aifactory/web/src/components/setup/DashboardSettings.vue`, `aifactory/web/src/components/backlog/BacklogFilters.vue`, `aifactory/web/src/components/repos/InspectCard.vue`, `aifactory/web/src/components/factory/InstallForm.vue`, `aifactory/web/src/components/factory/FactoryOperation.vue`, `aifactory/web/src/views/ReviewView.vue`, `aifactory/web/src/views/OverviewView.vue`, `aifactory/web/src/views/FactoryView.vue`. Lokální duplicitní styly (`textarea { ... }` v jednotlivých dialozích) můžeš zjednodušit, když po změně vypadají stejně.
- Hledej i jiné bílé plochy s textem v tmavém motivu (pre/code bloky, karty, popovery). Najdeš-li je, oprav je stejným způsobem.
- Světlý motiv se nesmí rozbít: pole v něm zůstanou světlá s tmavým textem.
- Po změně zdrojů spusť `just web-build` a commitni přegenerovaný `aifactory/src/aifactory/web/static/` (statický build je v repu).

## Mimo rozsah
Redesign barevné palety, nové motivy, změny chování formulářů. Checkboxy, radio a switch mají vlastní styl, ten neměň.

## Hotovo znamená:
- V tmavém motivu nemá žádná `textarea`, textový `input` ani `select` v dashboardu bílé pozadí. Text v nich má barvu `var(--text)` a je čitelný. Platí to i pro pole bez vlastního scoped stylu.
- `aifactory/web/src/style.css` obsahuje globální `:where(...)` styl formulářových polí a `color-scheme` pro oba motivy.
- Ve zdrojích v `aifactory/web/src/` nezůstala pro pole a plochy s textem natvrdo bílá barva pozadí, která by se v tmavém motivu ukázala.
- Světlý motiv vypadá jako dřív (světlá pole, tmavý text).
- `just web-test` projde (typecheck i vitest). Testy, které hlídají selektory nebo styly dotčených komponent, jsou aktualizované.
- `aifactory/src/aifactory/web/static/` je přegenerovaný přes `just web-build` a commitnutý.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-24 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/155 · náklady $0.00
