---
id: HAIFA-REFINEMENT-T58
title: "Přehled: revize stavů tasku, aby se při přechodech (běží → automerge, merge a další) na chvíli neukázal jako Ready"
status: done
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/web/backlog.py, aifactory/src/aifactory/web/overview.py, aifactory/tests/web/test_web_overview.py, aifactory/tests/web/test_web_backlog.py]
---

## Zadání
## Zadání
Na Přehledu (chipy stavů tasků u repa a u projektů) a v kanbanu Backlogu se task na chvíli zobrazí jako **Ready**. Nahlášené jsou dvě chvíle: když běh doběhne a task přechází do „Čeká na automerge“ (nebo „Čeká na review“), a když je PR sloučené. Nejspíš se to děje i jindy. Úkolem je **systematicky zjistit všechna taková místa** a opravit je tak, aby měl task po celou dobu smysluplný stav. Uživatele to mate, protože to vypadá, že se task znovu spustí.

Stav tasku se počítá ve funkci `board_state` v `aifactory/src/aifactory/web/backlog.py` z `_Runtime`: `running` jsou běhy ve stavu `running` a `in_review` jsou tasky s nejnovějším otevřeným PR. Když task nemá ani jedno a jeho status je `todo` bez nesplněných závislostí, vrátí `ready`. Přehled (`aifactory/src/aifactory/web/overview.py`, `_task_summary`) skládá `_Runtime` sám z trace DB (`_active_runs`, `_newest_open_prs`). Kanban ho bere z `_runtime(repo)`. Každá chvíle, kdy task nemá řádek `running` ani otevřené PR, ale ještě se s ním něco děje nebo je už hotový, se tedy ukáže jako `ready`.

### 1. Revize
Projdi celý životní cyklus tasku a pro každý přechod zjisti, jaký stav Přehled a kanban v mezičase ukážou. Čti kód zápisu do trace DB (`task_runs`, `task_prs`), spouštění běhů a řetězu, publikace, auto-merge a označení tasku jako hotového. Projdi aspoň tyto přechody:
- spuštění tasku z dashboardu a z auto-continue řetězu: proces běží, ale řádek v `task_runs` ještě nevznikl (`RunLauncher`, stav `pending`);
- konec úspěšného běhu, než vznikne PR. Funkce `run_task` (modul `aifactory.run.task`) nejdřív zapíše `store.finish(..., SUCCEEDED, ...)` a teprve potom `publish()` pushne větev a založí PR. Totéž platí, když proces skončí dřív, než se PR zapíše;
- úspěšný běh bez změn (`finish_unchanged`), než se task označí jako hotový;
- čekání na CI a auto-merge, auto-resolve konfliktu a ci-fix nad otevřeným PR;
- merge PR (automaticky i ručně), než se status `done` dostane do backlogu, který Přehled čte. Index tasků se drží v cache `TASKS_TTL = 60` s (`_task_index`) a stav do pracovního checkoutu přichází se zpožděním (commit do base / pull);
- retry a pokračování selhaného nebo zastaveného běhu, pauza a pokračování běhu, `task publish` a `task approve` spuštěné jako samostatný proces;
- běh, jehož proces skončil, ale řádek je pořád `running`: Přehled ho vyřadí (`_active_runs`), kanban ne, takže se oba pohledy rozcházejí.

U každého přechodu rozhodni, jestli je mezistav chybný, a pokud ano, jaký stav má task mít. Další místa, která najdeš, přidej do revize.

### 2. Oprava
- Chybné mezistavy oprav v odvození stavu (`_Runtime`, `board_state`, `_runtime`, `_task_summary`, `_read_trace`). Kanban a Přehled musí dávat stejný stav. Logiku sdílej, neduplikuj. Pokud trace view Přehledu nečte potřebné sloupce, doplň je; pozor na starší trace DB bez sloupců (vzor `"... if ... in columns else NULL AS ..."`).
- Úspěšný běh, který ještě nemá PR ani chybu publikace (`pr_error`), zůstane `running`. Spuštěný a ještě nezapsaný běh se nesmí ukázat jako `ready`, pokud to jde poznat z dat, která dashboard má.
- Task, jehož nejnovější PR je `merged` a jehož status v backlogu ještě není `done`/`cancelled`, nesmí být `ready`. Ukaž ho jako `done`, pokud nejde o task znovu otevřený po merge. Rozpoznání znovuotevření převezmi z `_merged_outside` (`has_entry(text, pr["url"])`). Přehled po merge nesmí čekat na vypršení 60s cache.
- Nové stavy kanbanu nezaváděj, použij stávající `BOARD_STATES`. Kde volíš jiný stav, než navrhuje toto zadání, zdůvodni to v popisu PR.
- Seznamy Přehledu (`running`, `automerge`, `review`) ať jsou s chipy konzistentní, pokud to jde bez velkého zásahu. Task nesmí z Přehledu v mezičase úplně zmizet.
- Kapacitu (`Slots`, `free_slots`, `ready`, `can_start`) a výběr dalšího tasku v auto-continue neměň, pokud to oprava přímo nevyžaduje. Řešíme zobrazení.
- Nalezené místo, které nejde opravit v rámci `writes` (např. vyžaduje změnu pořadí zápisů v běhu nebo launcheru), popiš v revizi a nahlas jako follow-up.

Mimo rozsah: frontend dashboardu a jeho statický build. Chipy už stav z API jen zobrazují.

Hotovo znamená:
- V popisu PR je tabulka revize: přechod, stav, který se dřív ukazoval, stav po opravě (nebo odkaz na follow-up). Obsahuje aspoň všechny přechody vyjmenované výše.
- Pro každý opravený mezistav je test v `aifactory/tests/web/test_web_overview.py` (Přehled: `tasks` repa i projektu) a odpovídající test v `aifactory/tests/web/test_web_backlog.py` (kanban: `board_state` / `backlog_view`). Mezi testy jsou aspoň tyto: úspěšný běh bez záznamu v `task_prs` je `running`, ne `ready`; task se statusem `todo` a nejnovějším PR `merged` není `ready`, ani při naplněné cache tasků; znovu otevřený task (záznam PR v souboru tasku) zůstává `ready`.
- Test, že Přehled a kanban dávají pro stejná data stejný stav, včetně běhu, jehož proces skončil.
- Task s během, který selhal, nebo s chybou publikace (`pr_error`) se zobrazuje stejně jako dosud. Stávající testy v `aifactory/tests/web/` procházejí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-20 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/126 · náklady $0.00
