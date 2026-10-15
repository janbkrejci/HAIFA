---
id: HAIFA-REFINEMENT-T38
title: "Přehled: tlačítka ovládání jako ikony vpravo nahoře, aktivita dole, jednotné pozadí karet, cesta v tooltipu"
status: todo
workflow: build-test-review
depends_on: []
related: [HAIFA-REFINEMENT-T30, HAIFA-REFINEMENT-T20, HAIFA-REFINEMENT-T37, HAIFA-REFINEMENT-T13]
writes: [aifactory/web/src/components/overview/, aifactory/web/src/views/OverviewView.vue, aifactory/web/src/App.test.ts, aifactory/web/src/test/overviewFixtures.ts]
---

## Zadání
Úpravy karet repozitářů na stránce Přehled (`aifactory/web/src/components/overview/RepoCard.vue`, `RepoControls.vue`, řádky „v klidu“ v `aifactory/web/src/views/OverviewView.vue`).

## Požadavky

1. **Tlačítka run, pause, stop vpravo nahoře**
   - Tlačítka Spustit továrnu, Pauza, Pokračovat a Stop se přesunou do hlavičky karty, vpravo nahoře vedle menu pro delete (`RepoMenu`).
   - Mají být menší než teď a jen jako ikona. Text („Spustit továrnu“, „Pauza“, „Pokračovat“, „Stop“) se zobrazí jen v tooltipu (vlastní `Tooltip` z `components/ui`) a pro přístupnost zůstane v `aria-label`.
   - Chování se nemění: podmínky zobrazení (canStart/canPause/canResume/canStop), spinner během akce, potvrzovací dialog u Stop i zprávy a chyby.
   - Totéž platí pro repa v klidu (řádek `.calm` v `OverviewView.vue`), aby obě varianty vypadaly stejně.

2. **Poslední aktivita vždy až dole v kartě**
   - Údaj „Poslední aktivita“ je vždy posledním prvkem karty repa, i u rep v klidu.

3. **Stejné pozadí všech karet**
   - Teď má repo v klidu solidní (bílé) pozadí `var(--panel)` a ostatní karty průhledné `var(--panel-2)`. Pozadí všech karet se sjednotí podle repa v klidu.

4. **Cesta k repu jako tooltip u názvu**
   - Cesta k repu (`repo.path`) se už nezobrazuje jako samostatný text v hlavičce. Ukáže se v tooltipu po najetí na název repa, u karet i u rep v klidu.

## Akceptační kritéria
- Na kartě repa je v pravém horním rohu řada malých tlačítek, která obsahují jen ikonu (play/pause/stop), a vedle nich menu pro delete. Po najetí ukáže tooltip text akce.
- Akce tlačítek a jejich podmínky zobrazení fungují stejně jako dosud a stávající `data-test` atributy zůstávají zachovány.
- „Poslední aktivita“ je na konci každé karty.
- Všechny karty repozitářů mají stejné, solidní pozadí jako repo v klidu.
- Text cesty není v kartě vidět. Po najetí na název repa ji ukáže tooltip.
- Unit testy komponent Přehledu (`RepoCard.test.ts`, `RepoControls.test.ts`, případně `App.test.ts`) jsou upravené podle nového rozložení a procházejí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
