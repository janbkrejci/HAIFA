# Auto-continue: souběžné běhy s limitem a bez kolize zápisových cest (HAIFA-S03-T16)

## Co se změnilo

Řetěz auto-continue (`run_chain` v `aifactory/src/aifactory/run/queue.py`) dřív spouštěl
tasky jen jeden po druhém. Teď může držet víc běhů naráz. Vybírá přitom tasky tak, aby
nesahaly na cesty běžících běhů ani otevřených PR.

## Konfigurace `max_parallel_runs`

- Klíč je v `.factory/config.yaml` (`ProjectSettings.max_parallel_runs`). Hodnota musí být celé
  číslo ≥ 1, výchozí je 1. Text `"2"`, `0` ani `true` neprojdou validací.
- Jde ho nastavit v dashboardu na obrazovce Nastavení, ve sdíleném fieldsetu jako pole
  „Souběžné běhy auto-continue“. Uložení zapíše `.factory/config.yaml`. Běh čte konfiguraci
  z commitu `base`, takže nová hodnota platí až po commitu do base.
- **`max_parallel_runs: 1`** dává dnešní chování: stejná sekvenční smyčka (`_sequential`),
  žádná kontrola překryvu a žádné podřízené procesy.
- **Hodnota nad 1**: řetěz spustí první task a hned doplní volné sloty dalšími připravenými
  tasky (když platí `--auto` nebo `auto_continue`). Po každém doběhnutém běhu doplní další.

## Pravidlo překryvu (`writes_overlap`)

Kandidát se spustí jen tehdy, když jeho efektivní `writes` (`scope.effective_task_writes`,
bez spec/doc výstupů) se nepřekrývají:

- s `writes` žádného běžícího běhu (`store.live_runs()`, tedy i ručních běhů z dashboardu);
- se soubory žádného otevřeného, nesloučeného PR v repu (`store.open_prs()`), včetně PR
  tasků tohoto řetězu.

Překryv se posuzuje podle prefixu cesty (`scope.paths_overlap`). Z každého vzoru se vezme
literální prefix před prvním wildcardem (`src/**/x.py` → `src`) a porovnává se na hranici
`/`: `src/app` a `src/application` se nepřekrývají, `src/app/` a `src/app/x.py` ano a `**`
se překrývá se vším.

Soubory PR počítá `gitops.pr_changed_files` v hlavním checkoutu jako
`git diff --name-only <merge-base base větev> refs/heads/<větev>`. Když je git nezjistí
(například chybí větev), použijí se `writes` tasku toho PR a detail obsahuje „soubory PR
nelze zjistit“. Když ani task neexistuje, bere se konzervativně celé repo.

Při překryvu řetěz task přeskočí s důvodem `writes_overlap`. Detail říká, který běh nebo PR
a které cesty (`běh <run_id> (<task>): …; PR <url> (<task>): …`, nejvýš 5 cest), a pak zkusí
dalšího kandidáta. Kontrola (`queue.Occupancy`) se volá v `select_next(conflict=…)` až po
všech dosavadních pravidlech (`no_workflow`, `running`, `in_review`, `blocked`,
`waits_on_pr`).

## Široké `writes` (`exclusive`)

Task, jehož `writes` pokrývají celé repo nebo celý balíček (`scope.is_wide`), běží jen
samostatně. Široký je vzor s prázdným literálním prefixem (`**`, `.`) nebo jediný segment,
který je adresářem (`aifactory/`, `src/`, `src/*` nebo existující adresář v kořeni repa).

- Široký task se nespustí, dokud cokoli běží (`exclusive`).
- Dokud široký task běží, nespustí se nic jiného (`exclusive`).
- `ChainResult.exclusive` (v CLI `data.chain.exclusive` a řádek
  `exclusive: <id> ran alone (wide writes)`) a panel v dashboardu uvádějí, které tasky
  běžely samostatně.

**HAIFA dnes dědí `writes: [aifactory/, justfile]`, takže každý HAIFA task je široký a i při
`max_parallel_runs > 1` poběží samostatně.** Je to očekávané chování. Souběh se projeví až
u tasků s užšími `writes`. Automatické zúžení `writes` je mimo rozsah.

## Procesní model

`run_task` nejde spouštět souběžně v jednom procesu, protože dělá `os.chdir` a mění
`os.environ`. Při `max_parallel_runs > 1` proto řetěz spouští každý task jako samostatný
proces (`run/members.py`, `ProcessRunner`):

```
<prefix> task run ID --repo ROOT --json --member
```

