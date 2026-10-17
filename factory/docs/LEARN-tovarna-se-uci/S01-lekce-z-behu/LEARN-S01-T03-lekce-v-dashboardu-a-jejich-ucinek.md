# LEARN-S01-T03: Lekce v dashboardu a jejich účinek

Obrazovka Factory repa (`#/r/<repo>/factory`) má sekci **Lekce** (`LessonsSection.vue`) s lekcemi z `factory learn`.

## Sekce Lekce

- **Najít lekce** spustí `factory learn scan` na pozadí (vlákno dashboardu, v jednom repu vždy jen jeden). Sekce se dotazuje, dokud hledání neskončí, a pak ukáže, kolik výtek z kolika běhů prošlo, kolik lekcí vzniklo a kolik výtek se přidalo k přijatým lekcím. Chyba hledání (např. nedostupný harness agenta `learner`) zůstane u tlačítka.
- **Navržená lekce** ukáže pravidlo, kam patří (`AGENTS.md`, `CLAUDE.md`, `skill <jméno>`, `prompt <role>`), počet běhů a výtky s odkazy na běhy a tasky.
  - **Přijmout** je `factory learn accept`: založí task ve stepu `LEARN` projektu a commitne backlog do base. Když z běhů nejde poznat projekt (`project_required`), sekce nabídne výběr projektu.
  - **Zamítnout** je `factory learn dismiss`: lekce se už nenabídne.
- **Přijatá lekce** odkazuje na svůj task a PR. Po merge PR ukáže, v kolika bězích se podobná výtka objevila před merge a po něm. Zamítnuté lekce jsou sbalené na konci.

## Účinek přijaté lekce

Seskupení dělá stejný scan jako u návrhu lekcí. Agent `learner` dostává přijaté lekce v `accepted_lessons` a výtky, které některou opakují, dá do lekce s jejím id v poli `accepted` (nebo se stejným pravidlem či se společnými výtkami). Taková lekce se nenavrhuje znovu; její výtky se přidají k přijaté lekci (`LessonStore.add_repeats`, ve výstupu scanu `repeats`). Počty se proto po merge aktualizují dalším **Najít lekce**.

`learn.view` počítá výtky lekce podle času vzniku vůči `merged_at` prvního sloučeného PR jejího tasku (tabulka `task_prs` v trace DB). Běhy samotného tasku lekce se nepočítají.

## API

- `GET /api/learn` → `{lessons, scan}`. Lekce: `id, rule, target, target_detail, state, reason, task_id, occurrences, runs, complaints, pr, effect`; `effect` je `{merged_at, before: {runs, objections}, after: {runs, objections}}` nebo `null`. `scan` je `{state: running | done | failed, since, started_at, finished_at, result, error}` nebo `null`.
- `POST /api/learn/scan` `{since?}` → scan (202), běžící scan je 409 `busy`.
- `POST /api/learn/lessons/{id}/accept` `{project?}` → výsledek `factory learn accept`; neznámá lekce 404 `unknown_lesson`, neurčený projekt 409 `project_required`.
- `POST /api/learn/lessons/{id}/dismiss` `{reason?}`.

## Testy

- `aifactory/tests/learn/test_learn_view.py`: opakování přijaté lekce ve scanu a počty před a po merge.
- `aifactory/tests/web/test_web_learn.py`: API s fake harnessem.
- `aifactory/web/src/components/factory/LessonsSection.test.ts`: vitest sekce.
- `aifactory/tests/e2e/test_learn_browser.py`: Najít lekce a Přijmout v prohlížeči.
