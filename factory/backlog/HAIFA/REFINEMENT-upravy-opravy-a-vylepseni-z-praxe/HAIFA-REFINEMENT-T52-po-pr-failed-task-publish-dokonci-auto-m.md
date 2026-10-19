---
id: HAIFA-REFINEMENT-T52
title: Po pr_failed task publish dokončí auto-merge a auto-continue
status: todo
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/providers/git.py, aifactory/src/aifactory/review/flow.py, aifactory/src/aifactory/review/automerge.py, aifactory/src/aifactory/run/queue.py, aifactory/src/aifactory/web/runs.py, aifactory/src/aifactory/web/app.py, aifactory/src/aifactory/web/launcher.py, aifactory/src/aifactory/cli.py, aifactory/src/aifactory/skill/skill.md, docs/decisions.md, aifactory/tests/providers/test_push_retry.py, aifactory/tests/run/test_task_publish.py, aifactory/tests/web/test_web_runs.py, aifactory/tests/web/test_web_launcher.py, aifactory/tests/web/thread_launcher.py]
---

## Zadání
Když se na konci `task run` (nebo `task retry`) nepovede push či otevření PR (`pr_failed`), task s `auto_merge: true` se už nikdy sám nesloučí a řetěz auto-continue skončí. Po `factory task publish` je PR otevřený, ale nikdo ho nemerguje, a přitom ho dashboard ukazuje ve sloupci „čeká na automerge“. Operátor nemá důvod nic dělat, takže PR visí, dokud si toho nevšimne.

Výskyt: HAIFA-REFINEMENT-T50, běh 91a29ca3, PR #117. Retry doběhl úspěšně, push na GitHub vrátil `! [remote rejected] factory/HAIFA-REFINEMENT-T50-1 -> factory/HAIFA-REFINEMENT-T50-1 (Internal Server Error)`. Po `factory task publish` stál PR otevřený se zelenou CI a bez `auto_merge_error` a sloučil ho až ruční `factory task approve`.

## Současný stav
- `providers/git.py` `transient_push_error`: `REJECTED_PUSH_ERRORS` obsahuje `[remote rejected]` a má přednost, takže dočasná chyba serveru GitHubu (`remote: Internal Server Error`, `[remote rejected] ... (Internal Server Error)`) se nezopakuje a běh hned skončí `pr_failed`.
- `review/automerge.py` `try_auto_merge`: bez PR vrátí `no_pr` a nic nezapíše. Řetěz v `run/queue.py` (`_run_sequential`, u paralelního `member_auto_merge`) skončí `not_merged`.
- `review/flow.py` `publish_task` / `_publish`: jen pushne a otevře PR. Nevolá auto-merge ani auto-continue, přestože dokumentace říká, že „opakuje konec `task run`“.
- `web/runs.py` `publish_run` (tlačítko na dashboardu) volá `publish_task` synchronně.
- `web/backlog.py` `waits_for_automerge`: „čeká na automerge“ = efektivní `auto_merge` a žádné `auto_merge_error`. Neověřuje, že sloučení opravdu někdo provede. Stejné pravidlo používají `web/overview.py` (`automerge`) a `web/review.py`.
- `run/queue.py` `retry_chain` ukazuje vzor: `run_chain(..., first_run=...)` nahradí první běh a řetěz pak pokračuje auto-merge a auto-continue jako po `task run`.

## Jak se to má chovat
Princip: dočasná chyba hostingu na konci běhu nesmí změnit výsledek. Po `task publish` dopadne task stejně, jako kdyby push napoprvé prošel. Dashboard pak „čeká na automerge“ ukazuje po právu: PR buď slučuje běžící proces, nebo má `auto_merge_error` a čeká na review.

## Co udělat
1. **Dočasné chyby pushe.** `transient_push_error` bere jako dočasnou i chybu serveru hostingu (HTTP 5xx). Patří sem `remote: Internal Server Error`, `[remote rejected] ... (Internal Server Error)`, `502 Bad Gateway`, `503 Service Unavailable` a `500` u `remote rejected`, i když řádek obsahuje `[remote rejected]`. Skutečná odmítnutí (non-fast-forward, práva, chráněná větev, hook, `403`) se dál neopakují.
2. **`task publish` dokončí řetěz.** Publish běžícího tasku s efektivním `auto_merge` po otevření PR provede totéž co konec `task run`: `try_auto_merge` (při konfliktu `resolve_and_merge`), se stejnými podmínkami a stejným zápisem `auto_merge_error`. Po sloučení řetěz pokračuje auto-continue podle stejných pravidel jako po `task run` (efektivní `auto_continue`, pořadí fronty v kanbanu, sloty, `max_parallel_runs`). Implementovat přes `run_chain(..., first_run=...)` jako `retry_chain`, ne druhou kopií logiky. `--auto` u publish není potřeba.
   - Task bez `auto_merge` se chová jako dnes: PR zůstane otevřený pro review.
   - Výstup `factory task publish --json` uvede výsledek auto-merge (`auto_merge`: merged, code, reason, url) a řetězu (spuštěné běhy a `stop`), stejně jako výstup `task run` a `task retry`.
3. **Dashboard publikuje na pozadí.** Publish s auto-merge čeká na CI (desítky minut na GitHubu). `POST /api/runs/{run_id}/publish` ho proto spustí v samostatném procesu přes `web/launcher.py`, stejně jako `start_approve`. Rychlá chyba (`pr_failed`, `pr_exists`, `no_succeeded_run`) se vrátí hned jako dnes.
4. Upravit popis `task publish` v `cli.py` a sekci Publish v `skill/skill.md`, ze kterých se generuje `factory --skill`. Do `docs/decisions.md` doplnit k rozhodnutí o auto-merge, že ho spouští i `task publish`.

## Mimo rozsah
- Proces auto-merge, který spadl během čekání na CI. PR pak zůstane bez `auto_merge_error`. Řeší se samostatně.
- PR otevřené dřív, než task dostal `auto_merge`.
- Automatické opakování `task publish` bez operátora.

## Hotovo znamená:
- Push, který napoprvé vrátí `[remote rejected] ... (Internal Server Error)` a podruhé projde, běh dokončí bez `pr_failed`. Push odmítnutý `[remote rejected] ... (pre-receive hook declined)` nebo non-fast-forward se nezopakuje. Testy v `tests/providers/test_push_retry.py`.
- Po `pr_failed` u tasku s `auto_merge` a schváleným review `factory task publish` PR otevře, sloučí ho (fake gh, zelené checky) a s `auto_continue` spustí další ready task. Bez `auto_merge` PR zůstane otevřený. Při červené CI nebo konfliktu vrátí stejný `auto_merge_error` jako `task run`. Testy v `tests/run/test_task_publish.py`.
- Tlačítko publish na dashboardu u tasku s `auto_merge` vrátí odpověď bez čekání na CI a sloučení proběhne v procesu na pozadí. Test na API a launcher.
- `just lint`, `just typecheck` a pytest dotčených balíčků (`tests/providers`, `tests/run`, `tests/review`, `tests/web`) jsou zelené.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
