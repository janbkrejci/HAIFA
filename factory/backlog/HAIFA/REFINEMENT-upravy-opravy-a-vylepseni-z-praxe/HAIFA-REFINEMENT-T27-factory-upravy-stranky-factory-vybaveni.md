---
id: HAIFA-REFINEMENT-T27
title: "Factory – úpravy stránky Factory (Vybavení továrny, chip konfigurace, nálezy)"
status: todo
workflow: simple-sdlc
depends_on: []
related: [HAIFA-REFINEMENT-T24, HAIFA-REFINEMENT-T03, HAIFA-REFINEMENT-T01, HAIFA-S05-T14, HAIFA-S05-T16]
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/src/aifactory/config/, aifactory/src/aifactory/check/, aifactory/src/aifactory/guide/, aifactory/tests/]
---

## Zadání
Úpravy stránky Factory v dashboardu z praxe.

## 1. Opravit hlášku v sekci „Položky repa“
Teď se zobrazuje: „Bez vlastní kopie v .factory/ se položka dědí z knihovnyaa8e9808b9a3a45697b65223d019063bd4e3e289.“ (`aifactory/web/src/components/factory/RepoItems.vue`). Chybí mezera a místo čitelného označení knihovny se ukazuje holý commit hash.

**Akceptace:** Hláška je gramaticky v pořádku a mezi textem a označením knihovny je mezera. Knihovna je označena srozumitelně, tedy názvem knihovny, případně zkráceným hashem jako doplňkem. Celý 40znakový SHA nalepený na slovo se už nezobrazuje.

## 2. Tlačítko „Commitnout konfiguraci“ nahradit chipem v topbaru
Odstranit tlačítka „Commitnout konfiguraci“ ze stránky Factory (`FactoryView.vue`: další kroky i akce, odkaz v `RosterEditor.vue` a odkaz v textu `RepoSettings.vue`). Místo nich se v topbaru zobrazí chip, když existuje necommitnutá konfigurace. Chip je červený a vypadá a chová se obdobně jako stávající chip pro necommitnutý backlog. Kliknutím na chip se otevře commit konfigurace (operace `config_commit`).

**Akceptace:** Na stránce Factory nezůstane žádné tlačítko ani odkaz „Commitnout konfiguraci“. Chip se objeví jen tehdy, když je co commitnout, a vede na commit konfigurace. Stylem odpovídá chipu backlogu.

## 3. Sekce „Položky repa“ → „Vybavení továrny“
- Sekci přejmenovat na „Vybavení továrny“.
- Vylepšit zobrazení agentů, workflows a skillů.
- Odstranit dvojí zobrazení seznamu agentů: dnes jsou agenti v položkách repa a znovu v rosteru (`RosterEditor.vue`). Pokud to jde, oba seznamy sloučit do jednoho.
- U agentů zachovat zobrazení harnessu, modelu a thinking levelu.
- Umožnit změnit harness, model a thinking na úrovni projektu a také je vrátit na výchozí hodnoty zděděné z knihovny.

**Akceptace:** Sekce se jmenuje „Vybavení továrny“ a každý agent je v ní uveden jen jednou. U každého agenta je vidět harness, model a thinking a je poznat, zda jde o zděděnou, nebo přepsanou hodnotu. Hodnoty lze přepsat a přepis lze vrátit na zděděnou hodnotu. Změna se projeví v konfiguraci, kterou čtou běhy.

## 4. Sekce problémů: jeden souhrnný warning o necommitnuté konfiguraci
Dnes se warning o necommitnuté konfiguraci zobrazuje zvlášť pro každý soubor. Nově bude jeden souhrnný warning, který může vyjmenovat dotčené soubory.

**Akceptace:** Při více necommitnutých souborech konfigurace je v sekci problémů jen jeden takový warning.

## 5. Řešení nálezu u nálezu
Řešení nálezu (`FactoryFindingRepair.vue`) se dnes zobrazuje daleko od samotných nálezů. Nově se zobrazí buď v modalu, nebo přímo pod nálezem, ke kterému patří.

**Akceptace:** Po spuštění řešení nálezu je jeho průběh a výsledek vidět bez scrollování pryč od nálezu.

## Obecně
- Upravit nebo doplnit testy dotčených komponent (např. `RepoItems.test.ts`, `RosterEditor.test.ts`, `UncommittedBanner.test.ts`, `FactoryOperation.test.ts`).
- Pokud se mění texty a názvy v UI, aktualizovat i průvodce v `aifactory/src/aifactory/guide/`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
