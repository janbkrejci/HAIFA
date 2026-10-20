# Ochrany tasků v dashboard API

Dashboard před editací tasku, změnou vazeb a spuštěním či uložením návrhu agenta ověřuje aktivní běh přes `TaskRunStore.running(task_id)`. Pokud běh existuje, vrací HTTP 409 s kódem `task_running` a českou zprávou obsahující id tasku a běhu. Odmítnutí platí i pro `status: cancelled` a pro opakované uložení návrhu přes `workflow_advice_id`; soubor tasku ani nové workflow se neuloží. Běh se zastavuje na stránce běhu.

Před spuštěním procesu dashboard používá `run_check`: nesplněné závislosti v base bez dostupného `stack` odmítne HTTP 409 `unmet_dependencies`, včetně požadavku s `force: true`. Otevřené PR závislostí, ze kterých lze složit běh, start bez `force` nadále umožňují. Stejná kontrola se provádí při startu nového follow-upu s `run` po zveřejnění jeho backlogu do base.

Kontroly jsou pouze ve webové vrstvě. Core backlogu, CLI `task run --force`, launcher a frontend se nemění. Tasky čekající na review nebo merge lze dál upravovat, pokud nemají aktivní běh v trace DB.

Regresní pokrytí obsahuje `tests/web/test_web_task_running_guard.py`: odmítnuté zápisy a návrhy, nezměněný obsah tasku, absence nového workflow a volání launcheru, závislosti z base oproti rozpracované editaci a zachování skládaného startu. `tests/web/test_web_task_run.py` ověřuje také skutečný start přes lokální falešný harness a odmítnutí blokovaného tasku s `force`.
