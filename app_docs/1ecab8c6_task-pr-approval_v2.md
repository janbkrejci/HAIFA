# Pull request, schválení a vrácení tasku (`GitProvider` local/github)

Spec: `specs/1ecab8c6_task-pr-approval.md`. Podrobnější referenční popis je v `app_docs/1ecab8c6_task-pr-approval.md`, který je součástí stejné změny.

## Co změna dělá

Doplňuje konec běhu tasku, tedy kroky 4–7 sekce „Běh úkolu“ (D6, D8, D9, D11):

- **`task run`**: po úspěšném běhu (`succeeded`) pushne větev `factory/<id>-<n>` a otevře PR. Popis PR obsahuje sekce `## Zadání`, `## Agenti`, `## Gates a testy`, `## Review` a `## Náklady`. Náklady se berou z `sessions.total_cost` a `total_tokens` v trace DB. Když se PR nepodaří vytvořit, běh zůstane `succeeded`, ale nastaví se `pr_error` a CLI vrátí exit 1.
- **`task approve <id>`** postupuje takto:
  1. zjistí stav PR;
  2. pošle approve review, ale jen při `require_review: true`;
  3. vytvoří jeden commit `<id>: status done` v PR větvi (`status: done` a řádek v `## Běhy`);
  4. pushne větev;
  5. provede merge s `merge_strategy`;
  6. smaže worktree.

  Při konfliktu, u PR, který už je mergnutý nebo zavřený, a při odmítnutém review příkaz skončí dřív, než cokoli změní. Opakované volání druhý done commit nevytvoří.
- **`task return <id> --note TEXT`**: odmítne worktree s necommitnutými změnami. Jinak smaže staré worktree, přidá do PR komentář „Vráceno k přepracování“ a spustí nový běh na téže větvi. Poznámka se do promptu dostane jako `## Note`. Potom se aktualizuje popis PR. Soubor tasku se nemění.
- **`backlog sync`**: posune `base` na stav z remote. Pokud se `base` a remote rozešly, vrátí `base_diverged`. Potom najde mergnuté PR z větví `factory/`, jejichž task v `base` není `done` ani `cancelled`, a všechny je doplní jedním commitem `backlog sync: <ids> done` do `base`. U provideru `local` se berou jen větve s vlastními commity.

`done` tedy vzniká jen commitem při approve (do PR větve) nebo při `backlog sync` (do `base`), nikdy při běhu.

## Konfigurace `.factory/config.yaml`

`git_provider` (`local` | `github`, výchozí `local`), `merge_strategy` (`squash` | `merge`, výchozí `squash`), `require_review` (bool, výchozí `false`), `remote` (výchozí `origin`). Neplatné hodnoty vyvolají `ConfigError`.

## Provideři (`providers/`)

- `base.py`: abstraktní `GitProvider` s metodami `create_pr`, `update_pr`, `status`, `approve`, `merge(strategy, head_sha, subject)`, `comment` a `merged_prs`; `push` jde přes `gitops.push`. Stavy PR jsou `open`, `mergeable`, `conflict`, `merged` a `closed`. Výjimky jsou `ReviewRejected` a `MergeFailed`. `get_provider()` je v `__init__.py`.
- `local.py`: PR je větev. Stav se určuje podle toho, zda větev existuje, zda je její tip předkem `base` a jak dopadne zkušební merge. Merge vytvoří commit v dočasném worktree a posune `base`. Když je nastavený remote, pushne se. Approve a comment nedělají nic.
- `github.py`: každé volání `gh` jde přes `GhCli.run` (`$HAIFA_GH` nebo `gh`). Těla jdou na stdin přes `--body-file -`. Merge používá `--squash|--merge --match-head-commit SHA --subject T`. Když `gh pr review --approve` selže, vznikne `ReviewRejected`.

## Soubory

| Soubor | Role |
|---|---|
| `prototype/src/haifa_proto/providers/{__init__,base,local,github}.py` | rozhraní a implementace |
| `prototype/src/haifa_proto/review.py` | `approve_task`, `return_task`, `sync_backlog` |
| `prototype/src/haifa_proto/run.py` | tabulka `task_prs`, `publish`, `run_on_branch`, `## Note` v promptu |
| `prototype/src/haifa_proto/prbody.py` | titulek, popis a náklady PR |
| `prototype/src/haifa_proto/taskfile.py` | `mark_done`, `run_entry` (textová úprava hlavičky a `## Běhy`) |
| `prototype/src/haifa_proto/gitops.py` | git operace, dočasné worktree, `advance_branch` |
| `prototype/src/haifa_proto/cli.py`, `config.py` | příkazy `task approve`, `task return`, `backlog sync`; nové klíče konfigurace |
| `prototype/tests/gh_fake.py`, `task_repo.py` | falešné `gh` (loguje argv a stdin), pomocníci pro testovací repo |
| `prototype/tests/test_*` (viz `changed_files`) | testy providerů, toku local i github, CLI, configu a taskfile |

## Použití a ověření

```
haifa-proto task run T-1           # vypíše i "pr <url>"
haifa-proto task return T-1 --note "oprav X"
haifa-proto task approve T-1 --json
haifa-proto backlog sync --json
```

Chyby mají tvar `{"ok": false, "error": {code, message}}` a exit 1. Kódy jsou například `no_pr`, `pr_not_open`, `conflict`, `review_rejected`, `merge_failed`, `dirty_worktree`, `branch_checked_out`, `base_diverged`, `gh_missing`, `gh_failed` a `missing_note`.

Testy (`cd prototype && uv run pytest`) nevolají model ani GitHub:

- `test_pr_flow_local.py` používá lokální bare repo jako remote. Ověřuje push a PR, `return` a potom `approve` (v `base` je `status: done` i kód), strategii `merge`, ohlášení konfliktu a `backlog sync` po ručním merge.
- `test_providers_github.py` a `test_pr_flow_github.py` ověřují přes `gh_fake.py` argv každé operace.

## Známá omezení (z kódu)

- Provider `local` větve nemaže. Squash merge od HAIFA pozná jen z `task_prs`.
- U `github` merguje hosting, takže lokální `base` se posune až při `backlog sync`.
- Konflikt se jen ohlásí, rebase se nedělá.
