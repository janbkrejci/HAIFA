# HAIFA-REFINEMENT-T33: Přehled ukazuje v review PR sloučené mimo factory

## Co se změnilo a proč

PR tasku sloučený mimo factory (`gh pr merge`, web GitHubu, Azure) zůstával v `task_prs` ve stavu `open`, dokud někdo ručně nespustil `factory backlog sync`. Přehled, kanban (`in_review`) i fronta čtou jen `task_prs`, takže task dál „čekal na review“.

Teď:

1. **Obnova na pozadí.** Dashboard obnovuje stav otevřených task PR a sync PR od providera každých `PR_REFRESH_INTERVAL` = 120 s. Kanban a fronta tedy dostanou správný stav bez vlastní změny. `GET /api/overview` providera dál nevolá.
2. **Filtr stavů v review.** Review na Přehledu vynechá tasky, které jsou v base `done` nebo `cancelled` (`CLOSED_STATUSES`), stejně jako seznam `failed`. Platí to i pro PR, který je v trace pořád `open`.
3. **Akce „Sloučeno mimo factory“.** Přehled ukáže tasky, jejichž nejnovější PR je `merged`, v base nejsou `done`/`cancelled` a jejich `## Běhy` tento PR ještě neobsahuje. Tlačítko „Otevřít sync PR“ zavolá stávající `sync_backlog`. Když už je sync PR otevřený, karta místo tlačítka ukáže odkaz „Sync PR čeká na merge“. Sync PR se nikdy nezakládá automaticky.

Bod 4 zadání (`merged_at` podle času merge od providera) **hotový není**: `merged_at` se dál zapisuje jako čas syncu (`_now()`). Viz „Co zbývá“.

## Kde to je

- `aifactory/src/aifactory/review/sync.py`: nová funkce `refresh_prs(repo, *, provider=None)`. Volá jen stávající `_refresh_task_prs` a `_refresh_sync_prs`, bez fetch, worktree, commitu i PR. Chyba providera u jednoho PR je warning ve výsledku. Exportuje se z `aifactory/src/aifactory/review/__init__.py`.
- `aifactory/src/aifactory/web/pr_refresh.py` (nový): `refresh_registered(registry, *, refresh=None)` projde registrované repozitáře postupně jeden po druhém. Přeskočí chybějící složku, repo mimo git a repo bez trace DB (trace DB nezakládá). Chyby po repozitářích (`ReviewError`, `TaskRunError`, `ConfigError`, `OSError`, `sqlite3.Error`) převede na warning `"<repo id>: …"` a zaloguje je. Jedno rozbité repo nezastaví ostatní.
- `aifactory/src/aifactory/web/app.py`: v `create_multi_app` přibyla úloha `periodic(refresh_registered, PR_REFRESH_INTERVAL)`, vedle ostatních kontrol na pozadí. Nový endpoint `POST /api/repos/{id}/backlog/sync` spustí `sync_backlog` a vrátí jeho `SyncResult` bez klíče `ok`. `sync_on_base` se mapuje na HTTP 409.
- `aifactory/src/aifactory/web/overview.py`:
  - `TaskIndex` nese `(title, status, path)`.
  - `_closed()` filtruje review i failed.
  - Repo má nové klíče `merged_outside` (`{task_id, task_title, pr_id, url, branch, merged_at}`, nejnovější `merged_at` první) a `sync_pr` (`{url, branch, tasks}` nejnovějšího otevřeného sync PR, jinak `null`).
  - `totals.merged_outside` je nový součet.
  - SELECT z `task_prs` čte `merged_at`, jen když sloupec existuje. `sync_prs` se čte jen pokud tabulka existuje.
- Frontend:
  - `aifactory/web/src/lib/api.ts`: typy `OverviewMergedOutside`, `OverviewSyncPr`, `BacklogSyncResult` a funkce `backlogSync()`.
  - `aifactory/web/src/components/overview/RepoCard.vue`: sekce „Sloučeno mimo factory“ s tlačítkem nebo odkazem na sync PR a s chybovou hláškou.
  - Statický build v `aifactory/src/aifactory/web/static/` je přegenerovaný.

## Jak ověřit

- `just lint`, `just typecheck`.
- `cd aifactory && uv run pytest tests/web/test_web_pr_refresh.py tests/web/test_web_overview.py tests/web/test_web_review.py tests/run/test_backlog_sync.py -n0`:
  - `test_web_pr_refresh.py`: obnovují se jen repozitáře s trace DB a rozbité repo nezastaví ostatní. Test `test_pr_merged_outside_leaves_review_and_kanban` s lokálním providerem ověří, že po obnově task zmizí z review, z počtu `in review` i z kanbanu `in_review` a objeví se v `merged_outside`.
  - `test_web_overview.py`: filtr `done`/`cancelled` v review, podmínky `merged_outside` (novější otevřený PR, PR už zapsaný v `## Běhy`), zobrazení `sync_pr` a nové klíče ve stubu a v totals.
  - `test_backlog_sync.py`: `refresh_prs` zapíše merge a nezaloží větev, commit ani worktree. Chyba providera skončí jako warning.
  - `test_web_review.py`: `POST /api/backlog/sync` otevře sync PR a chyba se mapuje na správný HTTP kód.
- `just web-test`: `RepoCard.test.ts` pokrývá sekci, tlačítko, chybu syncu a odkaz na už otevřený sync PR.
- Ručně: sloučit PR tasku mimo factory a nechat běžet `just dash`. Nejpozději za 2 minuty task zmizí z review a na kartě se objeví „Sloučeno mimo factory“.

## Co zbývá

Čas merge od providera (bod 4) vyžaduje změnu v `providers/`, kam tento task nesměl:

- `PrStatus` nemá čas merge.
- GitHub ani Azure ho nenačítají.

`_record_state` (`review/flow.py`) a `_refresh_sync_prs` proto dál zapisují `merged_at=_now()`. Ve výsledku `merged_at` u merge mimo factory odpovídá okamžiku obnovy, ne skutečnému merge, a tento čas se zobrazuje i v `merged_outside`.
