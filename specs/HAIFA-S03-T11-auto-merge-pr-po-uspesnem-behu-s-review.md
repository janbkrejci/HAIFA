# HAIFA-S03-T11: Auto-merge PR po úspěšném běhu s review

## Cíl

Nový dědičný klíč `auto_merge` (true/false; projekt → step → task, stejně jako
`auto_continue`). Když platí pro task, který právě doběhl přes `run_chain`
(`factory task run`, i z dashboardu, protože launcher spouští právě `factory task run`),
factory po běhu sama provede totéž co `factory task approve` (commit `status: done`,
push, merge, `task_prs` merged, dorovnání base, úklid worktree), ovšem jen když platí
všechny podmínky. Jinak PR zůstane otevřený a důvod se ukáže v CLI, trace
(`task_prs` v trace DB) i na dashboardu. Auto-continue se zapnutým `auto_merge` předá
další task až po merge.

Mimo rozsah: approve review v hostingu (OB3/D11), Azure DevOps (dostane jen výchozí
implementaci `checks()` z base třídy), auto-merge po `task return` / `task resolve`
(ty jdou dál ručně; v plánu ani v docs to nepřidávat).

Všechny cesty níže jsou relativní k `aifactory/` (kromě `justfile`). `vendor/` a
`prototype/` neměnit. Testy nesmí volat model ani síť (fake harness, fake `gh`,
provider `local`).

---

## 1. Backlog: klíč `auto_merge`

### `src/aifactory/backlog/model.py`
- Do `INHERITED_KEYS` přidat `"auto_merge"` (za `auto_continue`).
- Přidat konstantu `FLAG_KEYS: tuple[str, ...] = ("auto_continue", "auto_merge")`.

### `src/aifactory/backlog/loader.py`
- Validaci zobecnit z `auto_continue` na všechny `FLAG_KEYS`:
  - v `load_container`: `if key in FLAG_KEYS and not _flag(value): self.issue("invalid_field", _flag_message(key), ...)`; `continue`.
  - v `load_task`: pro každý klíč z `FLAG_KEYS` v `own`: když `not _flag(own.get(key))` → issue + `own.pop(key)`.
- `_AUTO_MESSAGE` nahradit funkcí `_flag_message(key) -> f"field '{key}' must be true or false"`
  (text pro `auto_continue` zůstane stejný – existující test na to spoléhá).
- Docstring `_flag` upravit („A valid flag value (`auto_continue`, `auto_merge`)…“).

### `src/aifactory/backlog/derived.py` (nebo tam, kde je `effective`)
- Žádná změna nutná – `effective(task)` dědí všechny `INHERITED_KEYS`.
  Volitelně přidat helper `effective_flag(task, key) -> bool` (`effective(task).get(key) is True`).

### `src/aifactory/backlog/edit.py`
- Zobecnit `set_auto_continue` na interní
  `_set_container_flag(root, container_id, key, enabled, command) -> ContainerWriteResult`
  (tělo dnešní funkce, `key` místo `"auto_continue"`, `command` do `_write_checked`,
  `ContainerWriteResult(action=key, ...)`).
- `set_auto_continue(root, id, enabled)` → `_set_container_flag(..., "auto_continue", ..., "backlog auto-continue")`.
- Nová `set_auto_merge(root, id, enabled)` → `_set_container_flag(..., "auto_merge", ..., "backlog auto-merge")`.
- `edit_task`: nové parametry `auto_merge: bool | None = None`, `clear_auto_merge: bool = False`
  (vzor `workflow`/`clear_workflow`):
  - započítat do kontroly `no_changes`;
  - `auto_merge is not None and clear_auto_merge` → `TaskEditError("conflicting_options", "--auto-merge and inherit are exclusive")`;
  - `auto_merge is not None` → `_apply(text, "set", "auto_merge", auto_merge)`;
    `clear_auto_merge` → `_apply(text, "remove", "auto_merge")`.
  - Ověřit, že `set_field` umí zapsat bool i do task souboru (pro index.md už to funguje).
- Docstring modulu a `edit_task` doplnit.

### `src/aifactory/backlog/__init__.py`
- Exportovat `set_auto_merge` (a `FLAG_KEYS`, případně `effective_flag`).

