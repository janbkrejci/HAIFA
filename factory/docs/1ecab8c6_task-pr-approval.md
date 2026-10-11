# Pull request tasku, `task approve`, `task return` a `backlog sync`

Spec: `specs/1ecab8c6_task-pr-approval.md`

## Co se změnilo

Běh tasku, který splní `accept`, pushne větev a otevře pull request přes `GitProvider`. `haifa-proto task approve <task-id>` do PR větve přidá jeden commit se `status: done` a záznamem do `## Běhy` a potom PR mergne. `haifa-proto task return <task-id> --note TEXT` spustí nový běh na téže větvi a PR aktualizuje. `haifa-proto backlog sync` doplní `done` u PR mergnutých mimo HAIFA. Tím jsou pokryté kroky 4–7 sekce „Běh úkolu“ a rozhodnutí D6, D8, D9 a D11 z briefu.

## Konfigurace (`.factory/config.yaml`)

| Klíč | Výchozí | Význam |
|---|---|---|
| `git_provider` | `local` | `local` nebo `github` |
| `merge_strategy` | `squash` | `squash` nebo `merge` |
| `require_review` | `false` | při `true` pošle `task approve` approve review jménem přihlášeného uživatele |
| `remote` | `origin` | git remote pro push |

## Rozhraní `GitProvider` (`providers/`)

`base.py` definuje `create_pr`, `update_pr`, `status`, `approve`, `merge(strategy, head_sha, subject)`, `comment` a `merged_prs`. Metoda `push` je společná a jde přes `gitops.push`. Stavy PR jsou `open` (mergnutelnost neznámá), `mergeable`, `conflict`, `merged` a `closed`. `get_provider(config, root)` vybere implementaci podle `git_provider`.

- **`local`**: PR je větev a jeho `url` je `<remote-url>#<branch>`, bez remote `local:<branch>`. Stav se zjišťuje z gitu: když větev neexistuje, je `closed`; když je její tip předkem `base`, je `merged`; jinak rozhodne zkušební merge v dočasném detached worktree mezi `mergeable` a `conflict`. Merge vytvoří squash nebo merge commit v dočasném worktree a `base` posune přes `merge --ff-only` tam, kde je checkoutnutá, jinde přes `update-ref`. S remote se `base` pushne. Approve a comment nic nedělají. Větve se nemažou.
- **`github`**: všechna volání `gh` jdou přes `GhCli.run` (`$HAIFA_GH` nebo `gh` z `PATH`). Těla se posílají přes stdin (`--body-file -`). Použité argv:
  - `pr create --base B --head BR --title T --body-file -`
  - `pr edit N --body-file -`
  - `pr view N --json state,mergeable,headRefOid,mergeCommit`
  - `pr review N --approve --body-file -`
  - `pr merge N --squash|--merge --match-head-commit SHA --subject T`
  - `pr comment N --body-file -`
  - `pr list --state merged --base B --json number,url,headRefName,mergeCommit --limit 200`

  Když hosting odmítne review, vznikne `ReviewRejected`, a to se stderr od `gh`.

## Tok

1. **`task run`** (`run.py`): po `succeeded` volá `publish`, který pushne větev a vytvoří PR. Titulek PR je `<id>: <title>`. Popis sestaví `prbody.py` a obsahuje sekce Zadání (včetně poznámek k běhům), Agenti (shrnutí envelope), Gates a testy (`gate_results` z trace a výsledky s `passed`), Review (`approved` a `blocking`) a Náklady (`sessions.total_cost` a `total_tokens` za každý běh na větvi). Když selže push nebo vytvoření PR, běh zůstane `succeeded`, ale `pr_error` je nastavené a CLI vrátí exit 1. Soubor tasku se nemění.
2. **`task return`** (`review.return_task`): zkontroluje otevřený PR a to, že worktree nemají necommitnuté změny. Pak smaže worktree předchozích běhů, pošle komentář „Vráceno k přepracování“ a zavolá `run.run_on_branch`, tj. nový běh na existující větvi s poznámkou v `## Note`. Nakonec pushne větev a aktualizuje popis PR. Stav tasku se nemění.
3. **`task approve`** (`review.approve_task`) postupuje v tomto pořadí:
   1. zjistí stav PR; `conflict`, `merged` nebo `closed` příkaz ukončí a nic se nezmění;
   2. pokud je `require_review: true`, pošle approve review; odmítnutí ukončí příkaz bez commitu a bez merge;
   3. vytvoří jeden commit `<id>: status done` v PR větvi, a to ve worktree běhu nebo v dočasném worktree `approve-…`;
   4. pushne větev;
   5. provede merge s `merge_strategy`, při `github` s `--match-head-commit`;
   6. zapíše `task_prs.state = merged` a smaže worktree.

   Opakované approve je idempotentní: druhý done commit nevznikne.
