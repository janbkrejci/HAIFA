---
id: HAIFA-S01-T21
title: "Instalace, aktualizace z knihovny a commit konfigurace z dashboardu"
status: done
workflow: finish-test-review
depends_on: [HAIFA-S01-T20, HAIFA-S01-T01, HAIFA-S01-T02, HAIFA-S01-T03, HAIFA-S03-T05]
auto_merge: false
---

## Zadání
Doplň na záložku Factory instalaci factory do repa bez ní, aktualizaci z knihovny a commit konfigurace (D4). Každý zápis jde přes náhled plánu a potvrzení, bez nich se nic nezapíše ani nepushne.

Where: `aifactory/web/src/` (`views/`, `components/`, `components/review/DiffView.vue`, `components/ConfigStatusBanner.vue`, `lib/review.ts`, `lib/api.ts` a testy), `aifactory/tests/e2e/`, build v `aifactory/src/aifactory/web/static/`.

Done means:
- Průvodce přidáním repa bez factory pokračuje instalací: repo se zaregistruje dočasně a Zrušit ho zase odebere a do repa nic nezapíše.
- Formulář instalace je předvyplněný zjištěnými hodnotami: base, git provider (u `azure` organizace, projekt a repo), adresáře backlogu, specs a docs, agenti z `available` (výchozí planner, builder, reviewer a documenter) s harnessem, modelem a thinking u každého agenta (D24, výchozí z položky, harness bez nainstalovaného CLI s varováním) a workflow (výchozí `simple-sdlc`). Každá změna přepočítá plán.
- Plán ukáže každý soubor včetně manifestu s celým obsahem nebo diffem (sdílená komponenta diffu z Review), varování (adresář s cizím obsahem), nálezy stroje (neblokují), blokátory (zakážou Provést s důvodem) a souhrn „1 commit na main (a6f3e1c → nový), push na origin/main“.
- Provést potvrdí vlastní modál („Commitnout N souborů do main a pushnout na origin?“). Odmítnutý push ukáže důvod, „V repozitáři se nic nezměnilo“ a Otevřít jako PR se stejným digestem. Úspěch ukáže commit nebo PR, spustí kontrolu znovu a nabídne Otevřít backlog. U PR připomene, že běhy počkají na merge a Dorovnat base.
- Aktualizace má skupiny Aktualizuje se z knihovny, Ponechá se změna v repu, Změněno v obou (Převzít, Sloučit, když ho plán nabízí, a dva diffy) a Migrace (zaškrtnutí ji provede). Repo bez manifestu ukáže blokátor `not_onboarded`.
- Commitnout konfiguraci na záložce i v banneru necommitnuté konfigurace otevře náhled s diffy a potvrzením. Dorovnat base se ukáže u nálezu zpoždění za remote.
- Dokud v repu běží běh, jsou přímé provedení, zápis a dorovnání zakázané s textem „V repu běží N běhů, počká se, až doběhnou“ a odkazy na běhy. `plan_changed` ukáže nový plán k novému potvrzení.
- Unit testy (vitest): formulář s vazbami po agentech a přepočet, blokátory, modál, odmítnutý push a PR, aktualizace s převzetím a migrací, banner a zákaz během běhu. Prohlížečový test nainstaluje factory do repa bez ní s providerem `local`, holým remote a builderem na jiném harnessu a ověří commit v logu repa i v remote.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: editory agentů a promptů (F4), správa položek (L14), onboarding a převzetí (O5), instalace nástrojů.

Pevná omezení:
- UI posílá jen volby plánu, cíl, zprávu a digest, nikdy cesty ani obsah souborů.
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-07 · workflow finish-test-review · PR https://github.com/janbkrejci/HAIFA/pull/80 · náklady $0.00
