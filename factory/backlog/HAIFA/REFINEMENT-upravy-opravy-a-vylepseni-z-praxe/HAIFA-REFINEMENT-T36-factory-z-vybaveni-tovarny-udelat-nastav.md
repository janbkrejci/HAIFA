---
id: HAIFA-REFINEMENT-T36
title: "Factory: z „Vybavení továrny“ udělat „Nastavení agentů“, sjednotit a sbalovat sekce stránky"
status: done
archived: true
workflow: build-test-review
depends_on: [HAIFA-TODO-T09]
related: [HAIFA-REFINEMENT-T27, HAIFA-REFINEMENT-T24, HAIFA-REFINEMENT-T35, HAIFA-REFINEMENT-T03]
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/src/aifactory/guide/]
---

## Zadání
## Zadání
Úpravy stránky Factory v dashboardu. 

### 1. Odstranit z „Vybavení továrny“ duplicity se stránkou Knihovna
Stránka Knihovna (`components/setup/LibrarySection.vue`) už ukazuje položky podle typu, repa s vlastní kopií, diff a „Přesunout kopii repa do knihovny“. Ze stránky Factory proto odstranit:
- výpis workflows, skillů a extensions (karty „vlastní kopie / z knihovny“),
- akci „Přesunout do knihovny“, a to u karet i u agentů v `RosterEditor.vue` (`item-move-*`), včetně plánu přesunu a potvrzovacího dialogu.

### 2. Přejmenovat sekci na „Nastavení agentů“
Sekce bude obsahovat jen přenastavení harnessu, modelu a thinking levelu agentů na úrovni repa. Zůstává tedy tabulka agentů z `RosterEditor.vue`: zděděné nebo přepsané hodnoty, přepis, „Vrátit na zděděné“ a náhled změny. Přejmenovat i tlačítko „Vybavení továrny“ v kroku „Co dál“ (`FactoryView.vue`, `data-test="next-roster"`) a texty a komentáře, které se na sekci odkazují.

### 3. Sjednotit nadpisy sekcí na stránce
Nadpisy sekcí stránky Factory budou mít jednotnou úroveň a vzhled. Jde o sekce „Co dál“, souhrn kontroly a skupiny nálezů, „Nastavení repozitáře“ (`RepoSettings.vue`) a „Nastavení agentů“. Dnes má každá komponenta jiný styl h2 (např. RepoItems velkými písmeny, šedě, 14 px).

### 4. Sbalitelné sekce
Sekce stránky Factory půjdou sbalit a rozbalit kliknutím na nadpis. Rozbalení a sbalení musí jít ovládat i klávesnicí a stav musí být přístupný (např. `<details>/<summary>` nebo tlačítko s `aria-expanded`).

## Akceptace
- Na stránce Factory není výpis workflows, skillů ani extensions a nikde na ní není akce „Přesunout do knihovny“. Tyto funkce zůstávají na stránce Knihovna beze změny.
- Sekce se jmenuje „Nastavení agentů“. Každý agent je v ní uveden jednou, s harnessem, modelem a thinking levelem a s rozlišením zděděné a přepsané hodnoty. Přepis i „Vrátit na zděděné“ fungují stejně jako dosud.
- Na stránce Factory ani v průvodci nezůstane text „Vybavení továrny“.
- Všechny sekce stránky mají nadpisy stejné úrovně a stylu.
- Každou sekci lze sbalit a znovu rozbalit myší i klávesnicí a její obsah se přitom skryje a zase zobrazí.
- Přechody na sekci (např. tlačítko v „Co dál“, otevření nastavení) sekci rozbalí, pokud je sbalená.

## Obecně
- Upravit testy dotčených komponent: `FactoryView.test.ts`, `RepoItems.test.ts`, `RosterEditor.test.ts`, případně `RepoSettings.test.ts`. Odebrat testy odstraněných funkcí a doplnit testy sbalování a nového názvu.
- Aktualizovat průvodce v `aifactory/src/aifactory/guide/` (`04-dashboard.md`, `08-konfigurace-repa.md`, `12-tym.md`), kde se zmiňuje „Vybavení továrny“.
- Pokud repo verzuje sestavený frontend v `aifactory/src/aifactory/web/static/`, přebuildovat ho.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/59 · náklady $2.71
