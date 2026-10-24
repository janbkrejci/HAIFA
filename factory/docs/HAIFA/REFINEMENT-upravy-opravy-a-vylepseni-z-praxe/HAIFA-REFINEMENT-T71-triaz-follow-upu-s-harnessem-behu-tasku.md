# HAIFA-REFINEMENT-T71: Binding triageru a learneru

Triager follow-upů dostává ID zdrojového tasku a binding z poznámky aktuálního běhu (`TaskRunRow.note`, parser `_note_override`). Po přepnutí harnessu kvůli kvótě tak použije nový harness, model i thinking uložené retry mechanismem. Binding se aplikuje přes `apply_agents_override` před přípravou konfigurace a výběrem triageru.

Pokud uložený binding chybí, triager použije `context_binding(harness_values(task))` z T69, tedy dědičnost projektu, stepu a tasku doplněnou nastavením počítače. Zdrojový task může být již dokončený. Neznámé ID vyvolá `TriageUnavailable`; volající zachová dosavadní fallback na nové follow-upy. Explicitní prázdný binding i samostatné volání bez taskového kontextu zachovají roster. Krátké návraty bez follow-upů nebo bez todo kandidátů zůstávají zachované.

Learner pracuje nad celým repozitářem a před výběrem agenta aplikuje `effective_override({}, None)`. Výchozí harness, model a thinking počítače tak přepíší roster; bez nastavení počítače se použije roster. Oba pomocníci si zachovávají izolovaný běh a zákaz zápisu.

## Ověření

- Regresní testy s fake harnessy zachycují skutečné požadavky a ověřují model i thinking, explicitní binding, odvození z tasku i počítače, prázdný binding, neznámý task a předání aktuální note po přepnutí harnessu.
- `just pytest tests/run/test_triage.py tests/run/test_followups_triage.py tests/learn/test_learn_scan.py`: 126 prošlo.
- `just pytest tests/run/test_task_run.py tests/run/test_task_retry.py tests/run/test_quota_fallback.py tests/run/test_quota_chain.py`: 77 prošlo.
- `MYPYPATH=tests:tests/workflow uv run mypy` s explicitním seznamem šesti změněných Python souborů (z `aifactory/`): prošlo bez chyb. Cesty zpřístupňují sdílené testovací helpery při cílené kontrole.
- Ruff lint a kontrola formátování všech šesti změněných Python souborů: prošly.
- Po rebase byly oba stuby triageru v testech fronty upraveny pro keyword argumenty `task_id` a `binding`; aserce rozhodnutí a pořadí fronty zůstaly zachované. `HAIFA_HOME="$PWD/.factory/data/t71-queue-check-home" just pytest tests/run/test_followups_queue.py`: 8 prošlo. Oddělený home zabránil kolizi kontroly izolace se souběžným zápisem jiného procesu do reálného HAIFA home, který způsobil chybu při úklidu prvního cíleného běhu.
- Ruff lint, kontrola formátování a `MYPYPATH=tests:tests/workflow uv run mypy tests/run/test_followups_queue.py` (z `aifactory/`): prošly.

Testy nepoužívají živé modely ani služby. Změna v `task.py` obsahuje pouze nezbytný import parseru a předání kontextu do `ask_triager`.
