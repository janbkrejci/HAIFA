---
id: HAIFA-S03-T02
title: "Úroveň module přejmenovaná na project (core, CLI, skill)"
status: done
depends_on: []
---

## Zadání
Přejmenuj úroveň backlogu module na project. Step a task zůstávají (rozhodnutí v `docs/decisions.md`: project → step → task). Kód projektu zůstává libovolný a krátký, třeba `M01` nebo `HAIFA`.

Where: `aifactory/src/aifactory/config/settings.py`, `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/backlog/` (`render.py`, `edit.py`, `model.py`), `aifactory/src/aifactory/run/queue.py`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), `aifactory/validation/template/.factory/config.yaml.tmpl`, testy v `aifactory/tests/`.

Done means:
- Výchozí `levels` je `[project, step, task]`. Repo s explicitním `levels: [module, step, task]` funguje dál beze změny.
- `factory backlog list` a `factory task list` filtrují projekt volbou `--project` místo `--module`, JSON vrací `filters.project` a neznámý projekt vrací kód `unknown_project`.
- Help a texty CLI mluví o projektu místo modulu. Chybové hlášky o projektu nebo stepu používají jméno úrovně z `levels`.
- `factory --skill` popisuje strom project → step → task v textu i v příkladech. V postupu převodu plánu se modul z plánu stane projektem.
- Šablona validace má `levels: [project, step, task]`.
- Testy: výchozí úrovně, volba `--project`, kód `unknown_project` a repo se starým `levels: [module, step, task]`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: API a obrazovky dashboardu (samostatný úkol), zakládání projektů a stepů, změna `levels` v `.factory/config.yaml` repa HAIFA (udělá engineer ručně).

Pevná omezení:
- Slovo phase dál znamená jen fázi běhu (tabulka `phases`, `phase_id`, API běhů). Backlog ho nepoužívá.
- `.factory/` a `docs/product-brief.md` se nemění.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-02 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/6 · náklady $2.19
