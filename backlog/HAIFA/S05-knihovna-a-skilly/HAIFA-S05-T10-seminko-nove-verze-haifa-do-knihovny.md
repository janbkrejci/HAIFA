---
id: HAIFA-S05-T10
title: Semínko nové verze HAIFA do knihovny
status: done
depends_on: [HAIFA-S05-T06]
---

## Zadání
Přidej příkaz, který po upgradu HAIFA převezme do knihovny nové verze položek ze semínka. Položka, kterou tým od posledního semínka nezměnil, se nahradí. Upravená zůstane a plán ukáže diff.

Where: `aifactory/src/aifactory/library/` (z L1 až L3), `aifactory/src/aifactory/seed/` (z L1), `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/library/`.

Done means:
- `factory library seed [--dry-run] [--take TYP/JMÉNO]… --json` porovná každou položku semínka s knihovnou. Chybí v knihovně: přidá se. Hlava knihovny se rovná verzi zapsané v `seed` v `library.yaml`: nahradí se novou verzí semínka. Hlava je jiná (změna týmu): zůstane, plán ukáže diff a `--take` převezme semínko. `seed` v `library.yaml` se obnoví.
- Zápis jde cestou knihovny z L3 (fetch, commit, push).
- `factory library status` hlásí `seed_update_available`, když nainstalované semínko má jiné verze než `seed` v knihovně.
- `factory --skill` popisuje postup po upgradu HAIFA (`factory library seed`, pak `factory update` v repech). Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) s náhradním semínkem v dočasné složce: přidaná položka, nahrazená položka, položka změněná týmem s `--take` i bez něj, druhé spuštění beze změn.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: aktualizace rep, mazání položek, které semínko už nemá, dashboard.

Pevná omezení:
- Změna týmu se bez `--take` nepřepíše.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/53 · náklady $2.01