## 2. Provider: checky v hostingu

### `src/aifactory/providers/base.py`
- Konstanty `CHECKS_PASSING, CHECKS_PENDING, CHECKS_FAILING, CHECKS_NONE = "passing", "pending", "failing", "none"`.
- `@dataclass(frozen=True) class ChecksStatus: state: str; failing: tuple[str, ...] = ()` (názvy červených checků).
- Na `GitProvider` ne-abstraktní metoda
  `def checks(self, pr: PullRequest) -> ChecksStatus: return ChecksStatus(CHECKS_NONE)`
  (local i azure tím mají „žádné checky“).
- Exportovat z `providers/__init__.py`.

### `src/aifactory/providers/github.py`
- `checks(pr)`: `self.gh.json("pr", "checks", pr.id, "--json", "name,bucket")`
  (klíč falešného `gh` je pak `"pr checks"`, nekoliduje s `"pr view"`).
  - Odpověď musí být list dictů; jinak `ProviderError("gh_failed", ...)`.
  - `bucket` ∈ {`fail`, `cancel`} → failing (sbírat `name`); jinak když nějaký `pending` → pending;
    prázdný list → none; jinak passing.
  - `GhError`, jehož stderr obsahuje `no checks reported` → `ChecksStatus(CHECKS_NONE)`.
    Jiná chyba propadne jako `ProviderError` (auto-merge to pak bere jako blokaci, viz níže).
  - Pozn.: s `--json` `gh pr checks` vrací exit 0 i při červených checkách; pro jistotu
    při `GhError` s neprázdným stdout zkusit stdout naparsovat (volitelné, ne nutné).

## 3. Trace: kdo PR sloučil a proč auto-merge nesloučil

### `src/aifactory/run/store.py`
- Do `task_prs` dva nové sloupce: `merged_by TEXT` (`"auto-merge"` | `"operator"` | NULL)
  a `auto_merge_error TEXT` (důvod, proč auto-merge PR nesloučil; NULL jinak).
  - Přidat do `_SCHEMA` (CREATE TABLE pro nové DB) i do `_PR_COLUMNS` a `TaskPrRow`
    (pole s default `None`, na konec).
  - Migrace stávajících DB v `TaskRunStore.__init__` po `executescript`: helper
    `_add_columns(conn, "task_prs", {"merged_by": "TEXT", "auto_merge_error": "TEXT"})`
    přes `PRAGMA table_info`; `ALTER TABLE ... ADD COLUMN` obalit
    `try/except sqlite3.OperationalError` s kontrolou `duplicate column` (souběžné procesy).
  - Konstanty `MERGED_BY_AUTO = "auto-merge"`, `MERGED_BY_OPERATOR = "operator"` (zde nebo v review).
- `TaskPrRow.to_json()` je přes `asdict` → nová pole se objeví automaticky v CLI JSON
  i ve web API (`pr` v review list/detail, backlog task detail). Zkontrolovat testy, které
  porovnávají přesné klíče `TaskPrRow.to_json()` / `pr`, a doplnit je.

## 4. Schválení a auto-merge

### `src/aifactory/review/flow.py`
- `approve_task(repo, task_id, *, provider=None, merged_by: str = MERGED_BY_OPERATOR)`
  → `_approve(ctx, task_id, merged_by)`; při zápisu merge
  `ctx.store.update_pr(branch, state=MERGED, merged_at=_now(), merge_sha=merge_sha, merged_by=merged_by, auto_merge_error=None)`.
- `ApproveResult` + `to_json` rozšířit o `merged_by: str`.
- CLI `task approve` i web approve tím zapisují `operator` bez další změny.

### `src/aifactory/workflow/interpreter.py`
- `WorkflowRun` dostane `history: list[tuple[str, Any]] = field(default_factory=list)`;
  `run_workflow` vyplní `history=list(interp.history)`. (Pořadí potřebujeme pro „poslední review“;
  `envelopes` je dict po klíčích.)

### Nový modul `src/aifactory/review/automerge.py`
Obsah (vše typované, mypy strict):

