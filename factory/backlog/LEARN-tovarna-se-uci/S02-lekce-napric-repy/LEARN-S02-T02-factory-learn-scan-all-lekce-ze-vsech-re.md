---
id: LEARN-S02-T02
title: "factory learn scan --all: lekce ze všech rep s cílovým repem"
status: todo
workflow: plan-build-test
depends_on: [LEARN-S02-T01]
writes: [aifactory/src/aifactory/learn/scan.py, aifactory/src/aifactory/learn/store.py, aifactory/src/aifactory/learn/__init__.py, aifactory/src/aifactory/cli.py, aifactory/src/aifactory/seed/agents/learner/, aifactory/tests/learn/test_learn_scan.py, aifactory/tests/learn/test_learn_store.py, aifactory/tests/learn_fixture.py, aifactory/tests/library/test_library_seed.py]
---

## Zadání
Rozšiř `factory learn scan` o sběr ze všech registrovaných rep. Každá lekce nese cílové repo, kam pravidlo patří.

Co udělat:
- `aifactory/src/aifactory/learn/scan.py`: `scan(repo, since=None, all_repos=False)`. S `all_repos=True` vezme výtky z `sources.collect_all` místo `collect` jednoho repa. Learner pořád běží read-only v izolovaném klonu repa `repo`.
- `ProposedLesson` dostane pole `repo: str`, tedy id cílového repa z registru. Kontext learneru (`context`) dostane `repos`: id, název a příznak `is_factory` každého registrovaného repa. Dál dostane popis pravidla: pravidlo pro konvence a kód konkrétního repa patří do toho repa. Nedostatek factory samotné (chování role nebo agenta, prompt role, který selhává ve více repech) patří do repa s příznakem `is_factory`. Každá výtka v kontextu má `repo`.
- Nový cíl `seed` (prompt role v semínku knihovny, `target_detail` je název role) je povolený jen pro repo factory. Gate v `_ask_learner` vrátí agentovi k opravě neznámé id repa i cíl `seed` mimo repo factory, stejně jako dnes neznámé id výtky.
- Bez `--all` se nic nemění. `repo` je repo, ve kterém scan běží, a výtky mají klíče bez předpony.
- Ukládání: lekce se ukládá do `LessonStore` trace DB **cílového** repa. `learn/store.py` dostane sloupec `origin TEXT NOT NULL DEFAULT ''` s ids rep, odkud výtky pocházejí (migrace `ALTER TABLE` pro starší tabulku jako u `task_id`). Rozhodnuté lekce (`settled`) pro learner i pro filtr `_blocked`/`_repeated` se při `--all` berou ze storů všech registrovaných rep. Opakování přijaté lekce (`add_repeats`) jde do storu repa té lekce.
- Výsledek `scan` a `format_scan` u každé lekce uvádějí cílové repo a počet rep, ze kterých výtky pocházejí.
- CLI (`aifactory/src/aifactory/cli.py`, `_add_learn_commands`): přepínač `--all` u `factory learn scan` a nápověda k němu.
- Semínko learneru: `aifactory/src/aifactory/seed/agents/learner/system.md` a `user.md` popíšou `repos`, pole `repo` a cíl `seed`.
- Testy v `aifactory/tests/learn/test_learn_scan.py` a `aifactory/tests/learn/test_learn_store.py` s falešným harnessem z `learn_fixture.py`: výtky ze dvou rep, lekce mířící do repa factory se uloží do trace DB repa factory, lekce pro repo X do X, `seed` mimo repo factory jde k opravě, scan bez `--all` se chová jako dřív. Uprav i test semínka, pokud kontroluje obsah promptu learneru (`aifactory/tests/library/test_library_seed.py`).

Mimo rozsah: `accept` a `view` (T03) a dashboard (T04).

Hotovo znamená:
- `uv run pytest aifactory/tests/learn/ aifactory/tests/library/test_library_seed.py` projde.
- `factory learn scan --all --json` vrátí lekce s polem `repo` a uloží je do trace DB cílových rep.
- `factory learn scan` bez `--all` dává stejný výsledek jako před změnou.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
