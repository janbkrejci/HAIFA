# HAIFA-S01-T11: `factory config commit` a `factory config pull`

Zveřejnění commitu do base, které posune lokální base až poté, co je commit na remote.
Dřív `backlog commit` commitoval přímo v hlavním checkoutu a po odmítnutém push zůstal na
lokální base nepushnutý commit. Jádro je obecné (`aifactory/providers/publish.py`), konfigurační
vrstva je v `aifactory/config/commit.py`. `factory backlog commit` se nemění.

```
factory config commit [--repo CESTA] [--dry-run] [--pr] [--expect DIGEST] [-m TEXT] [--json]
factory config pull   [--repo CESTA] [--json]
```

## Soubory

| Soubor | Co nese |
|---|---|
| `aifactory/src/aifactory/providers/publish.py` | `PlannedFile`, `PublishPlan`, `plan_files`, `plan_digest`, `remote_state`, `run_blocker`, `publish_direct`, `publish_pr`, `pull_base` |
| `aifactory/src/aifactory/providers/git.py` | `run_bytes`, `hash_blob`, `blob_at`, `read_blob`, `commit_tree_with`, `push_ref`, `remote_tip`, `count_commits`, `next_numbered_branch` |
| `aifactory/src/aifactory/config/commit.py` | `plan_config_commit`, `commit_config`, `pull_config`, `ConfigCommitError` |
| `aifactory/src/aifactory/run/store.py` | `TaskRunStore.live_runs()` a `live_runs_locked()` (běhy `running` s živým pid; mrtvé přejdou na `aborted`) |
| `aifactory/src/aifactory/cli.py` | podpříkazy `config commit` a `config pull` |
| `aifactory/src/aifactory/skill/skill.md`, `skill/codes.py` | popis příkazů a nové kódy |
| `aifactory/tests/config/test_config_publish.py`, `tests/providers/test_providers_publish.py`, `tests/test_skill.py` | testy |

## Tok `config commit`

1. **Plán**: cesty z `config_changes`, tedy jen sdílená konfigurace (`config.yaml`,
   `agents.yaml`, `roles.yaml`, `prompts/`, `workflows/`, nikdy `local.yaml`). Každý soubor má
   `path`, `action` (`create` | `modify` | `delete`), `old_blob`, `mode`, `diff` proti base
   a `content` (text, nebo `null` s `binary: true`). Plán obsahuje i `blockers` a `digest`.
2. **Digest**: sha256 přes jméno base, sha base a u každé cesty přes cestu, původní blob a nový
   obsah. Cíl ani zpráva commitu do něj nepatří. `--expect` s jiným digestem vrátí
   `plan_changed`. Kontroluje se dřív než „nic ke commitu“.
3. **Blokátory**: `invalid_config`, když pracovní strom neprojde `load_config`. U přímého cíle
   navíc `not_on_base`, `run_in_progress` a s remote (a neprázdným plánem) po `git fetch` base
   `base_behind` (remote je napřed) nebo `base_diverged`. Bez změn se vrátí `committed: false`
   ještě před blokátory.
4. **Commit bez checkoutu** (`git.commit_tree_with`): dočasný `GIT_INDEX_FILE`, `read-tree` base,
   `update-index --cacheinfo` / `--force-remove`, `write-tree`, `commit-tree`. Skutečný index,
   HEAD ani cizí staged a unstaged práce se nemění. Výchozí zpráva je
   `config: N file(s) from factory`.
5. **Přímý cíl** (`publish_direct`): když se lokální base mezitím pohnula, vrátí `base_moved`.
   Pak `git push <remote> <sha>:refs/heads/<base>` bez force. Odmítnutý push vrátí
   `push_failed` a refy, index ani soubory se nezmění. Po úspěšném push (nebo hned, když remote
   není) se pod `TaskRunStore.serialized()` znovu ověří, že nic neběží a base je pořád na sha
   z plánu. Pak se stagnou plánované cesty, které už v checkoutu mají plánovaný obsah, a
   `update-ref` posune base fast-forwardem. Selhání posunu skončí jen varováním (`advanced:
   false`, rada `run factory config pull`), nic se nevrací zpět.
6. **`--pr`** (`publish_pr`): commit dostane větev `factory-config/<n>`, tedy první číslo volné
   lokálně, ve sledovaných refech i na remote. Následuje `GitProvider.push` a `create_pr`. Když
   push selže, větev se smaže. Base ani hlavní checkout se nemění.

Výstup `data`: plán (`base`, `base_sha`, `target`, `digest`, `files`, `blockers`), dál
`paths`, `dry_run`, `committed`, `commit`, `pushed`, `advanced`, `branch` a
`pr` (`{id, url, branch}` | `null`).

## `config pull`

`git fetch` base. Když je remote napřed, lokální base se posune (`merge --ff-only` v checkoutu
na base, jinak `update-ref`) pod zámkem trace DB a jen když nic neběží. Když je lokální base
napřed, nic se nestane a výsledek varuje. Odmítne a nic nezmění při `base_diverged`,
`dirty_base` (sledované změny v checkoutu na base), `run_in_progress` a `no_remote`. Chyba gitu
vrátí `pull_failed`. `data`: `base`, `remote`, `before`, `after`, `updated`.

## Kódy

Nové: `base_behind`, `base_diverged`, `run_in_progress`, `plan_changed`, `no_remote`,
`pull_failed`. `not_on_base` a `commit_failed` teď platí pro backlog i config commit.
Použité stávající kódy: `push_failed`, `base_moved`, `dirty_base`, `unknown_base`,
`invalid_config`.

## Ověření

```
just test        # mj. tests/config/test_config_publish.py, tests/providers/test_providers_publish.py
just typecheck
just lint
```

Testy pracují s holým remote v `tmp_path`. Pokrývají commit a push, odmítnutý push přes
`pre-receive` hook (bajtově stejné refy, index a soubory), `base_behind`/`base_diverged`,
`plan_changed`, živý a mrtvý běh, přežití cizí staged práce, repo bez remote, `not_on_base`,
neplatný strom, prázdný plán, PR přes `gh_fake`, `config pull` (fast-forward, rozejití,
špinavý checkout, běh, bez remote), `commit_tree_with`, push bez force a digest.

Ruční vyzkoušení:
`factory config commit --dry-run --json`, potom `factory config commit --expect <digest> --json`.
