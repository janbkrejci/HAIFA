---
id: HAIFA-S06-T05
title: Onboarding a převzetí v dashboardu
status: done
depends_on: [HAIFA-S05-T14]
---

## Zadání
Doplň do dashboardu stav onboardingu repa, jednorázové vytěžení přes náhled plánu a převzetí onboardovaného repa na stroji kolegy. Volby po položkách zůstávají v CLI, dashboard používá výchozí.

Where: `aifactory/web/src/` (`views/`, `components/`, `components/review/DiffView.vue`, `lib/api.ts`, `lib/router.ts` a testy), `aifactory/tests/e2e/`, build v `aifactory/src/aifactory/web/static/`.

Done means:
- Karta repa v průvodci přidáním a záložka Factory ukážou štítek: Bez factory, sssf, HAIFA před knihovnou, Onboardováno (kdo, kdy, z čeho, knihovna), Onboardováno na remote nebo Čeká v PR #n.
- `sssf` a `pre_library` nabídnou Onboarding (jednou pro repo). Repo `sssf` se zaregistruje dočasně jako u instalace a Zrušit ho odebere. Náhled má sekce Knihovna (nové položky a verze), Repozitář (soubory s obsahem) a Zpráva (skupiny podle kódů) a blokátory s opravou: `onboarded_in_remote` nabídne Dorovnat base a pak Převzít, `onboarding_pending` odkaz na PR.
- Provést potvrdí vlastní modál „Commitnout N položek do knihovny <jméno> a pushnout, pak commitnout M souborů do <base> a pushnout na <remote>? adws/ zůstane beze změny.“ Výsledek ukáže commit knihovny a commit nebo PR repa.
- `onboarded`: panel Převzetí. Bez knihovny Naklonovat knihovnu z <remote z manifestu>, chybějící položky Doplnit knihovnu (plán `adopt`), jiná knihovna varování.
- Unit testy (vitest): štítky, náhled se třemi sekcemi, blokátory, modál, převzetí. Prohlížečový test onboarduje fixturu sssf s holými remote a ve druhém `HAIFA_HOME` repo převezme bez nabídky vytěžení.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: volby po položkách (`--keep-local`, `--name`), převod backlogu, smazání `adws/`.

Pevná omezení:
- UI posílá jen volby plánu, cíl, zprávu a digest, nikdy cesty ani obsah souborů.
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/95 · náklady $0.00
