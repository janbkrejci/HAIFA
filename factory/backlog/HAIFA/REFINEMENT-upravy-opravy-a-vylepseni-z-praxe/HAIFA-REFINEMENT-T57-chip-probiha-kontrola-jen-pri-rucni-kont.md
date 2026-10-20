---
id: HAIFA-REFINEMENT-T57
title: "Chip „Probíhá kontrola“ jen při ruční kontrole, ne při každém načtení stránky"
status: todo
workflow: build-test-review
depends_on: []
writes: [aifactory/web/src/lib/readiness.ts, aifactory/web/src/components/OverviewReadiness.vue, aifactory/web/src/components/OverviewReadiness.test.ts, aifactory/web/src/App.vue, aifactory/web/src/App.test.ts, aifactory/src/aifactory/web/static/]
---

## Zadání
## Zadání
Chip „Probíhá kontrola“ v topbaru (`aifactory/web/src/components/OverviewReadiness.vue`, režim `chip`) teď vypadá, jako by se kontrola stroje a rep spouštěla pořád dokola, například po každém kliknutí na logo HAIFA. Kontrola se má skutečně provádět jen při startu továrny (server dashboardu ji pouští jednou při startu, také po restartu kvůli upgradu) a na ruční žádost. Chip má ukazovat „Probíhá kontrola“ jen tehdy, když kontrola opravdu běží.

## Příčina
- `aifactory/web/src/lib/readiness.ts`: `check()` při každém volání nastaví `phase = 'checking'` a vyprázdní `issues`. Volá se v `onMounted` při každém načtení stránky. Data přitom jen čte z cache serveru (`/api/machine/check` bez `fresh`), přesto chip mezitím ukazuje „Probíhá kontrola“.
- Logo HAIFA je záměrně odkaz `href="/"` (HAIFA-S01-T36), takže klik načte celou stránku znovu a chip znovu ukáže kontrolu. Odkaz neměň.
- Čerstvou kontrolu (`fresh=1`) spouští i automatické podněty: událost `factory-applied` v `readiness.ts`, uložení a test harnessů v `App.vue` (`readiness.recheck()` v `MachineHarnessesDialog`) a odebrání repa v `OverviewReadiness.vue`.

## Co udělat
- Rozliš dva způsoby obnovy:
  - **Čtení výsledku** (bez `fresh`): při načtení stránky a po automatických podnětech. Proběhne potichu. Chip během čtení neukazuje „Probíhá kontrola“: buď zůstane předchozí stav, nebo při prvním načtení stránky není vidět nic. Výjimka: když čtení trvá déle než asi 1 s (server ještě dokončuje kontrolu po startu), smí se „Probíhá kontrola“ ukázat.
  - **Ruční kontrola** (`fresh=1`): klik na zelený chip „Systém v pořádku“ a tlačítko „Zkontrolovat znovu“ na stránce Problémy. Jen tady se hned ukáže „Probíhá kontrola“.
- Automatické podněty (`factory-applied`, uložení a test harnessů, odebrání repa) nesmí přepnout chip na „Probíhá kontrola“. Ponech jen tiché obnovení výsledku. Kde se stav stroje opravdu změnil (test harnessů), smí tiché obnovení použít `fresh=1`, chip ale drží předchozí stav, dokud nepřijde nový výsledek.
- Při tichém obnovení nemaž `issues` předem, nahraď je až novým výsledkem, aby chip neblikal.
- Velký panel na stránce Problémy (`chip=false`) se chová stejně: při ruční kontrole ukáže „Probíhá kontrola“, při tichém obnovení drží poslední výsledek.
- Uprav testy v `aifactory/web/src/components/OverviewReadiness.test.ts`. Pokud se mění volání v `App.vue`, uprav i `aifactory/web/src/App.test.ts`.
- Statický build dashboardu (`aifactory/src/aifactory/web/static/`) přegeneruj podle zvyklosti repa.

## Mimo rozsah
- Backend: serverová kontrola stroje, její cache a periodické úlohy serveru se nemění.
- Odkaz loga HAIFA (`href="/"`) zůstane beze změny.
- Chip aktualizací, chip knihovny, limity a další chipy.

Hotovo znamená:
- Po načtení stránky (také po kliknutí na logo HAIFA) se chip v topbaru nepřepne na „Probíhá kontrola“, pokud server odpoví z cache rychle. Rovnou se ukáže „Systém v pořádku“ nebo „Nalezeny problémy“. Test ve vitestu to ověřuje.
- Klik na zelený chip a tlačítko „Zkontrolovat znovu“ zavolají `/api/machine/check?fresh=1` a po dobu kontroly ukazují „Probíhá kontrola“. Test to ověřuje.
- Událost `factory-applied` ani uložení a test harnessů nepřepnou chip na „Probíhá kontrola“. Výsledek se potichu obnoví. Test to ověřuje.
- Fokus okna nespouští žádnou kontrolu (stávající test zůstane zelený).
- `just web-test` a build frontendu projdou, statický build v `aifactory/src/aifactory/web/static/` odpovídá zdrojům.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
