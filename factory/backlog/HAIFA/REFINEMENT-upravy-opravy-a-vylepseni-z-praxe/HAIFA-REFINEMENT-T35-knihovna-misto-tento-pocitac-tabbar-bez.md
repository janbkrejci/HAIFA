---
id: HAIFA-REFINEMENT-T35
title: "Knihovna místo „Tento počítač“, tabbar bez scrollbaru, dialogy knihovny a obnova knihovny při instalaci nové verze"
status: done
archived: true
workflow: simple-sdlc
depends_on: []
related: [HAIFA-REFINEMENT-T24, HAIFA-REFINEMENT-T27, HAIFA-REFINEMENT-T32, HAIFA-S10-T04, HAIFA-S10-T05, HAIFA-S05-T17, HAIFA-S04-T02, HAIFA-S04-T04, HAIFA-S01-T15]
---

## Zadání
Soubor drobných úprav z praxe. Všechny se týkají UI dashboardu a knihovny.

## 1. Tabbar (Backlog, Běhy, …)
- Zkontrolovat a vylepšit layout tabbaru. Teď má vpravo vertikální scrollbar.
- **Hotovo, když:** tabbar nemá při běžné šířce okna žádný vertikální scrollbar, a to na žádné stránce, kde se používá (Backlog, Běhy a další).

## 2. Stránka „Tento počítač“ → „Knihovna“
- Stránku přejmenovat na **Knihovna**. Týká se to titulku stránky, nadpisu, `document.title` i textů v průvodci a UI.
- Odstranit ji z pravého horního menu (přepínač repozitářů). Dostupná bude jen z chipu knihovny v top baru.
- **Hotovo, když:** v pravém horním menu není odkaz na stránku. Kliknutí na chip v top baru otevře stránku s názvem „Knihovna“. Testy jsou upravené podle nového stavu.

## 3. Dialog obnovení knihovny ze seedu
- Potvrzovací tlačítko v dialogu má jinou barvu, než mají potvrzovací tlačítka v ostatních dialozích.
- **Hotovo, když:** tlačítko používá stejný styl jako ostatní potvrzovací dialogy (u destruktivní akce stejný styl jako ostatní destruktivní potvrzení). Ověřeno v dark i light mode.

## 4. Importní dialog knihovny
- Pole pro cestu vypadá jinak než ostatní inputy. Chci ho hezčí a hlavně má používat **existující path browser** z přidávání repa.
- **Hotovo, když:** import knihovny používá stejnou komponentu pro výběr cesty jako přidání repa (procházení adresářů a ruční zadání).

## 5. Seznam objektů knihovny (agenti, workflow, …)
- Úhlednější a přehlednější layout seznamu.

## 6. Pravý panel položky knihovny: smazání custom verze z repa
- Vedle převzetí custom verze do knihovny přidat akci **smazat custom verzi z repa**, aby se položka znovu dědila z knihovny.
- Akce se musí potvrdit v dialogu.
- **Hotovo, když:** po potvrzení zmizí custom verze z repa a položka se zobrazí jako zděděná. Bez potvrzení se nic nesmaže.

## 7. Obnova knihovny při instalaci nové verze factory
- Knihovna se vždy při instalaci nebo upgradu nové verze factory obnoví na aktuální obsah dané verze.
- Customizace si uživatel drží ve svých repech. Obnova knihovny je nepřepisuje.
- **Hotovo, když:** po instalaci nebo upgradu odpovídá obsah knihovny nainstalované verzi. Custom verze v repech zůstanou nedotčené.

## 8. Skill v knihovně při instalaci
- Při instalaci nebo upgradu nové verze se v knihovně vytvoří skill z výstupu `factory --skill`.
- **Hotovo, když:** po instalaci nebo upgradu je v knihovně skill, jehož obsah odpovídá výstupu `factory --skill` nainstalované verze.

## Testy
- Upravit nebo doplnit unit testy frontendu u dotčených komponent (menu, chip, dialogy, seznam knihovny, pravý panel).
- Doplnit backendové testy pro obnovu knihovny a vytvoření skillu při instalaci.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-15 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/49 · náklady $10.16