```python
AUTO_MERGE = MERGED_BY_AUTO  # "auto-merge"

@dataclass
class AutoMergeResult:
    merged: bool
    code: str | None          # důvod blokace / chyby (None když sloučeno)
    reason: str | None        # lidsky čitelný text
    pr_url: str | None
    merge_sha: str | None = None
    approve: ApproveResult | None = None
    def to_json(self) -> dict[str, object]: {"merged", "code", "reason", "pr_url", "merge_sha", "merged_by": "auto-merge" if merged else None}

def auto_merge_enabled(task: Task) -> bool  # effective(task).get("auto_merge") is True
def workflow_has_review(workflow: Workflow) -> bool
    # any(isinstance(s, RoleStep) and issubclass(s.role.output_type, ReviewOutput) for s in walk(workflow.steps))
def last_review(wf: WorkflowRun | None) -> ReviewOutput | None
    # poslední envelope typu ReviewOutput v wf.history (fallback: wf.envelopes.values() když history prázdná)
def review_blocker(review: ReviewOutput | None) -> tuple[str, str] | None
    # None review -> ("no_review", "no review ran in this run")
    # not approved -> ("review_rejected", ...)
    # blocking -> ("review_blocking", "N blocking item(s): ...")
    # unmet = [f.requirement for f in findings if not f.met] -> ("review_unmet", ...)
def hosting_blocker(status: PrStatus, checks: ChecksStatus) -> tuple[str, str] | None
    # state != OPEN -> ("pr_not_open", ...)
    # mergeability == CONFLICT -> ("conflict", "... run `factory task resolve ID`")
    # mergeability != MERGEABLE -> ("mergeability_unknown", ...)
    # checks.state == CHECKS_FAILING -> ("checks_failing", "red checks: a, b")
def try_auto_merge(repo: Path, result: TaskRunResult, task: Task, *, provider: GitProvider | None = None) -> AutoMergeResult
```

Pořadí kontrol v `try_auto_merge` (první neplatná podmínka = důvod):
1. `result.run.state != SUCCEEDED` → `run_not_succeeded`; `result.pr is None` → `no_pr`
   (s `result.pr_error`). Bez PR se nic nezapisuje do `task_prs`.
2. Workflow běhu (`named_workflow(result.run.workflow, rc.config, task.id)` z `aifactory.run.task`,
   `rc = load_run_config(main)`) nemá review fázi → `no_review_phase`
   („workflow X has no review phase; auto-merge never merges it“). Chyba načtení workflow →
   `workflow_unavailable`.
3. `review_blocker(last_review(result.workflow_run))`.
4. Provider (`provider` nebo `get_provider(settings, main)`): `status = provider.status(pr.request())`,
   `checks = provider.checks(pr.request())`; `ProviderError` z checků → `checks_unavailable`,
   ze statusu → `status_unavailable`; pak `hosting_blocker`.
5. Merge: `approve_task(repo, task.id, provider=provider, merged_by=AUTO_MERGE)`;
   `ReviewError` → `AutoMergeResult(False, exc.code, exc.message)` (např. `conflict`,
   `merge_failed`; done commit na větvi zůstává, `task approve` jde zopakovat – stejné jako dnes).
- Při každém nesloučení zapsat `store.update_pr(pr.branch, auto_merge_error=f"{code}: {reason}")`
  (store otevřít přes `TaskRunStore(result.trace_db)` a zavřít ve `finally`).
  Při úspěchu `auto_merge_error` vynuluje už `_approve`.
- Funkce nikdy nevyhazuje kvůli blokaci; vrací `AutoMergeResult`. (Neočekávané výjimky typu
  `OSError` převést na `merge_failed`, aby run_chain nespadl a PR zůstal otevřený.)

### `src/aifactory/review/__init__.py`
- Exportovat `AutoMergeResult`, `try_auto_merge`, `auto_merge_enabled`, `workflow_has_review`,
  `review_blocker`, `hosting_blocker`, `last_review`. Docstring doplnit.

## 5. Auto-continue po merge

### `src/aifactory/run/task.py`
- `TaskRunResult` nové pole `auto_merge: AutoMergeResult | None = None`
  (import pod `TYPE_CHECKING` z `aifactory.review.automerge` – review importuje run, za běhu
  nesmí vzniknout cyklus; modul už má `from __future__ import annotations`?
  ověřit, jinak anotovat řetězcem).

