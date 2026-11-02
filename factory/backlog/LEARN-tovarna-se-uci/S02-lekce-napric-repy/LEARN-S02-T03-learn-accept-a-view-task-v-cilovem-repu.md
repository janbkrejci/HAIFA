---
id: LEARN-S02-T03
title: "learn accept a view: task v cílovém repu s důkazy z běhů jiných rep"
status: done
archived: true
workflow: build-test-review
depends_on: [LEARN-S02-T02]
writes: [aifactory/src/aifactory/learn/accept.py, aifactory/src/aifactory/learn/view.py, aifactory/tests/learn/test_learn_accept.py, aifactory/tests/learn/test_learn_view.py, aifactory/tests/learn_fixture.py]
---

## Zadání
Lekce uložená v cílovém repu (T02) se přijme a zobrazí správně i tehdy, když její výtky pocházejí z běhů jiných rep.

Co udělat:
- `aifactory/src/aifactory/learn/accept.py`: výtky lekce čti přes `sources.resolve_objections(lesson.complaints, repo)` místo `collect(db)`. Klíče s předponou se dohledají v trace DB svého repa. Task se zakládá v backlogu repa, ve kterém lekce je (cílové repo), tak jako dnes. Projekt LEARN stepu se z tasků z cizích rep určit nedá: tasky jiného repa při počítání projektu (`_project`) ignoruj a `related` naplň jen tasky, které v cílovém backlogu existují. Když projekt zůstane neurčený, platí stávající `project_required`.
- Důkazy v těle tasku (`_evidence`) uvádějí u každé výtky i repo, ze kterého pochází (např. ``- repo `x`, běh `…`, task `…` (review): …``).
- Cíl `seed`: `target_writes` vrátí `aifactory/src/aifactory/seed/agents/<role>/` a `_where` text „promptu role <role> v semínku knihovny“. Tělo tasku připomene, že po merge se změna do knihovny dostane přes `factory library seed` nebo novou verzi.
- `aifactory/src/aifactory/learn/view.py`: výtky lekce a počty `effect` (před a po merge PR) čti přes `resolve_objections`, takže započítají i běhy jiných rep. PR tasku se dál hledá v trace DB cílového repa. Výstup lekce dostane `origin` (seznam rep výtek) a u každé výtky `repo`.
- Testy v `aifactory/tests/learn/test_learn_accept.py` a `aifactory/tests/learn/test_learn_view.py`: lekce s výtkami ze dvou rep se přijme v repu factory, task má důkazy s repem a writes podle cíle (včetně `seed`), opakované přijetí nezaloží nový task, `effect` počítá běhy z obou rep. Stávající testy jednoho repa projdou beze změny chování.

Mimo rozsah: dashboard (T04) a dokumentace (T05).

Hotovo znamená:
- `uv run pytest aifactory/tests/learn/` projde.
- `factory learn accept ID` v repu factory založí task, jehož důkazy uvádějí i běhy z jiných rep.
- U lekce s cílem `seed` má task writes `aifactory/src/aifactory/seed/agents/<role>/`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-01 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/193 · náklady $1.57
