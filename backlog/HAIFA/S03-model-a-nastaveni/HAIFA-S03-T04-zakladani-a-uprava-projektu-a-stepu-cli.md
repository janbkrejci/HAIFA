---
id: HAIFA-S03-T04
title: "Zakládání a úprava projektu a stepu (CLI, API)"
status: done
depends_on: [HAIFA-S03-T02, HAIFA-S01-T06, HAIFA-S03-T03]
---

## Zadání
Umožni založit projekt a step s libovolným krátkým kódem (třeba `M01`) a stručným názvem a upravit jeho název a nastavení z `index.md`, z CLI i z API dashboardu. Dnes se `index.md` píše ručně.

Where: `aifactory/src/aifactory/backlog/` (`edit.py`, `taskfile.py`, `derived.py`, `__init__.py`), `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/web/backlog.py`, `aifactory/src/aifactory/web/app.py`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/backlog/` a `aifactory/tests/web/`.

Done means:
- `factory backlog add [RODIČ] --id KÓD --title NÁZEV [--body TEXT] --json` založí projekt (bez rodiče) nebo step v projektu: adresář `<kód>-<slug>` s `index.md`. Kód odpovídá vzoru id tasků, je jedinečný a kód stepu začíná kódem projektu a pomlčkou. Neplatný zápis se neprovede a vrátí chyby z validace.
- `factory backlog edit ID --json` změní název a nastaví nebo smaže klíče `workflow`, `writes`, `test`, `source`, `target`, `specs_dir`, `docs_dir` a `auto_continue`. Neznámé klíče v `index.md` zůstanou.
- API dashboardu dělá totéž přes tytéž funkce core. Detail projektu nebo stepu vrací název, popis, vlastní hodnoty a efektivní hodnoty s původem: která úroveň nebo `.factory/config.yaml` hodnotu dává.
- Oba příkazy jsou ve `factory --skill`.
- Testy (pytest) CLI i API nad dočasným repem: neplatný kód, duplicitní kód, step mimo projekt, nastavení a smazání klíče, zachování neznámých klíčů, původ efektivní hodnoty.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: obrazovky dashboardu (samostatný úkol), změna kódu existujícího projektu nebo stepu, mazání projektů a stepů, editace popisu po založení.

Pevná omezení:
- Zápis mění jen soubory backlogu v hlavním checkoutu a nic necommituje.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/43 · náklady $3.42