- `--member` je interní přepínač. Spustí právě jeden task, nikdy řetěz.
- Když task dědí `auto_merge`, podřízený proces po běhu sám zkusí `try_auto_merge`, protože
  jen on má workflow run s posledním review. Dělá to pod mezi-procesním zámkem
  `<trace db>.merge.lock` (`TaskRunStore.merge_lock()`), takže souběžné merge do base jdou
  jeden po druhém.
- `ProcessRunner.start` čeká, až se běh claimne v `task_runs`, takže další výběr ho už
  vidí. `wait_any` vrátí `TaskRunResult` sestavený z envelope a ze store.
- Neúspěšný běh zastaví doplňování (`stop: failed`). Ostatní běhy se nechají doběhnout,
  nic se nezabíjí. Nesloučený PR s `auto_merge` zastaví doplňování (`not_merged`).
- Parametry `code` a `provider` funkce `run_chain` (pro testy) se do podřízených procesů
  nepředávají. Platí jen pro sekvenční režim.
- Prefix příkazu (`command_prefix`, `set_command_prefix`) a pomocné funkce pro envelope se
  přesunuly z `web/launcher.py` do `run/members.py`. Launcher je reexportuje a jeho API se
  nemění.

## Stav řetězu: `task_chains`, `/api/chains`, panel v Bězích

- Nová tabulka `task_chains` v trace DB (`store.TaskChainRow`) obsahuje `chain_id`, první
  task, pid, `max_parallel`, stav (`running`, `finished`, `aborted`), `stop`, běhy v pořadí
  startu, přeskočené tasky posledního výběru (`Skip.to_json()`) a `exclusive`. Řádek
  `running`, jehož proces už neběží, se při čtení změní na `aborted`.
- Řetěz zapisuje stav při založení, startu, dokončení, výběru a konci. Sekvenční režim
  zapisuje také. Selhání zápisu jen vypíše varování a řetěz neovlivní.
- `GET /api/chains` (`web/chains.py`) vrací `{max_parallel_runs, chains}`. Ke každému řetězu
  dává běhy se stavem, `running`, `free_slots` (jen u běžícího řetězu), `skipped` a
  `exclusive`.
- Na obrazovce Běhy je nad seznamem panel `ChainPanel`. Ukazuje hlavičku „Řetěz od … ·
  běží/skončil: …“, sloty „Sloty: běžící/max (volné N)“, běhy s odkazem, „Samostatně: …“ a
  přeskočené tasky se štítkem důvodu (`překryv writes`, `jen samostatně`, …) a detailem.
  Chyba načtení řetězů seznam běhů nerozbije.

## Ověření

- `aifactory/tests/run/test_scope_overlap.py`: prefixy, překryv, `is_wide`.
- `aifactory/tests/run/test_parallel_chain.py` (fake runner, bez modelu a sítě):
  - limit souběhu;
  - doplnění po doběhnutí;
  - přeskočení při překryvu s během a s otevřeným PR;
  - fallback na neznámé soubory PR;
  - široké `writes`;
  - selhání a `not_merged`;
  - `cannot_start`;
  - čtení `max_parallel_runs` z konfigurace;
  - `max_parallel_runs: 1` jako dnes;
  - `select_next(conflict=…)`.
- `aifactory/tests/run/test_chain_parts.py`: `task_chains`, `pr_changed_files`, envelope a
  `member_result`, CLI `--member`.
- `aifactory/tests/web/test_web_chains.py`, `test_web_settings.py` a
  `tests/config/test_config_settings.py`.
- Frontend: `lib/chains.test.ts`, `components/runs/ChainPanel.test.ts`, testy Nastavení a
  RunsView.

Spuštění kontrol: `just test`, `just typecheck`, `just lint`.

## Soubory

- Backend: `run/queue.py` (`Occupancy`, `run_chain`, `_sequential`, `_ChainRecord`),
  `run/scope.py` (`literal_prefix`, `paths_overlap`, `overlaps`, `is_wide`),
  `run/members.py` (nový: `ProcessRunner`, `member_result`, prefix příkazu),
  `run/store.py` (`task_chains`, `merge_lock`), `run/gitops.py` (`pr_changed_files`),
  `run/__init__.py`, `review/automerge.py` (`AutoMergeResult.from_json`), `cli.py`
  (`--member`, výpis řetězu), `config/settings.py` (`max_parallel_runs`), `skill/skill.md`.
- Web API: `web/chains.py` (nový), `web/app.py`, `web/launcher.py`, `web/settings.py`.
- Frontend: `web/src/lib/chains.ts`, `components/runs/ChainPanel.vue`, `views/RunsView.vue`,
  `components/settings/SettingsForm.vue`, `lib/settings.ts` a přebuildovaný
  `web/static/` bundle.