### `src/aifactory/run/queue.py`
- `STOP_NOT_MERGED = "not_merged"`, přidat do `STOP_REASONS`; exportovat v `run/__init__.py`.
- `run_chain` přestavět smyčku:
  ```
  while True:
      if not last.ok or last.pr is None: return STOP_FAILED
      with tmp: backlog = _base_backlog(...); after = backlog.by_id.get(last.run.task_id)
      if not isinstance(after, Task): return STOP_DISABLED
      merge_on = auto_merge_enabled(after)
      cont = auto or auto_continue_enabled(after)
      if merge_on:
          from aifactory.review.automerge import try_auto_merge   # lokální import (cyklus)
          last.auto_merge = try_auto_merge(repo, last, after, provider=provider)
          if not last.auto_merge.merged:
              return ChainResult(runs, STOP_NOT_MERGED if cont else STOP_DISABLED)
      if not cont: return STOP_DISABLED
      with tmp: backlog = _base_backlog(...) znovu (base se po merge posunul, task je done)
                after = ...; selection = select_next(...)
      ... beze změny dál
  ```
  (Dvojí načtení base backlogu jen když `merge_on`; jinak stačí první – zachovat dnešní chování.)
- `ChainResult.to_json()`: u každého runu přidat `"auto_merge": r.auto_merge.to_json() if r.auto_merge else None`.
- Docstring modulu: věta „The chain never approves nor merges anything“ nahradit popisem
  `auto_merge` (merge jen přes `try_auto_merge`, chain pokračuje až po merge, při nesloučení
  stop `not_merged`). Docstring `run_chain` („Never approves or merges“) upravit.
- `run/__init__.py` docstring a `__all__` (`STOP_NOT_MERGED`).

## 6. CLI (`src/aifactory/cli.py`)

- Nový `backlog auto-merge ID --on|--off|--inherit` (zkopírovat parser `auto-continue`; help:
  „With auto_merge: true, a succeeded run whose last review approved and whose PR merges
  cleanly with no red checks is approved and merged like `factory task approve`; a workflow
  without a review phase is never merged automatically.“). Handler `_backlog_auto_merge`
  – zobecnit `_backlog_auto_continue` na `_backlog_flag(args, key, setter, command)`.
  JSON: `{"changed","id","level","path","auto_merge","issues"}`; text
  `auto_merge on|off|inherited for ID (path)`. Dispatch `if command == "auto-merge"`.
- `task edit`: `--auto-merge {on,off,inherit}` (`choices`) → `edit_task(auto_merge=True/False)`
  nebo `clear_auto_merge=True`. Popis parseru doplnit. Do JSON výstupu task edit nic extra není třeba.
- `_run_json(result)`: přidat `"auto_merge": result.auto_merge.to_json() if result.auto_merge else None`.
- `_print_run`: když `result.auto_merge`:
  - sloučeno: `auto-merge: merged {url} into {base} ({sha7})`
  - jinak: `auto-merge: not merged ({code}): {reason}; the PR stays open, approve it with factory task approve {ID}` (stdout).
- `_task_run`: tisk `auto-continue: stopped (...)` i pro `chain.stop == STOP_NOT_MERGED`.
  Exit kód: blokovaný auto-merge není chyba (0, pokud runy ok).
- `_task_approve` text beze změny (merged_by=operator je default).
- Modulový docstring / epilog `task run` (řádek ~736) a help `--auto` doplnit o `auto_merge`.

## 7. Web API (`src/aifactory/web/`)

### `backlog.py`
- `_own_auto`/`_effective_auto` zobecnit na `_own_flag(container, key)` / `_effective_flag(container, key)`.
- Strom (`_container_json`): přidat `"auto_merge": _own_flag(c, "auto_merge")`.
- `_container_info`: `auto_merge`, `effective_auto_merge`.
- Task JSON (kolem ř. 120, kde je `own_workflow`): `own_auto_merge` (bool|None) a
  `effective_auto_merge` (bool, `effective(task).get("auto_merge") is True`).