4. **`backlog sync`** (`review.sync_backlog`): pokud existuje remote, stáhne `base` a posune ji fast-forwardem (při rozejití vrátí chybu `base_diverged`). Potom vezme `merged_prs()` z větví `factory/`, u `local` jen ty s vlastními commity. Pro tasky, které v `base` nejsou `done` ani `cancelled`, vytvoří jeden commit `backlog sync: <ids> done` do `base` a pushne ho.

Záznam v `## Běhy` (`taskfile.py`) má tvar `- 2026-09-26 · workflow build-commit · PR <url> · náklady $0.42`. Když sekce chybí, přidá se na konec souboru. Úprava souboru je čistě textová, zbytek souboru zůstane beze změny.

## Tabulka `task_prs` (trace DB)

Sloupce: `branch` (PK), `task_id`, `provider`, `pr_id`, `url`, `base`, `base_sha` (fork point prvního běhu), `title`, `body`, `state` (`open`/`merged`/`closed`), `created_at`, `updated_at`, `merged_at`, `merge_sha`. `task show` je vypisuje (v JSON pod klíčem `"prs"`).

## CLI

- `task run`: navíc vypíše `pr <url>`. JSON obsahuje navíc `"pr"` a `"pr_error"`.
- `task approve <id> [--repo] [--json]`: `{"ok", "task_id", "pr", "merge_sha", "strategy", "reviewed", "removed_worktrees"}`.
- `task return <id> --note TEXT [--repo] [--json]`: výstup je stejný jako u `task run`.
- `backlog sync [--repo] [--json]`: `{"ok", "updated": [{task_id, branch, url}], "commit"}`.
- Chyby mají tvar `{"ok": false, "error": {code, message}}` a exit 1. Kódy: `no_pr`, `pr_not_open`, `conflict`, `review_rejected`, `merge_failed`, `push_failed`, `dirty_worktree`, `branch_checked_out`, `base_diverged`, `gh_missing`, `gh_failed`, `missing_note`.

## Odchylky a otevřené body (pro zprávu 1.10)

- Approve review se posílá jen při `require_review: true`, protože GitHub nedovolí autorovi schválit vlastní PR.
- Pořadí je approve review → done commit → merge. Pokud má hosting zapnuté „dismiss stale reviews“, nový commit review zneplatní; tuto kombinaci je potřeba ještě vyřešit.
- Provider `local` větve nemaže. Že HAIFA větev squash-mergnula, pozná jen z `task_prs`.
- Konflikt se jen ohlásí. Rebase ani workflow `resolve` v 1.6 nejsou.
- U `github` merge provede hosting, takže lokální `base` se posune až při dalším `backlog sync` nebo `git pull`.

## Soubory

| Soubor | Role |
|---|---|
| `prototype/src/haifa_proto/providers/{__init__,base,local,github}.py` | `GitProvider`, `get_provider`, implementace |
| `prototype/src/haifa_proto/gitops.py` | git operace, dočasné detached worktree, posun větve |
| `prototype/src/haifa_proto/prbody.py` | titulek a popis PR, náklady z trace |
| `prototype/src/haifa_proto/taskfile.py` | `mark_done`, `run_entry` |
| `prototype/src/haifa_proto/review.py` | `approve_task`, `return_task`, `sync_backlog` |
| `prototype/src/haifa_proto/run.py` | `task_prs`, `publish`, `run_on_branch` |
| `prototype/src/haifa_proto/cli.py`, `config.py` | nové příkazy a klíče |
| `prototype/tests/gh_fake.py` | falešné `gh` na `PATH`, loguje argv a stdin |
| `prototype/tests/test_providers_{local,github}.py`, `test_pr_flow_{local,github}.py`, `test_taskfile.py` | testy |
