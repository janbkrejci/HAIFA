# `factory backlog sync`: PR s `status: done` pro PR mergnuté mimo HAIFA

## Co se změnilo a proč

Když se PR tasku mergne mimo factory (UI hostingu, ruční `git merge`), task v `base` zůstal bez `status: done` a `task approve` pak končil chybou `pr_not_open`. Nový příkaz `factory backlog sync [--json] [--repo PATH]` tento stav dorovná, a to **jen přes PR**. Do `base` nic necommituje a vlastní sync PR nemerguje.

Průběh (`review/sync.py`, `_sync`):

1. **Obnovení stavů.** Pro každý otevřený řádek v `task_prs` se zeptá providera a zapíše `merged`/`closed` (`_record_state`). Stejně obnoví otevřené sync PR v nové tabulce `sync_prs`. U zavřeného PR tasku se změní jen jeho záznam, task samotný zůstává beze změny.
2. **Dotažení base.** Zavolá `_catch_up_base`. Výchozí ref je `refs/remotes/<remote>/<base>`, pokud existuje, jinak `refs/heads/<base>`. Když není ani jeden, skončí chybou `unknown_base`.
3. **Kandidáti.** V dočasném detached worktree `<worktrees_dir>/sync-check` načte backlog z `base`. Projde tasky, které mají aspoň jeden `merged` PR (`merged_task_ids`), a vezme vždy nejnovější PR. Přeskočí (a uvede ve `skipped`) tyto případy:
   - `newer_pr`: nejnovější PR není mergnutý,
   - `not_in_base`: task v `base` není,
   - `cancelled`: task je zrušený,
   - `reopened`: v `## Běhy` už je záznam s URL toho PR,
   - `missing_on_sync_branch`: soubor tasku na sync větvi chybí.

   Tasky, které už mají `done`, tiše vynechá.
4. **Zápis.** Pokud nejsou žádní kandidáti, nevytvoří se větev, commit ani PR. Jinak použije existující otevřený sync PR, nebo založí novou větev `factory-sync/<n>` (n = nejvyšší číslo z git refů a z `sync_prs`, zvýšené o 1). Prefix záměrně není `factory/`, aby se sync větev nečetla jako větev tasku. Hlavičku tasku a řádek v `## Běhy` upraví `mark_done` (workflow posledního úspěšného běhu a cena, viz `_done_entry`). Všechny tasky jdou do jednoho commitu `backlog sync: status done for …`. `_guard_branch` odmítne commit mimo větev `factory-sync/*` (chyba `sync_on_base`). Následuje push a `create_pr`. Pokud už sync PR existuje, zavolá se `update_pr` a do těla PR se doplní nové řádky tasků.

## Soubory

- `aifactory/src/aifactory/review/sync.py` (nový): `sync_backlog(repo, *, provider=None) -> SyncResult` a dataclassy `SyncTask`, `SyncSkip` a `SyncResult`. Chyby providera, konfigurace a worktree převádí na `ReviewError`.
- `aifactory/src/aifactory/review/flow.py`: z `_approve` jsou vytažené sdílené helpery `_worktrees_dir`, `_branch_worktree` a `_done_entry`, chování approve zůstává stejné. Hláška u `pr_not_open` teď odkazuje na `factory backlog sync`.
- `aifactory/src/aifactory/run/store.py`: nová tabulka `sync_prs` (klíčem je `branch`, `tasks` je JSON seznam id), `SyncPrRow` a metody `save_sync_pr`, `update_sync_pr` (neznámý sloupec vyhodí `ValueError`, nastavuje `updated_at`), `sync_pr_for_branch`, `open_sync_prs`, `sync_branches` a `merged_task_ids`. Sync PR nepatří žádnému tasku, a proto se neobjevuje v `open_prs()`.
- `aifactory/src/aifactory/review/__init__.py` a `run/__init__.py`: exporty `sync_backlog`, `SyncResult` a `SyncPrRow`.
- `aifactory/src/aifactory/cli.py`: podpříkaz `backlog sync` s `--json` a `--repo`. Při chybě vrací kód 2 (`invalid_config` nebo kód `ReviewError`/`TaskRunError`).
- `aifactory/tests/run/test_backlog_sync.py` (nový): testy s providerem `local`.
- `specs/077275cc_backlog-sync-pr.md`: specifikace změny.

## Použití

```
factory backlog sync            # textový výstup
factory backlog sync --json     # {ok, pr, url, created, updated, tasks, skipped, states, warnings}
```

Textový výstup vypíše jednu z těchto zpráv: `nothing to sync`, `opened <url>: done for <ids>`, `updated <url>: …` nebo `sync PR <url> already open: …`. Pak následují řádky `skipped …` a `PR <url> of <task> is merged|closed`. Varování jdou na stderr. Sync PR je potřeba mergnout ručně. Další běh sync ho pak zaznamená jako `merged` a nic nového neotevře.

## Ověření

`just test` (hlavně `tests/run/test_backlog_sync.py`), `just typecheck`, `just lint`. Testy pokrývají tyto scénáře:

- merge mimo HAIFA: sync otevře `factory-sync/1`, `main` zůstane beze změny a pracovní strom je čistý,
- po merge sync PR je `done` v `main` a druhý sync nic neotevře,
- zavřený PR: task beze změny, `task_prs.state = closed`,
- prázdný běh nevytvoří větev,
- opakovaný sync znovu použije otevřený sync PR bez nového commitu,
- sync po `task approve` nic neudělá,
- operace nad `sync_prs` ve store,
- nápověda příkazu.
