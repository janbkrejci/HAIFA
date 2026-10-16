# HAIFA-REFINEMENT-T36 — Factory: „Nastavení agentů“ a sbalitelné sekce

Stránka Factory v dashboardu už neduplikuje stránku Knihovna. Sekce „Vybavení továrny“ se
jmenuje **Nastavení agentů** a obsahuje jen přenastavení harnessu, modelu a přemýšlení agentů
na úrovni repa. Všechny sekce stránky mají stejný nadpis a jdou sbalit.

## Co zmizelo ze stránky Factory

- Karty workflow, skillů a rozšíření pi (vlastní kopie / z knihovny).
- Akce **Přesunout do knihovny** u karet i u agentů, s plánem přesunu a potvrzovacím dialogem.

Obojí zůstává beze změny na stránce Knihovna (`LibrarySection.vue`). API (`/factory/items`,
plán a apply akce `move`) se nemění.

## Nastavení agentů

- `RepoItems.vue` je teď jen obal sekce: úvodní věta s knihovnou, ze které se agenti bez vlastní
  kopie dědí (z `GET /api/repos/<id>/factory/items`), a `RosterEditor.vue`.
- `RosterEditor.vue` nemá událost `move` ani tlačítko `item-move-agent-*`. Přepis, **Vrátit na
  zděděné** a náhled změny fungují jako dřív.
- Tlačítko v kroku „Co dál“ (`data-test="next-roster"`) se jmenuje **Nastavení agentů**.

## Nadpisy a sbalování

- Nová komponenta `components/ui/CollapsibleSection.vue`: `h2.section-title` s tlačítkem
  (`aria-expanded`, `aria-controls`), které sekci sbalí a rozbalí myší, Enterem i mezerníkem.
  Obsah zůstává připojený (`v-show`), formulář ani rozpracovaný přepis se sbalením neztratí.
  Stav jde řídit přes `v-model:open`, volitelný slot `aside` je vedle nadpisu (např. „Uloženo“).
- Používají ji sekce **Co dál**, **Souhrn kontroly** (nový nadpis), obě skupiny nálezů,
  **Nastavení repozitáře** (`RepoSettings.vue`) a **Nastavení agentů**.
- `FactoryView.vue` drží stav otevření sekcí. Tlačítko v „Co dál“ i trasa
  `#/r/<id>/factory/settings` sekci nejdřív rozbalí a pak na ni posunou stránku.

## Testy

`CollapsibleSection.test.ts`, `RepoItems.test.ts`, `RosterEditor.test.ts`, `RepoSettings.test.ts`
a `FactoryView.test.ts` (jednotné nadpisy, sbalení každé sekce, rozbalení při přechodu,
žádný text „Vybavení továrny“ ani „Přesunout do knihovny“).