- `EDIT_KEYS` += `"auto_merge"`, `"clear_auto_merge"`; v `edit()` číst `auto_merge` jako
  volitelný bool (nový `_opt_flag` – `None` když chybí, jinak musí být bool) a `clear_auto_merge`
  přes `_opt_bool`, předat do `core.edit_task`.
- Nová `auto_merge(repo, container_id, body)` (vzor `auto_continue`, `core.set_auto_merge`,
  výstup `auto_merge`, `effective_auto_merge`).
### `app.py`
- Route `POST /api/backlog/containers/{container_id}/auto-merge` → `backlog_auto_merge`
  (kopie `backlog_auto_continue`). Docstring modulu doplnit.
### `review.py`
- `pr` už nese `merged_by`, `auto_merge_error` (row.to_json). V `_done_list` přidat
  `"merged_by": row.merged_by` na úroveň položky (pro pohodlí UI) – volitelné.
- `approve()` vrací `ApproveResult.to_json()` → obsahuje `merged_by: "operator"`.
### `runs.py`
- `_summary`: `pr` rozšířit o `merged_by` a `auto_merge_error`.

## 8. Dashboard (`web/src/`)

- `lib/backlog.ts`: typy – tree node `auto_merge?: boolean | null`; `ContainerGraph.container`
  + `auto_merge`, `effective_auto_merge`; task detail `own_auto_merge`, `effective_auto_merge`;
  `TaskEditInput` + `auto_merge?: boolean`, `clear_auto_merge?: boolean`;
  `AutoMergeResult` + `setAutoMerge(containerId, mode)` (POST `/auto-merge`).
- `components/backlog/AutoContinueToggle.vue`: přidat props `label?: string` (default
  `'Auto-continue'`) a `testPrefix?: string` (default `'auto'`) → `data-test` `${prefix}-toggle`,
  `${prefix}-${mode}`, `${prefix}-effective`, `aria-label` = label. Výchozí hodnoty zachovají
  stávající testy.
- `views/BacklogView.vue`: vedle toggle auto-continue druhý toggle
  `label="Auto-merge" test-prefix="merge"` s `autoMode(graph.container.auto_merge)`,
  `effective_auto_merge`, vlastní `mergeBusy`/`mergePending` a handler `onAutoMerge`
  (vzor `onAutoContinue`: zavolat `setAutoMerge`, pak znovu načíst graf / aktualizovat
  container, chyby do `graphError`). Krátká poznámka/tooltip: „Workflow bez review se
  automaticky nemerguje.“
- `components/backlog/TreeNode.vue`: vedle ikonky auto-continue ikonka/tooltip
  „auto-merge zapnuto“ když `node.auto_merge === true`.
- `components/backlog/TaskForm.vue` (jen režim edit): `SelectMenu` „Auto-merge“ s volbami
  `inherit` (Zděděno), `on`, `off`, počáteční hodnota z `task.own_auto_merge`; při změně
  `input.auto_merge = true/false` nebo `input.clear_auto_merge = true`. `data-test="auto-merge"`.
- `components/backlog/TaskDetail.vue`: řádek „Auto-merge: zapnuto/vypnuto (zděděno|vlastní)“.
- `lib/review.ts`: typ PR + `merged_by?: string | null`, `auto_merge_error?: string | null`;
  `ApproveResult.merged_by`.
- `components/review/ReviewDetail.vue`: když `pr.merged_by === 'auto-merge'` → štítek
  „Sloučil auto-merge“ (`data-test="merged-by-auto"`); když PR otevřený a `pr.auto_merge_error`
  → upozornění „Auto-merge nesloučil: {důvod} – schvál ručně“ (`data-test="auto-merge-error"`).
- `components/review/ReviewList.vue` (hotové PR): štítek „auto-merge“ u položek s
  `pr.merged_by === 'auto-merge'`; u otevřených s `auto_merge_error` malá poznámka.
- `views/ReviewView.vue`: pokud detail/list renderuje sám, doplnit totéž tam (zadání ho
  jmenuje – ověřit, kde se štítky reálně zobrazují).
