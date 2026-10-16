# HEAL-S02-T04: Řetěz provede bezpečnou akci sám

## Cíl

Auto-continue řetěz se po selhání běhu nemá zastavit tam, kde je bezpečná akce jasná.
Sám ji provede, zapíše ji do svých událostí a ukáže ji na Přehledu.

## Chování (`run/heal.py`)

Řetěz, který by po tasku pokračoval (`--auto` nebo zděděné `auto_continue: true`), po
selhaném běhu (ne blokovaném) jedná podle `failure_kind`:

- `quota`: běh už sám jednou pokračoval na záložním harnessu (`fallback.continue_on_fallback`
  v `run_task`/`retry_run`, HEAL-S02-T03). Řetěz přepnutí zapíše jako událost a po úspěchu
  zálohy pokračuje. Selže-li i záloha, řetěz se zastaví (`failed`).
- `process_gone`: řetěz běh jednou zopakuje (`retry_run`). Projde-li opakování, pokračuje
  (u `auto_merge` nejdřív merge), jinak se zastaví.
- `nothing_to_do` s důvodem agenta (`failure_detail.summary`, důkaz): řetěz označí task
  v `base` jako hotový bez změn (`unchanged.finish_nothing_to_do`, záznam „bez změn“
  s důvodem) a pokračuje jako po běhu bez změn. Výsledek běhu má `closed_by_heal`,
  `ChainResult.ok` ho počítá jako úspěch. Bez důvodu nechá task na člověku.
- ostatní druhy: beze změny, řetěz se zastaví (`failed`).

Každý běh se opravuje nejvýš jednou. Paralelní řetěz (`max_parallel_runs` > 1) opakuje
běh ve svém procesu, stejně jako první běh `retry_chain`.

## Nastavení `auto_heal`

Dědí se jako `auto_continue` (task, step, projekt; `null` se přeskočí), výchozí `true`.
`auto_heal: false` vypne všechny automatické akce tasku, i přepnutí harnessu u
jednotlivého běhu (varování `quota fallback skipped: auto_heal is off`). Nastaví se
v front matter, `factory backlog edit ID --auto-heal on|off`, `--clear auto_heal` nebo
přes API úpravy kontejneru (`CONTAINER_KEYS`).

## Události

- `task_chains.events` (JSON seznam, starší DB dostanou sloupec při otevření):
  `{at, action: fallback|retry|close, failure_kind, task_id, run_id, ok, text, detail?}`.
- `ChainResult.events` a `data.chain.events` v `--json`.
- Texty: „Factory pokračovala na Claude Code po vyčerpání kvóty Codexu“, „Factory
  zopakovala běh RUN po pádu procesu“ (případně „; opakování selhalo“), „Factory uzavřela
  task ID jako hotový bez změn: důvod“.
- `GET /api/overview`: `auto_actions` u repozitáře, nejnovějších 5 akcí ze 20 posledních
  řetězů, s `chain_id` a `task_title`. Karta repozitáře na Přehledu má sekci
  **Factory zasáhla sama**, každý řádek odkazuje na běh, neúspěšná akce je červeně.
