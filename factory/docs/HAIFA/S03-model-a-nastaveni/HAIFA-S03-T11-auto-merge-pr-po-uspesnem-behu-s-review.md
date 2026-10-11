# HAIFA-S03-T11: Auto-merge PR po úspěšném běhu s review

## Co se změnilo a proč

Přibyl dědičný klíč `auto_merge` (`true`/`false`). Když je zapnutý, factory po běhu
sama schválí a sloučí PR tasku stejnou cestou jako `factory task approve`, včetně
commitu `status: done`. Děje se to jen tehdy, když jsou splněné všechny podmínky.
Běhy tak můžou pokračovat bez obsluhy. Dřív PR po každém běhu ručně slučoval
orchestrátor.

### Podmínky (`review/automerge.py`, `try_auto_merge`)

Podmínky se kontrolují v tomto pořadí a první nesplněná určí kód důvodu:

| # | Podmínka | Kód, když neplatí |
|---|---|---|
| 1 | běh skončil `succeeded` a otevřel PR | `run_not_succeeded`, `no_pr` |
| 2 | workflow lze načíst a má fázi review (role step s výstupem `ReviewOutput`) | `workflow_unavailable`, `no_review_phase` |
| 3 | poslední review běhu schválilo a nemá blokující ani nesplněné body | `no_review`, `review_rejected`, `review_blocking`, `review_unmet` |
| 4 | PR je otevřený a jde sloučit bez konfliktu | `status_unavailable`, `pr_not_open`, `conflict`, `mergeability_unknown` |
| 5 | žádný check v hostingu není červený (pending a „žádné checky“ merge neblokují) | `checks_unavailable`, `checks_failing` |
| 6 | samotný `approve_task` uspěl | kód z `ReviewError`, nebo `merge_failed` |

Workflow bez fáze review se automaticky nesloučí nikdy. Když některá podmínka neplatí,
PR zůstane otevřený. Do `task_prs.auto_merge_error` se uloží `"<code>: <reason>"`
a `try_auto_merge` kvůli tomu nevyhazuje výjimku.

### Dědění a zápis

- `backlog/model.py`: `auto_merge` je přidaný do `INHERITED_KEYS`. Nové `FLAG_KEYS`
  (`auto_continue`, `auto_merge`) jsou klíče, které musí mít hodnotu bool. Validuje je
  `backlog/loader.py`, který hlásí chybu `field '<key>' must be true or false`.
- `backlog/edit.py`: přibyla funkce `set_auto_merge`, která sdílí `_set_container_flag`
  se `set_auto_continue`. `edit_task` dostal parametry `auto_merge` a `clear_auto_merge`;
  oba najednou zadat nelze (`conflicting_options`).
- `run/queue.py`: přibyla funkce `auto_merge_enabled(task)`, která čte efektivní hodnotu
  přes hierarchii projekt → step → task.

### Auto-continue po merge (`run/queue.py`, `run_chain`)

Když má dokončený task `auto_merge` zapnutý, `run_chain` nejdřív zavolá `try_auto_merge`.
Pokud PR sloučit nejde, řetěz skončí s novým stop důvodem `not_merged` (`STOP_NOT_MERGED`).
Když by řetěz stejně nepokračoval, skončí s `disabled`. Po úspěšném merge se backlog
znovu načte z base, takže další task vychází z base, která už obsahuje předchozí změnu.
Výsledek merge je v `TaskRunResult.auto_merge` (`run/task.py`).

### Kdo PR sloučil

- `run/store.py`: tabulka `task_prs` má nové sloupce `merged_by` (`auto-merge` nebo
  `operator`) a `auto_merge_error`. Když store otevře starší trace DB, sloupce do ní
  doplní přes `_add_columns`.
- `review/flow.py`: `approve_task(..., merged_by=...)` zapisuje `merged_by` a při merge
  maže `auto_merge_error`. `ApproveResult` hodnotu `merged_by` vrací. Ruční approve
  zapisuje `operator`.
- `workflow/interpreter.py`: `WorkflowRun.history` uchovává obálky v pořadí, v jakém
  vznikly. Podle ní `last_review` najde nejnovější review.

### Checky v hostingu (`providers/`)

- `providers/base.py`: přibyly `ChecksStatus` a konstanty `CHECKS_PASSING`, `CHECKS_PENDING`,
  `CHECKS_FAILING` a `CHECKS_NONE`. Výchozí `GitProvider.checks()` vrací `none`.