- `lib/runs.ts` (typ běhu) + `components/runs/RunDetail.vue`: u odkazu na PR text
  „sloučil auto-merge“ (`data-test="pr-merged-by"`) nebo důvod `auto_merge_error`.
- Fixtures `test/backlogFixtures.ts`, `test/reviewFixtures.ts` doplnit o nová pole.
- Na konci `just web-build` (přebuildí `src/aifactory/web/static/`, jak to dělaly dřívější
  UI tasky); pokud by build v prostředí nešel, není to podmínka testů.

## 9. Dokumentace v balíčku
- `src/aifactory/skill/skill.md`: u ukázky frontmatter (`auto_continue: false`, ř. ~160) přidat
  `auto_merge: false`; v bodě 5 (auto-continue, ř. ~360) přidat odstavec o `auto_merge`
  (`factory backlog auto-merge ID --on|--off|--inherit`, `factory task edit ID --auto-merge on|off|inherit`,
  podmínky, workflow bez review nikdy, při nesloučení PR čeká na `task approve`, chain
  pokračuje až po merge). Ověřit `tests/test_skill.py` (pokud porovnává s vyrenderovanou kopií,
  aktualizovat i ji).
- `run/guard.py`, `run/mainwrites.py`: v docstringu seznamu příkazů doplnit `backlog auto-merge`.

## 10. Testy (pytest, `tests/`)

Nový `tests/review/test_auto_merge.py` (+ případně `tests/run/test_auto_merge_chain.py`).
Používat `run_repo` (`make_run_repo`, `fake_env`, `Script`, `ok`, `write`, `commit_all`, `git`)
a pro GitHub `gh_fake` (`install_fake_gh`, `reply`, …) podle vzoru
`tests/review/test_approve_merge_retry.py`. Testovací repo potřebuje workflow s review,
např. zapsat do `.factory/workflows/plan-review-commit.yaml`:
`name: plan-review-commit`, `steps: [plan, review, commit]` **bez** `accept` vázaného na
review (aby šlo mít `succeeded` běh se zamítnutým review), a prompty
`.factory/prompts/reviewer/{system,user}.md` (+ reviewer v `agents.yaml`, pokud ho
`agents_yaml` nemá – ověřit v `run_repo.py`). Review envelope přes
`script.add("reviewer", ok(approved=True, findings=[{"requirement": "x", "met": True}], blocking=[]))`.

Čisté funkce (bez gitu):
1. `review_blocker`: None → `no_review`; `approved=False` → `review_rejected`;
   `approved=True, blocking=["x"]` → `review_blocking`; `approved=True`, finding `met=False`
   → `review_unmet`; čisté schválení → None.
2. `hosting_blocker`: CLOSED/MERGED → `pr_not_open`; CONFLICT → `conflict`; UNKNOWN →
   `mergeability_unknown`; `CHECKS_FAILING` → `checks_failing`; PENDING/NONE/PASSING + MERGEABLE → None.
3. `workflow_has_review`: packaged `simple-sdlc` True, `plan-commit` False.
4. `last_review`: dvě review v history (první approved, poslední rejected) → vrací poslední.

Integrace (provider local, fake harness):
5. Happy path: `auto_merge: true` na stepu, workflow s review → `run_chain` (bez auto-continue)
   sloučí PR: `main` obsahuje změnu i `status: done`, `task_prs.state == merged`,
   `merged_by == "auto-merge"`, `auto_merge_error is None`, `chain.stop == STOP_DISABLED`,
   `result.auto_merge.merged`.
6. `run` neskončil `succeeded` (např. `accept` nesplněn / planner selže) → žádný merge, `STOP_FAILED`.
7. Workflow bez review (`plan-commit`) s `auto_merge: true` → PR otevřený,
   `auto_merge_error` začíná `no_review_phase`, `main` beze změny.
8. Review zamítnuto (`approved=False`, blocking) → PR otevřený, `review_rejected`.
9. Konflikt: `run_task` (ne chain) otevře PR, pak na `main` commit konfliktní změny téhož
   souboru, pak `try_auto_merge(repo, result, task)` → `conflict`, PR otevřený, důvod v `task_prs`.
