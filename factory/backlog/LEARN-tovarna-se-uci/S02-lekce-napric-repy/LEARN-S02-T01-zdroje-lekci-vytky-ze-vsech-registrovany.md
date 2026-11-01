---
id: LEARN-S02-T01
title: "Zdroje lekcí: výtky ze všech registrovaných rep a repo factory"
status: todo
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/learn/sources.py, aifactory/src/aifactory/learn/collect.py, aifactory/tests/learn/test_learn_sources.py, aifactory/tests/learn_fixture.py]
---

## Zadání
Přidej modul `aifactory/src/aifactory/learn/sources.py`. Z něj budou `factory learn` číst výtky ze všech rep, která dashboard zná, a poznají, které repo je factory samotná.

Co udělat:
- `registered_repos(home=None)`: seznam rep z registru dashboardu (`aifactory.web.registry.Registry(haifa_home()).snapshot()`), tedy id, název a cesta. Repo, jehož cesta už neexistuje nebo nemá trace DB, přeskoč a vrať pro něj varování. Pád celého volání kvůli jednomu repu nesmí nastat.
- `factory_repo(home=None)`: registrované repo, které je zdrojákem HAIFA. Pořadí: proměnná prostředí `HAIFA_FACTORY_REPO` (id z registru), jinak registrované repo, jehož podadresář `aifactory` obsahuje Python projekt s názvem `aifactory` (název projektu v jeho pyproject). Když takové repo není, vrať `None`.
- `collect_all(since=None, home=None)`: výtky (`learn.collect.collect`) z trace DB každého registrovaného repa (`load_local(repo).trace_db_path(repo)`). V `learn/collect.py` dostane `Objection` pole `repo: str = ""` (id repa z registru) a `to_json` ho vrací. V `collect_all` má klíč výtky předponu `<repo_id>:` (`<repo_id>:<envelope_id>#<n>`), takže je v rámci všech rep jednoznačný. Stávající `collect(db, since)` vrací klíče beze změny (zpětná kompatibilita s uloženými lekcemi).
- `resolve_objections(keys, origin_repo, home=None)`: k seznamu klíčů vrátí výtky. Klíč bez předpony patří do `origin_repo`, klíč s předponou do repa z registru. Neznámé repo nebo klíč tiše vynech.
- Testy v `aifactory/tests/learn/test_learn_sources.py`: dvě registrovaná repa v dočasném `HAIFA_HOME` (rozšiř `aifactory/tests/learn_fixture.py` o pomocníka pro registr s více repy), detekce repa factory podle názvu projektu i podle `HAIFA_FACTORY_REPO`, předpony klíčů, přeskočené repo s varováním a `resolve_objections` pro klíče s předponou i bez ní.

Mimo rozsah: scan, accept, dashboard a dokumentace (další tasky stepu).

Hotovo znamená:
- `uv run pytest aifactory/tests/learn/test_learn_sources.py aifactory/tests/learn/test_learn_scan.py aifactory/tests/learn/test_learn_store.py` projde.
- `collect_all` vrací výtky ze všech registrovaných rep s polem `repo` a klíči `<repo_id>:...`.
- `factory_repo` najde repo HAIFA mezi registrovanými repy, případně ho určí `HAIFA_FACTORY_REPO`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