- `providers/github.py`: `checks()` volá `gh pr checks ID --json name,bucket`. Bucket
  `fail` nebo `cancel` znamená `failing` a vrátí jména červených checků. Výstup
  `no checks reported` znamená `none`.

### CLI (`cli.py`)

- `factory backlog auto-merge ID --on|--off|--inherit` nastavuje klíč u projektu nebo
  stepu (zapisuje do pracovního stromu a podporuje `--json`).
- `factory task edit ID --auto-merge on|off|inherit` nastavuje klíč u tasku.
- `factory task run` vypíše buď `auto-merge: merged <url> into <base> (<sha>)`, nebo
  `auto-merge: not merged (<code>): <reason>; the PR stays open, approve it with …`.
  JSON výstup má klíč `auto_merge` (`merged`, `code`, `reason`, `pr_url`, `merge_sha`,
  `merged_by`), a to i u každého běhu v `chain.runs`.
- Nápovědu doplňují `skill/skill.md` (bod 6, Auto-merge) a docstringy v `run/guard.py`
  a `run/mainwrites.py`. Ty teď mezi zápisy factory počítají i `backlog auto-merge`.

### API a dashboard

- `web/app.py` a `web/backlog.py`: přibyl endpoint `POST /api/backlog/containers/{id}/auto-merge`
  (`{mode: on|off|inherit}`). Kontejnery vracejí `auto_merge` a `effective_auto_merge`,
  tasky `own_auto_merge` a `effective_auto_merge`. Úprava tasku přijímá `auto_merge`
  a `clear_auto_merge`.
- `web/runs.py`: `pr` v souhrnu běhu nově obsahuje `merged_by` a `auto_merge_error`.
- Frontend (`aifactory/web/src/`):
  - `AutoContinueToggle.vue` má nové props `label`, `testPrefix` a `hint`. `BacklogView.vue`
    jimi vykreslí přepínač Auto-merge vedle Auto-continue v grafu modulu nebo stepu.
  - `TaskForm.vue` (při editaci) nabízí volbu Auto-merge: zděděné/zapnuto/vypnuto.
    `TaskDetail.vue` ukazuje efektivní hodnotu. `TreeNode.vue` zobrazí odznak „merge“.
  - `ReviewList.vue`, `ReviewDetail.vue` a `RunDetail.vue` ukazují „sloučil auto-merge“,
    případně důvod, proč auto-merge PR nesloučil.
  - Typy a helpery jsou v `lib/backlog.ts` (`setAutoMerge`), `lib/review.ts` (`mergedByAuto`)
    a `lib/runs.ts`.
- Build se znovu vygeneroval: `web/static/index.html` a nové soubory v `web/static/assets/`.

## Jak to použít

```sh
factory backlog auto-merge PROJEKT --on         # projekt
factory backlog auto-merge STEP --inherit        # step zdědí hodnotu projektu
factory task edit TASK --auto-merge off # task, který mění hlídač nebo oprávnění
factory backlog commit -m "Zapnout auto-merge"   # běhy čtou backlog z base
factory task run TASK --auto
```

Když PR sloučit nejde, CLI, `task_prs.auto_merge_error` i dashboard ukážou důvod
a PR počká na `factory task approve`.

## Ověření

- Python testy:
  - `aifactory/tests/backlog/test_backlog_auto_merge.py`: zápis on/off/inherit,
    dědění, `task edit`, CLI a odmítnutí hodnoty, která není bool.
  - `aifactory/tests/review/test_auto_merge_rules.py`: každá podmínka review a hostingu
    zvlášť, `workflow_has_review` a `last_review`.
  - `aifactory/tests/run/test_auto_merge.py`: merge reviewovaného běhu, neúspěšný běh,
    workflow bez review, zamítnuté review, task s vypnutým klíčem, konflikt, řetěz,
    který pokračuje po merge, a řetěz, který se zastaví na `not_merged`, výstup CLI,
    záznam `operator` u ručního approve, falešný `gh` (červené checky, neznámá
    mergeabilita) a migrace sloupců.
  - Testy webu: `aifactory/tests/web/test_web_backlog.py`, `test_web_backlog_graph.py`
    a `test_web_runs.py`.
- Vitest: `AutoContinueToggle.test.ts`, `TaskForm.test.ts`, `ReviewDetail.test.ts`,
  `RunDetail.test.ts`, `lib/backlog.test.ts` a `BacklogView.test.ts`.
- Spustit `just test`, `just typecheck` a `just lint`.
