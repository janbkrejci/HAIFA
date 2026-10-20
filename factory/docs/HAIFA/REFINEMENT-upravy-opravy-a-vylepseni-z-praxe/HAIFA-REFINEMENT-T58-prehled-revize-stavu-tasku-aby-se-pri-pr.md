# HAIFA-REFINEMENT-T58: revize přechodů stavů

## Prameny revize

`web/launcher.py` (`RunLauncher._launch`, `running`) uchovává spuštěné procesy
v paměti serveru; API vrací `pending`, když ještě není vidět claim. Přehled ani
`backlog_view(repo)` launcher nedostávají. `run/members.py`
(`ProcessRunner.start`) spouští proces člena řetězu, ale do seznamu členů jej
přidá až po claimu. Trace tedy v této chvíli neobsahuje task běžícího procesu.

`run/task.py` (`_execute`) ukládá `store.finish(SUCCEEDED)` před voláním
`review/publish.py::publish`. Ten nejdřív pushuje, pak vytváří nebo adoptuje PR,
nakonec zapíše `task_prs`. Chyba provideru se ukládá jako `pr_error`.
`run/unchanged.py::finish_unchanged` po úspěchu zapisuje dokončení do backlogu
a commituje base; chyba dokončení také skončí v `pr_error`.

`review/automerge.py` čeká nad otevřeným PR, při chybě nastavuje
`auto_merge_error`; konflikt řeší `resolve_task` a další běh. CI opravy a návrat
z review používají běhy nad existující větví/PR. `review/flow.py::_finish_approve`
zapíše `task_prs.state = merged` před `_catch_up_base`. Ruční merge se nejdřív
promítne přes `review/sync.py::refresh_prs` a `web/pr_refresh.py` do trace.
`backlog/taskfile.py::has_entry` odlišuje historii již dokončeného, znovuotevřeného
tasku od dosud nezapsaného dokončení.

`run/store.py::reclaim` přepne retry na `running` a vyčistí předchozí chyby;
`finish`, stop a reap odstraňují pauzu. Pauza nemění stav `running`.
`all_runs()` provádí reap, proto jej odvození kanbanu již nepoužívá.
Přehled čte proces pouze diagnosticky; zobrazení samotné neukončuje běh.

## Tabulka revize

„Ready“ v tabulce znamená dosud otevřený `todo` s workflow a splněnými závislostmi;
jiné závislosti či přiřazení mohou místo něj dát `blocked`, `human` nebo `todo`.

