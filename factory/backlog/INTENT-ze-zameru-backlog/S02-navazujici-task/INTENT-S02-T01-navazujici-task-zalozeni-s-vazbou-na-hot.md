---
id: INTENT-S02-T01
title: "Navazující task: založení s vazbou na hotový task"
status: done
archived: true
depends_on: []
writes: [aifactory/, docs/decisions.md]
---

## Zadání
Hotový task dnes nejde rozvinout. Nový task se zakládá ručně a agenti o původním nic nevědí.

Zadání:
1. Nový klíč front matter tasku (návrh `follows: <task-id>`), validovaný jako odkaz na existující task. Zapsat do `docs/decisions.md`.
2. `factory task follow-up ID --body TEXT [--title TEXT] [--run]` založí task ve stejném stepu jako původní. Nastaví `follows`, převezme vlastní `writes` a `workflow` původního tasku a vloží text do `## Zadání`. Výchozí titulek je „Navazuje na <ID>: <titulek původního>“, dokud ho člověk nezmění. S `--run` backlog commitne a task rovnou spustí.
3. Založit jde jen navazující task na task ve stavu hotovo. Jiný stav se odmítne s jasnou chybou.
4. API pro dashboard se stejným chováním. Detail tasku vrací `follows` a seznam tasků, které na něj navazují.

Hotovo znamená:
- Testy CLI a API: založení, převzetí writes a workflow, odmítnutí nehotového tasku, `--run`.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/91 · náklady $3.76
