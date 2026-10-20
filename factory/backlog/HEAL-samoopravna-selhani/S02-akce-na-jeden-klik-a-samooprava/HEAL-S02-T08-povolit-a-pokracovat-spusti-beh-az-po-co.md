---
id: HEAL-S02-T08
title: Povolit a pokračovat spustí běh až po commitu backlogu do base
status: todo
workflow: build-test-review
depends_on: [HEAL-S02-T01]
writes: [aifactory/src/aifactory/run/allow_writes.py, aifactory/src/aifactory/web/runs.py, aifactory/src/aifactory/web/app.py, aifactory/src/aifactory/cli.py, aifactory/src/aifactory/skill/codes.py, aifactory/src/aifactory/skill/skill.md, aifactory/tests/run/test_allow_writes.py]
---

## Zadání
Navazuje na HEAL-S02-T01. Když běh skončí jako `writes_violation`, tlačítko „Povolit tyto cesty a pokračovat“ (FailureCard.vue → `POST /api/runs/{id}/allow-writes`) a příkaz `factory task retry --allow-writes` nesmí pustit nový pokus dřív, než je změna writes commitnutá v base. Nový pokus čte backlog z commitu base (`run/retry.py`, `gitops.extract_backlog` na `rc.commit` po `_pull_base`), ne z pracovního stromu hlavního checkoutu.

Co udělat:
- V `aifactory/src/aifactory/run/allow_writes.py` (funkce `allow_writes`) po `commit_backlog` ověřit, že backlog v `refs/heads/<base>` obsahuje u tasku všechny cesty z `plan.allow` v efektivních writes. Načíst ho z commitu base stejně jako retry, třeba přes `gitops.extract_backlog` do dočasného adresáře a `effective_task_writes`. Projít tím musí všechny cesty: přímý commit, výsledek `committed=False` (commit_backlog nic necommitnul) i `base_changes: pr` se sloučeným PR.
- Když base nové writes neobsahuje, vyhodit `TaskRunError` s novým kódem `writes_not_committed`. Zpráva řekne, co chybí a jak pokračovat (commitnout backlog, potom `factory task retry <task>`). Retry se nespustí. Stávající `writes_in_pr` (PR čeká na sloučení) zůstává beze změny.
- Nový kód zaregistrovat stejně jako `writes_in_pr`: `aifactory/src/aifactory/skill/codes.py`, HTTP status 409 v `aifactory/src/aifactory/web/app.py`, popis v `aifactory/src/aifactory/skill/skill.md` a v nápovědě `--allow-writes` v `aifactory/src/aifactory/cli.py`. Aktualizovat docstring modulu `allow_writes.py`.
- `web/runs.py` (`start_allow_writes`) a `cli.py` (`_task_retry`) musí volat `launcher.start_retry` nebo `retry_chain` až po úspěšném návratu `allow_writes`. Dnes to tak je, zachovat to a pokrýt testem.

Tvrdá omezení: nepsat do backlogu ani do `.factory/` jinak než přes existující `edit_task` a `commit_backlog`. Neměnit chování akce u jiných druhů selhání.

Mimo rozsah: frontend (FailureCard už chybu z API zobrazí v `allow-error`), změna `commit_backlog` samotné.

Hotovo znamená:
- Nový test v `aifactory/tests/run/test_allow_writes.py`: když se commit backlogu do base nepovede nebo base nové writes neobsahuje (např. `commit_backlog` podvržený tak, že vrátí `committed=False` bez commitu), `factory task retry --allow-writes --json` skončí chybou `writes_not_committed`, běh zůstane `failed` se stejným `attempt` a žádný agent se znovu nespustí.
- Nový test přes API (`POST /api/runs/{id}/allow-writes`) ověří, že při `writes_not_committed` launcher `start_retry` nezavolá a odpověď má status 409.
- Stávající testy v `test_allow_writes.py` (včetně `writes_in_pr` a úspěšného pokračování) procházejí a v úspěšném případě má nový pokus v base rozšířené writes.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
