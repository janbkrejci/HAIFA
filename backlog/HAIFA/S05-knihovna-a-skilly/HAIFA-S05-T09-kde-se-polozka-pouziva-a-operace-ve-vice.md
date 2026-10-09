---
id: HAIFA-S05-T09
title: Kde se položka používá a operace ve více repech
status: done
depends_on: [HAIFA-S01-T14, HAIFA-S01-T13]
---

## Zadání
Přidej přehled, která registrovaná repa položku knihovny používají a v jakém stavu, a přidání nebo aktualizaci položky ve více repech s náhledem. Tím jsou skilly, agenti a workflow spravovatelní přes všechna repa (rozhodnutí 4 a 5). Každé repo dostane vlastní plán a výsledek, protože zápis do více rep nemá transakci (R31).

Where: `aifactory/src/aifactory/cli.py`, registr z M3 v `aifactory/src/aifactory/web/`, `aifactory/src/aifactory/library/` (z L4 a L7), aktualizace z M9, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/library/`.

Done means:
- `factory library where TYP JMÉNO --json` vrátí registrovaná repa, která položku používají: repo, slot, stav a verze. Chybějící složku hlásí `repo_missing` a pokračuje.
- `factory update --repos all|ID,ID [--item TYP/JMÉNO]… [--dry-run | --commit [--pr] [-m TEXT]] --json` a `factory config add TYP JMÉNO [--agent A] --repos all|ID,ID …` vrátí plán pro každé repo a provedou je po jednom. `--commit` přijme `--expect ID=DIGEST` pro každé repo a repo s jiným digestem přeskočí s `plan_changed`.
- Výsledek repa je commit, PR, blokátor (`run_in_progress`, `dirty_paths`, ...) nebo chyba. Zablokované repo se přeskočí s důvodem a ostatní pokračují. Opakované spuštění je idempotentní.
- Bez registru vrátí `--repos` chybu `registry_missing`.
- `factory --skill` popisuje operace ve více repech. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) se třemi repy a holými remote: where se stavy, přidání skillu builderovi ve všech repech, aktualizace s jedním repem s živým během a jedním odmítnutým push, `--expect`, opakování, chybějící složka.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: repa mimo registr, souběžné zápisy do více rep, dashboard.

Pevná omezení:
- Repa se zapisují po jednom a každé přes vlastní plán s digestem.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-07 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/82 · náklady $0.00
