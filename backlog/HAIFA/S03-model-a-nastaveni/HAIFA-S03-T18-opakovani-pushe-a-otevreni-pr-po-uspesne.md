---
id: HAIFA-S03-T18
title: Opakování pushe a otevření PR po úspěšném běhu
status: done
workflow: build-test-review
depends_on: []
related: [HAIFA-S03-T15]
writes: [aifactory/src/aifactory/providers/, aifactory/src/aifactory/review/, aifactory/src/aifactory/run/, aifactory/src/aifactory/cli.py, aifactory/src/aifactory/web/, aifactory/web/, aifactory/src/aifactory/skill/, aifactory/tests/]
---

## Zadání
Běh HAIFA-S04-T03 (2ad228cf) skončil succeeded, ale push větve spadl na přechodné síťové chybě (`push_failed: ... RPC failed; curl 16 Error in the HTTP2 framing layer`). PR nevznikl. `pr_error` je jen v obálce běhu v `~/.config/haifa/logs/`, dashboard ukázal success bez PR. Push ani otevření PR nejde zopakovat jinak než ručním voláním `review.publish.publish`.

Where: `aifactory/src/aifactory/providers/git.py`, `providers/github.py`, `review/publish.py`, `run/task.py`, `cli.py`, `web/`, `skill/`, testy v `aifactory/tests/`.

Done means:
- Push větve se při přechodné chybě (síť, HTTP2 framing, `remote end hung up`, timeout) opakuje s pauzou, omezeně (jednotky pokusů). Odmítnutý push (non-fast-forward, práva) se neopakuje.
- Nový příkaz `factory task publish <task-id>` pro poslední succeeded běh tasku bez PR pushne větev a otevře PR stejně jako konec `task run`, včetně záznamu v `task_prs` a těla PR z běhu. Bez succeeded běhu nebo s otevřeným PR vrátí chybový kód, nic nemění.
- Když hosting už má otevřený PR pro větev, ale `task_prs` ho nezná, publish ho převezme (uloží do `task_prs` a aktualizuje tělo) místo zakládání nového.
- Dashboard u succeeded běhu bez PR ukáže `pr_error` a tlačítko pro publish.
- `factory --skill` popisuje `task publish` a jeho kódy.
- Testy proti falešnému `git` a `gh`: přechodná chyba a pak úspěch, odmítnutý push bez opakování, `task publish` po `pr_failed`, převzetí existujícího PR.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: provider Azure DevOps, auto-merge po publish.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-06 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/70 · náklady $5.54
