# 2.10 — `GitProvider` (`local`, `github`) a mergeability v `aifactory`

## Co se změnilo a proč

Do `aifactory` přibyl balík `aifactory.providers`: rozhraní `GitProvider` a dva providery
přenesené z prototypu — `local` (PR = větev, merge = lokální merge do base) a `github`
(PR přes CLI `gh`). Oproti prototypu je **stav PR** (`open` / `merged` / `closed`) oddělený
od **mergeability** (`mergeable` / `conflict` / `unknown`). Mergeability má smysl jen
u otevřeného PR, u `merged`/`closed` je vždy `unknown`.

Hlavní body:

- **Rozhraní** (`base.py`): `create_pr`, `status`, `merge(pr, head_sha, subject, strategy=None)`,
  `comment`, plus výchozí `push` (obyčejný `git push -u <remote> <branch>`).
  Datové typy `PullRequest`, `PrStatus`, chyby `ProviderError(code, message)` a `MergeFailed`.
- **Strategie merge**: když `strategy` není zadaná, použije se `settings.merge_strategy`
  (výchozí `squash`, D9). Povolené hodnoty jsou jen `squash` a `merge`, jiná hodnota
  vyhodí `ProviderError("invalid_strategy")`.
- **Konflikt ≠ selhání**: `merge` vyhodí `MergeFailed` s `code == "conflict"` při konfliktu
  a s `code == "merge_failed"` při jakémkoli jiném selhání.
- **Opakování `unknown`** (`github.py`): GitHub počítá mergeability líně. `status` proto
  při odpovědi „otevřený PR a `unknown`“ opakuje `gh pr view` až `attempts`krát
  (výchozí `UNKNOWN_ATTEMPTS = 5`) s pauzou `delay` (výchozí `UNKNOWN_DELAY = 2.0` s).
  Pokud pokusy dojdou, vrátí `unknown`. `sleep` lze injektovat, `attempts < 1` vyhodí `ValueError`.
- **Výběr provideru**: `get_provider(settings, root)` čte `git_provider` z `.factory/config.yaml`
  (`ProjectSettings`, výchozí `local`). Pro `azure` vrací `ProviderError("unsupported_provider")`,
  protože Azure je až v 2.11.
- `task_id_from_branch("factory/<task-id>-<n>")` → `<task-id>`, u jiných názvů `None`.

Konfigurace se neměnila: pole `git_provider`, `merge_strategy`, `base` a `remote` už
v `ProjectSettings` existovala.

## Soubory

Zdrojový kód (`aifactory/src/aifactory/providers/`):

| Soubor | Obsah |
|---|---|
| `__init__.py` | `get_provider` a reexporty konstant, typů a chyb |
| `base.py` | konstanty stavů/mergeability/strategií, `ProviderError`, `MergeFailed`, `PullRequest`, `PrStatus`, ABC `GitProvider`, `task_id_from_branch` |
| `git.py` | git operace převzaté z prototypového `gitops`: `push`, `rev_parse`, `advance_branch`, `detached_worktree`, `trial_merge`, `merge_commit` atd. |
| `local.py` | `LocalProvider` |
| `github.py` | `GhCli` (jediné místo, kde se spouští `gh`) a `GitHubProvider` |

Testy (`aifactory/tests/providers/`): `gh_fake.py`, `provider_repo.py`,
`test_providers_local.py`, `test_providers_github.py`, `test_providers_select.py`.
Plán: `specs/02f264c1_git-provider-mergeability.md`.

## Chování providerů

**`local`**
- `create_pr`: `id` je název větve, `url` je `<remote_url>#<branch>`, nebo `local:<branch>`,
  pokud remote není nastavený.
- `push` a push base po merge proběhnou jen tehdy, když existuje remote.
- `status`: když větev neexistuje, vrátí `closed`. Když je tip předkem base, vrátí `merged`.
  Jinak vrátí `open` a mergeability určí zkušební merge (`trial_merge`) v dočasném
  detached worktree. U `local` tedy nikdy nevznikne `unknown`. Když base neexistuje,
  vyhodí `ProviderError("unknown_base")`.
- `merge`: když se tip větve liší od `head_sha`, vrátí `merge_failed`. Squash nebo merge
  commit vznikne v dočasném worktree (`merge_commit`), takže checkout operátora zůstane
  nedotčený. Base se pak posune přes `advance_branch`: `merge --ff-only` tam, kde je base
  checked out, jinak `update-ref`.
- `comment` nic nedělá.

**`github`**
- `gh` se hledá na `PATH`, případně přes `$AIFACTORY_GH`. Když chybí, vyhodí
  `ProviderError("gh_missing")`. Těla PR a komentářů jdou na stdin (`--body-file -`).
- `create_pr` volá `gh pr create --base … --head … --title …`. Číslo PR se čte z URL
  na výstupu; když tam URL není, vyhodí `gh_failed`.
- `status` volá `gh pr view <n> --json state,mergeable,headRefOid,mergeCommit`.
  Hodnota `CONFLICTING` odpovídá `conflict`.
- `merge` nejdřív zavolá `status` (včetně opakování `unknown`). U stavu `merged` vrátí
  merge SHA bez dalšího volání a u `closed` vyhodí `merge_failed`. Při `conflict` vyhodí
  `conflict` a `gh pr merge` vůbec nezavolá. Jinak spustí
  `gh pr merge <n> --<strategy> --match-head-commit <sha> --subject …`. Když `gh` selže,
  provider se jednou znovu zeptá na stav: pokud je PR teď v konfliktu, vrátí `conflict`,
  jinak `merge_failed`.

## Použití

```python
from aifactory.providers import get_provider, MergeFailed

provider = get_provider(settings, repo_root)   # settings = ProjectSettings z .factory/config.yaml
pr = provider.create_pr("factory/T01-1", "T01: …", body)
st = provider.status(pr)                        # st.state, st.mergeability, st.head_sha
try:
    provider.merge(pr, st.head_sha, "T01: …")   # strategie z configu (squash)
except MergeFailed as e:
    e.code  # "conflict" | "merge_failed"
```

```yaml
# .factory/config.yaml
git_provider: github      # local (výchozí) | github
merge_strategy: squash    # squash (výchozí) | merge
```

## Ověření

Spusťte `just test`, `just typecheck` a `just lint`.

- `test_providers_local.py` testuje proti dočasnému repu s bare `origin.git`: squash
  (výchozí) i `merge` z configu, přebití strategie parametrem, konflikt (base ani remote
  se nepohnou, checkout zůstane čistý), posunutý head, neplatnou strategii a stav
  po smazání větve.
- `test_providers_github.py` testuje proti falešnému `gh`. Ten zapisuje argv a stdin
  do `calls.jsonl` a odpovídá podle `responses.json`; seznam odpovědí se postupně odebírá.
  Pokryté případy:
  - opakování `unknown` → `mergeable` (dvě pauzy),
  - vyčerpání pokusů,
  - `unknown` → `conflict`, kdy `merge` vyhodí `conflict` bez volání `gh pr merge`,
  - neúspěšné `gh pr merge`, po kterém stav ukáže konflikt → `conflict`.
- `test_providers_select.py` ověřuje výběr provideru z YAML, výchozí `local`, `azure`
  jako nepodporovaný, neplatnou hodnotu jako chybu konfigurace a výchozí `squash`.

Testy nevolají síť. Falešný `gh` se zapíše do sdíleného adresáře v tempu
(klíčovaného obsahem skriptu) a jednou se „zahřeje“ fixturou `_shared_gh` na úrovni
modulu. Na macOS totiž první spuštění nového souboru trvá dlouho.
