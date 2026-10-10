# Tok PR úkolu: publish, `task approve`, `task return`, `task clean`

Implementuje kroky 4, 5 a 7 sekce „Běh úkolu“ z `docs/product-brief.md`. Po úspěšném běhu se větev pushne a otevře se PR. Nové příkazy `factory task approve`, `task return` a `task clean` PR schválí a zmergují, vrátí úkol agentům, nebo uklidí worktree.

> **Dočasné (D11):** `task approve` zatím **neposílá approve review** do hostingu. Rovnou udělá commit `status: done` a merguje. Je to označené v kódu (`TODO(D11)` v `review/flow.py` a `cli.py`), v nápovědě i ve výstupu (`note: approve review not sent (D11, temporary)`). V JSON výstupu je `reviewed` vždy `false`.

## Co se změnilo

### Publikace PR po běhu (krok 4) — `run/task.py`, `review/publish.py`, `review/prbody.py`
- Když běh skončí ve stavu `succeeded`, `_execute` zavolá `publish()`. Ta pushne větev a otevře PR, nebo přes `provider.update_pr` aktualizuje popis PR, pokud větev PR už má. Záznam se uloží do `task_prs`.
- Pokud push nebo hosting selže (`ProviderError`), běh zůstane `succeeded`, ale do `TaskRunResult.pr_error` se zapíše důvod a `result.ok` je `False` (exit 1).
- Popis PR sestavuje `pr_body()` v češtině. Obsahuje sekce `## Zadání` (včetně poznámek z návratů), `## Agenti` (shrnutí z envelope, harness a model), `## Gates a testy` (poslední verdikt každé gate z `gate_results` a výsledky testů), `## Review` (approved nebo blokující výhrady) a `## Náklady` (za každý běh na větvi a celkem, ze `sessions` v trace DB). Titulek je `"<task-id>: <title>"`.
- `run_task` má nové parametry `provider` (výchozí je hodnota z `git_provider`) a interní `branch`. S `branch` se běh nevytvoří na nové větvi, ale pokračuje na existující, přes `worktree add` bez `-b`. Jako `base_sha` se převezme hodnota z existujícího PR. Neexistující větev vrátí chybu `unknown_branch`.

### Tabulka `task_prs` — `run/store.py`
- Jeden řádek na větev (PK je `branch`) se stavem `open`, `merged` nebo `closed`, dále `merged_at`, `merge_sha` a `body`.
- Nový dataclass `TaskPrRow` s metodou `.request()`, která vrací `PullRequest`.
- Nové metody store: `save_pr`, `update_pr`, `pr_for_branch`, `latest_pr`, `open_pr`, `prs_for_task`, `open_prs`, `runs_on_branch` a `all_runs` (ta nejdřív převede mrtvé `running` na `aborted`).
- `run/task.py` přidává `task_prs_for()`. `factory task show` vypisuje sekci `prs:` a v `--json` pole `prs`.

### Approve, return, clean (kroky 5 a 7) — `review/flow.py`
- **`approve_task`** postupuje takto:
  1. Kontroly. Chybí PR → `no_pr`. PR není `open` → `pr_not_open`. Úkol právě běží → `already_running`.
  2. Dotaz na stav u providera. Zavřený PR se zapíše jako `closed` a vrátí `pr_not_open`. PR zmergovaný mimo factory vrátí `pr_not_open` s odkazem na `backlog sync`.
  3. `CONFLICT` vrátí `conflict`. Větev checkoutnutá v hlavním checkoutu vrátí `branch_checked_out`.
  4. V worktree větve (případně v dočasném `approve-<branch>`) se provede `mark_done` se záznamem `run_entry` (datum, workflow, URL, náklady) a commit `"<id>: status done"`.
  5. Push, pak `provider.merge`. Když merge selže, done commit na větvi zůstane a approve lze pustit znovu.
  6. `task_prs` se nastaví na `merged`.
  7. `_catch_up_base` provede fetch a fast-forward lokální `base` z remote. Při divergenci nebo chybě jen přidá warning.
  8. Smažou se worktree všech běhů na větvi.
- **`return_task`**: bez poznámky vrátí `missing_note`. Zkontroluje PR stejně jako approve. Pokud má některý worktree větve necommitnuté změny, vrátí `dirty_worktree`. Jinak worktree smaže, do PR pošle komentář „Vráceno k přepracování: …“ a spustí `run_task(..., note=..., force=True, branch=<větev PR>)`. Po úspěšném běhu `publish` aktualizuje popis PR.
- **`clean_worktrees`**: nejdřív obnoví stav otevřených PR u providera. Pak smaže worktree běhů, jejichž PR je `merged`/`closed` (reason = stav PR), a „opuštěných“ běhů bez PR, které nejsou nejnovějším během úkolu (reason `abandoned`). Běžící běhy vynechá.
- Chyby se hlásí jako `ReviewError(code, message)` (`review/errors.py`).

### Providery — `providers/base.py`, `github.py`, `azure.py`, `local.py`, `git.py`
- Nová abstraktní metoda `GitProvider.update_pr(pr, body)`:
  - GitHub používá `gh pr edit <id> --body-file -`.
  - Azure používá `az repos pr update --id … --description …`.
  - `local` nedělá nic, popis je uložený jen v `task_prs.body`.
- `providers/git.py`: nová funkce `fetch(root, remote, branch)`, která při selhání vyhodí chybu `fetch_failed`.

### CLI — `cli.py`
- Nové podpříkazy `task approve ID`, `task return ID --note TEXT` a `task clean`, všechny s `--json` a `--repo`.
- `task run` a `task return` sdílejí výpis `_run_output`. V JSON výstupu přibyla pole `pr` a `pr_error`.
- `ReviewError` se hlásí stejně jako `TaskRunError`: exit 2, v `--json` jako `errors[].code`. Nápověda obsahuje seznam nových chybových kódů.

## Použití

```sh
factory task run M01-S01-T01            # po accept: push + PR, vypíše "pr <url>"
factory task return M01-S01-T01 --note "Doplň index na sloupec id"
factory task approve M01-S01-T01        # commit status: done, merge, base z remote, úklid worktree
factory task clean --json               # smaže worktree zavřených/zmergovaných a opuštěných běhů
factory task show M01-S01-T01           # sekce prs:
```

## Ověření

- `aifactory/tests/run/test_task_pr_flow.py` (provider `local`) obsahuje testy:
  - publikace PR a žádný PR po neúspěšném běhu,
  - approve (done commit a merge, textový výstup, zmínka D11 v nápovědě),
  - return na téže větvi a return bez poznámky,
  - zavřený PR zapsaný jako `closed` a následné `pr_not_open`,
  - `no_pr`,
  - dotažení base z remote (`HostedLocal` merguje na remote, další běh startuje z `merge_sha`),
  - `clean` pro opuštěné a zavřené worktree i bez běhů,
  - metody store pro `task_prs`.
- `test_update_pr` je v `tests/providers/test_providers_github.py` a `test_providers_azure.py`.
- Spusťte `just test`, `just typecheck` a `just lint`.

Plán je ve `specs/7c3b89ff_task-pr-flow.md`.