10. Task přepíše `auto_merge: false` při `true` na stepu → nic se nemerguje, `result.auto_merge is None`.
11. Řetěz: step `auto_continue: true` + `auto_merge: true`, T02 `depends_on: [T01]` →
    `run_chain(T01)` sloučí T01, pak spustí T02 (dřív by byl `waits_on_pr`), worktree/base_sha
    T02 vychází z base obsahujícího změnu T01 (ověřit soubor T01 v commitu `base_sha` T02);
    oba PR sloučené.
12. Řetěz se zablokovaným merge (např. review zamítnuto) → `chain.stop == "not_merged"`, další
    task nespuštěn.
13. Falešný `gh` (GitHubProvider jako v `test_approve_merge_retry.py`): `pr view` MERGEABLE,
    `pr checks` → `[{"name":"ci","bucket":"fail"}]` → `checks_failing`, žádné `pr merge` v logu;
    druhý test s `bucket: pass` → volá `pr merge`, `merged_by == "auto-merge"`; třetí:
    `pr checks` exit 1 se stderr `no checks reported…` → merguje.
14. Operátor: `approve_task` zapíše `merged_by == "operator"`.
15. Migrace store: DB vytvořená starým schématem (ručně `CREATE TABLE task_prs` bez nových
    sloupců) → `TaskRunStore` ji otevře a sloupce doplní.

Backlog / CLI / web:
16. `tests/backlog/test_backlog_auto_merge.py` (vzor `test_backlog_auto_continue.py`):
    `set_auto_merge` on/off/inherit, idempotence, dědění projekt→step→task, nevalidní hodnota
    → `invalid_field` s `'auto_merge'`, CLI `backlog auto-merge` text i `--json`, neznámé ID → 2.
17. `task edit --auto-merge off|on|inherit` zapíše/odebere klíč v task souboru; konflikt
    `--auto-merge` vs. clear přes `edit_task` → `conflicting_options`.
18. CLI `task run` text: řádek `auto-merge: merged …` / `auto-merge: not merged (no_review_phase)…`;
    `--json` obsahuje `auto_merge` u runu i v `chain.runs`.
19. Web (`tests/web/`): `POST /api/backlog/containers/{id}/auto-merge` jako CLI (vzor
    `test_auto_continue_writes_like_the_cli`), graf vrací `auto_merge`/`effective_auto_merge`,
    edit tasku s `auto_merge`/`clear_auto_merge`, review detail/list a runs detail vrací
    `merged_by`/`auto_merge_error`.

Vitest (`web/src/**.test.ts`):
- `AutoContinueToggle.test.ts`: s `label="Auto-merge" test-prefix="merge"` renderuje `merge-on` atd.
- `BacklogView.test.ts`: graf stepu – klik na `merge-on` pošle POST na `/auto-merge`.
- `TaskForm.test.ts`: volba auto-merge pošle `auto_merge: false` / `clear_auto_merge: true`.
- `ReviewDetail.test.ts`: štítek „Sloučil auto-merge“ a hláška `auto-merge-error`.
- `RunDetail.test.ts`: `pr-merged-by`.
- `lib/backlog.test.ts`: `setAutoMerge` volá správný endpoint.

## 11. Ověření
- `just test` (pytest + `web-test`: bun typecheck + vitest), `just typecheck` (mypy),
  `just lint` (ruff check + ruff format --check). Vše musí projít.
- Ruční sanity: `cd aifactory && uv run factory backlog auto-merge --help`,
  `uv run factory task edit --help`.

## Poznámky / rizika
- Cyklus importů: `aifactory.review` importuje `aifactory.run`; v `run/queue.py` a
  `run/task.py` importovat automerge lokálně / pod `TYPE_CHECKING`.
- Gate `verdict_consistent` v enginu nepustí `approved=True` s blocking/unmet, proto
  podmínky blocking/unmet testovat čistou funkcí `review_blocker`, ne přes engine.
- `try_auto_merge` volá `approve_task`, který si otevírá vlastní kontext/store – nedržet
  otevřený zápisový store přes to volání.
- `GitHubProvider.status` už opakuje dotaz při `unknown` mergeability; `local` vrací vždy
  MERGEABLE/CONFLICT, takže `mergeability_unknown` reálně nastává jen u hostingu.