| Přechod | Dřívější zobrazení | Zobrazení po opravě / vyhodnocení |
| --- | --- | --- |
| Start z dashboardu, proces před claimem (`pending`) | Ready | Předáno navazujícím taskem v reportu: launcher není vstupem těchto čtenářů. Po claimu running. |
| Start člena auto-continue před claimem | Ready | Stejný navazující task: ProcessRunner před claimem nezveřejňuje identitu procesu v trace. |
| Úspěch běhu → push/vytvoření/zápis PR | Ready, task chyběl v seznamech | running v chipech i seznamu; po zápisu PR awaiting merge / in review. |
| Proces skončí po úspěchu před zápisem PR | Ready | running, v seznamu diagnostika procesu; bez uložené chyby nelze bezpečně odlišit nedokončenou publikaci. |
| Úspěšný běh bez změn → označení done | Ready, až 60 s i po dokončení | running → done; změna souboru obnoví cache i bez PR. |
| Publikace nebo dokončení bez změn selže (`pr_error`) | Ready dle backlogu | Beze změny; chyba není předstíraný běh. |
| Čekání na CI, auto-merge nebo předchozí PR ve stacku | awaiting merge / in review | Beze změny, PR zůstává otevřené. |
| Auto-resolve konfliktu / ci-fix nad otevřeným PR | PR stav → running → PR stav | Beze změny; existující PR vyplňuje mezeru před claimem a po úspěchu. |
| Auto-merge skončí s `auto_merge_error` | in review | Beze změny, čeká na uživatele. |
| Automatický merge → catch-up base / pull / cache | Ready | done ihned podle nejnovějšího PR v trace; změna souboru obnoví cache. |
| Ruční merge → refresh trace → backlog sync/pull | PR stav → Ready | PR stav do refresh trace, pak done; žádné volání hostingu při čtení pohledu. |
| Znovuotevření po merge, záznam stejného PR v tasku | Ready | Ready; respektuje has_entry a změnu souboru i před TTL. |
| Retry/pokračování failed nebo aborted před claimem | Ready, případně PR stav | Před claimem bez PR navazující task; po reclaim running. Novější selhání nepřekryje starší úspěch. |
| Pauza a pokračování | running | Beze změny; pause/pausing zůstává v seznamu. |
| Samostatné task publish | Ready při dosavadním pr_error, jinak Ready | Bez pr_error running; při opakované publikaci s uloženou chybou do zápisu PR původní stav, zahrnuto v navazujícím tasku. |
| Samostatné task approve | PR stav, po merge Ready | PR stav → done; approve nemusí zakládat běh. |
| Proces skončil, trace stále running | Přehled Ready; kanban při čtení mohl reapnout na aborted | Oba running s diagnostikou procesu v Přehledu; skutečný reap na aborted vrátí původní stav backlogu. |
| PR uzavřené bez merge | Ready dle backlogu | Beze změny; úspěch na větvi s uzavřeným PR není čekání na první publikaci. |
| Explicitní done/cancelled, i se starými PR/běhy | done/cancelled | Beze změny; seznam running již neskrývá chip uzavřeného tasku jiným stavem. |

## Implementace a ověření

`web/backlog.py::_display_runtime` sdílí pravidla pro oba pohledy.
`board_state` používá nejnovější běh a nejnovější PR, včetně sloučených.
Přehled načítá `branch` a `pr_error` s fallbackem `NULL AS ...` pro staré DB.
Kanban čte stejný read-only trace snapshot, nastavení pořadí fronty čte dosavadním
způsobem. Přehled obnovuje index při změně souborů tasků v předání po úspěchu/merge;
ostatní cache i plánování zůstávají zachované.

Regresní testy jsou v `tests/web/test_web_overview.py` a
`tests/web/test_web_backlog.py`: úspěch bez PR, chyba publikace, failed/aborted,
merge bez změny backlogu, dokončení bez PR, znovuotevření při naplněné cache,
shoda kanbanu s chipy repozitáře i projektu a čtení ukončeného procesu bez reapu.
Stávající testy pokrývají review/automerge, chybu auto-merge, pauzu, starší trace DB
a neměnnost výpočtu kapacity. Frontend ani distribuovaný build se nemění.

### Výsledek širšího ověření na Windows

Testovací krok dokončil lint, typecheck a testy workflow advice úspěšně. Backendové
webové testy skončily výsledkem 541 passed, 10 skipped a 5 failed. Dvě selhání
`test_delete_refuses_a_thread_that_answers` a `test_delete_removes_the_thread_for_good`
způsobuje `web/assistant.py::delete`: obyčejné `shutil.rmtree` nedokáže odstranit
read-only Git objekty pracovního repozitáře vlákna (`WinError 5`, odpověď HTTP 500).
Obě selhání se reprodukovala i se zdrojovým kódem `web/backlog.py` a `web/overview.py`
z `HEAD`, načteným místo změněných modulů pouze do paměti procesu pytest.

Zbývající tři selhání jsou parametrizace
`test_publish_launcher_reports_quick_errors`: při paralelním běhu neobdržely chybu
do výchozího třísekundového limitu launcheru. V cíleném sériovém běhu všechny tři
prošly, a to se změnou T58 i s původními moduly z `HEAD`. Produkční launcher po
vypršení limitu záměrně vrací pending; test musí odlišit tuto větev od ověřování
chybové obálky dokončeného procesu. Tato zjištění jsou předána v reportu s cestami
pro opravu mimo povolené zápisy T58; širší webový gate zatím není zelený.
