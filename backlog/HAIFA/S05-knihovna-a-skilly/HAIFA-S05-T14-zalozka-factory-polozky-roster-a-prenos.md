---
id: HAIFA-S05-T14
title: "Záložka Factory: položky, roster a přenos mezi repy"
status: done
depends_on: [HAIFA-S05-T13]
---

## Zadání
Doplň na záložku Factory správu položek repa: roster agentů s vazbami, workflow, skilly a rozšíření se stavem proti knihovně a akce přidat, nastavit, exportovat, vrátit, odebrat a kopírovat do jiného repa. Každý zápis jde přes náhled plánu a potvrzení.

Where: `aifactory/web/src/` (`views/`, `components/`, `components/review/DiffView.vue`, `lib/api.ts` a testy), `aifactory/tests/e2e/`, build v `aifactory/src/aifactory/web/static/`.

Done means:
- Tabulka Agenti: slot, položka knihovny se stavem, harness, model a thinking (úprava přímo v řádku přes akci `set`), skilly, rozšíření a writes. Sloupce, které vlastní knihovna (purpose, prompty), jsou označené.
- Tabulky Workflow, Skilly a Rozšíření pi se stavem a u workflow s počtem tasků backlogu, které ho používají.
- Akce řádku: Diff, Aktualizovat, Exportovat (další verze nebo nová položka), Vrátit, Odebrat a Kopírovat do… (u změněné položky export, pak `add` v cílovém repu jako dva plány za sebou).
- Přidat z knihovny…: typ, položka, slot a vazby. Plán ukáže uzávěr závislostí.
- Blokátor (`slot_taken`, `in_use`, `library_changed_since`, `run_in_progress`) zakáže Provést s důvodem a opravou.
- Unit testy (vitest): stavy, úprava vazby, každá akce, kopírování do jiného repa, blokátory. Prohlížečový test přidá skill z knihovny builderovi, commitne ho a ukáže stav `synced`.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: editory promptů a workflow (F4), onboarding (O5), operace ve více repech (L13).

Pevná omezení:
- UI posílá jen volby plánu, cíl, zprávu a digest, nikdy cesty ani obsah souborů.
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow finish-test-review · PR https://github.com/janbkrejci/HAIFA/pull/94 · náklady $0.00
