---
id: HAIFA-S03-T03
title: "Adresáře výstupů (specs, docs) po projektech"
status: done
depends_on: [HAIFA-S03-T01]
---

## Zadání
Umožni nastavit adresáře výstupů zvlášť pro projekt (nejvyšší úroveň backlogu) nebo step. Klíče `specs_dir` a `docs_dir` v `index.md` (i v tasku) se dědí jako `workflow` a přebijí hodnoty z `.factory/config.yaml`.

Where: `aifactory/src/aifactory/backlog/model.py`, `aifactory/src/aifactory/backlog/loader.py`, `aifactory/src/aifactory/run/scope.py`, `aifactory/src/aifactory/run/guard.py`, `aifactory/src/aifactory/run/task.py`, testy v `aifactory/tests/run/` a `aifactory/tests/backlog/`.

Done means:
- Spec a dokumentace tasku vzniknou v nejbližším nastaveném `specs_dir` a `docs_dir` (task, step, projekt), jinak v adresářích z `.factory/config.yaml`. Prompt agentů a proměnné `{{spec_path}}` a `{{doc_path}}` nesou tyto cesty.
- Hodnota musí být relativní cesta uvnitř repa. Jinak ji `factory backlog check` hlásí a běh takového tasku skončí chybou před startem.
- Podle rozhodnutí v `docs/decisions.md`: agent smí zapsat dva výstupní soubory svého tasku i mimo své `writes`, pokud jeho `writes` není `[]`. Agent s `writes: []` je zapsat nesmí a ostatní cesty mimo `writes` se dál vrací.
- Testy s falešným harnessem: task v projektu se `specs_dir: docs/M07/specs` zapíše spec tam a běh projde, zápis planneru mimo jeho `writes` a mimo výstupy se vrátí a fáze selže, `factory backlog check` odmítne `../x`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: úprava nastavení z dashboardu, `workdir` po projektech, agenti a modely po projektech.

Pevná omezení:
- `.factory/` se nemění.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/24 · náklady $2.61
