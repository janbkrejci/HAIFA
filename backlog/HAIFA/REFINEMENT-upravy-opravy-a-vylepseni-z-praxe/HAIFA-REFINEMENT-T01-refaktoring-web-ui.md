---
id: HAIFA-REFINEMENT-T01
title: "Refaktoring web UI: ergonomie, úklid a řízení výroby"
status: done
workflow: simple-sdlc
depends_on: []
related: [HAIFA-S03-T16, HAIFA-S08-T01, HAIFA-S08-T02, HAIFA-S01-T34, HAIFA-S06-T05, HAIFA-S05-T14, HAIFA-S05-T16, HAIFA-S01-T37, HAIFA-S01-T38]
writes: [aifactory/]
---

## Zadání
Je potřeba uhladit web UI (Vue frontend `aifactory/web/src` a jeho API `aifactory/src/aifactory/web/`):

- vylepšit ergonomii – lépe vést uživatele všemi cestami použití,
- odstranit mrtvé a staré funkce,
- odstranit duplicity a zbytečnosti.

### Na co se soustředit

1) **První návštěva** – konfigurace harnessů a modelů, inicializace factory, onboarding repozitářů, knihovna; prostě příprava na práci v několika repo současně.

2) **Semi-interaktivní tvorba backlogů** – konfigurace workflows, promptů, agentů, testování.

3) **Řízení výroby**
   - ad-hoc úprava použitých harnessů (v každém repu může být jiný, dokonce i v rámci jednoho workflow může být zapojeno více harnessů),
   - příprava běhu – doladění parametrů, revize zadání,
   - spouštění běhů – auto continue musí být inteligentní:
     - v kanbanu jde určit pořadí tasků, které jsou ready, a auto continue je pak bere přednostně v tomto pořadí,
     - v kanbanu jde tasky ručně vyloučit z auto continue – buď přepínačem na tasku, nebo třeba přesunem do swimlane „odloženo“.

4) **Schvalování PR.**

Plus oprava nalezených drobných chyb, např. aktuálně nezobrazujeme Claude limity.

### Akceptační kritéria
- Každá ze čtyř cest (první návštěva, tvorba backlogu, řízení výroby, schvalování PR) jde v UI projít bez slepých míst a uživatel na každém kroku vidí, co dál.
- Mrtvé, zastaralé a duplicitní obrazovky, komponenty a endpointy jsou odstraněné, včetně jejich testů. Co bylo odstraněno a proč, je v popisu PR.
- Pořadí ready tasků nastavené v kanbanu se uloží a auto continue podle něj vybírá další task.
- Task vyloučený v kanbanu z auto continue se automaticky nespustí. Ručně spustit jde dál.
- Limity Claude se znovu zobrazují v horní liště (`LimitsBar`) vedle Codexu.
- Nalezené drobné chyby jsou opravené a vyjmenované v popisu PR.
- `just check-scoped` prochází. Změněné chování pokrývají frontendové i backendové testy.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/99 · náklady $43.23
