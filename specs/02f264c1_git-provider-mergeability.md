# Plán 2.10 — `GitProvider` (github, local) a mergeability v `aifactory`

## Cíl

Přenést rozhraní `GitProvider` a providery `local` a `github` (přes `gh`) z prototypu
(`prototype/src/haifa_proto/providers/`, `prototype/src/haifa_proto/gitops.py`) do
`aifactory/src/aifactory/providers/`. Proti prototypu oddělit **stav PR**
(`open`, `merged`, `closed`) od **mergeability** (`mergeable`, `conflict`, `unknown`),
opakovat dotaz na `unknown` s omezeným počtem pokusů a hlásit konflikt při merge
jako chybu `conflict` (ne `merge_failed`).

Pevná omezení: `vendor/` a `prototype/` se NEMĚNÍ (jen se z nich čte / kopíruje). Testy
nevolají síť (github jen proti falešnému `gh`, local jen proti dočasným repům).

Mimo rozsah: Azure DevOps (2.11), tok approve/return/úklid (2.12), napojení na
`factory task run` (2.12). Metody `approve`, `update_pr`, `merged_prs` z prototypu se
teď NEPŘENÁŠEJÍ (přijdou s 2.12).

## Výchozí stav (ověřeno)

- `aifactory/src/aifactory/config/settings.py`: `ProjectSettings` už má
  `git_provider: Literal["local", "github", "azure"] = "local"`,
  `merge_strategy: Literal["squash", "merge"] = "squash"`, `base = "main"`,
  `remote = "origin"`. Konfiguraci se tedy nic přidávat nemusí.
- `aifactory/src/aifactory/run/gitops.py` má vlastní `git`/`git_ok` (chyby jako
  `RuntimeError` / `TaskRunError`) a `BRANCH_PREFIX`. Providery na něm nezávisí, mají
  vlastní modul `providers/git.py` (viz níže), aby balík `providers` neimportoval `run`.
- Testy v `aifactory/tests/<oblast>/` nejsou balíčky; pomocné moduly (`harness_fakes.py`,
  `run_repo.py`) se importují jménem ze stejného adresáře. Stejně udělat `gh_fake.py`.
- Git identita v testech se nastavuje v repu (`git config user.email ...`,
  `commit.gpgsign false`) — viz `tests/run/run_repo.py`.
- Příkazy: `just test`, `just typecheck` (mypy strict přes `src` a `tests`),
  `just lint` (ruff check + ruff format --check, řádek 100).

## Soubory

Nové:
- `aifactory/src/aifactory/providers/__init__.py` — `get_provider`, reexporty.
- `aifactory/src/aifactory/providers/base.py` — konstanty, dataclassy, chyby, ABC.
- `aifactory/src/aifactory/providers/git.py` — git operace pro providery (z `gitops.py`).
- `aifactory/src/aifactory/providers/local.py` — `LocalProvider`.
- `aifactory/src/aifactory/providers/github.py` — `GhCli`, `GitHubProvider`.
- `aifactory/tests/providers/gh_fake.py` — falešný `gh` (převzít z `prototype/tests/gh_fake.py`).
- `aifactory/tests/providers/conftest.py` — session fixture, která fake `gh` jednou zapíše
  do sdíleného adresáře a „zahřeje“ prvním spuštěním (macOS první exec nového souboru trvá).
- `aifactory/tests/providers/provider_repo.py` — pomocník: dočasné repo + bare remote.
- `aifactory/tests/providers/test_providers_select.py`
- `aifactory/tests/providers/test_providers_local.py`
- `aifactory/tests/providers/test_providers_github.py`

Beze změny: `config/settings.py` (pole už existují), `vendor/`, `prototype/`.
Volitelně aktualizovat `BACKLOG.md` řádek 2.10 NEDĚLAT — to řeší orchestrace.

## Návrh API

### `providers/base.py`

```python
OPEN, MERGED, CLOSED = "open", "merged", "closed"
PR_STATES = (OPEN, MERGED, CLOSED)
MERGEABLE, CONFLICT, UNKNOWN = "mergeable", "conflict", "unknown"
MERGEABILITY = (MERGEABLE, CONFLICT, UNKNOWN)
STRATEGIES = ("squash", "merge")
BRANCH_PREFIX = "factory/"

class ProviderError(Exception):          # code + message, jako v prototypu gitops.ProviderError
    def __init__(self, code: str, message: str) -> None: ...

class MergeFailed(ProviderError):
    """code je `merge_failed` nebo `conflict`."""

@dataclass(frozen=True)
class PullRequest:  id: str; url: str; branch: str; base: str; title: str

@dataclass(frozen=True)
class PrStatus:
    state: str                      # OPEN | MERGED | CLOSED
    mergeability: str = UNKNOWN     # MERGEABLE | CONFLICT | UNKNOWN; pro MERGED/CLOSED vždy UNKNOWN
    head_sha: str | None = None
    merge_sha: str | None = None

class GitProvider(abc.ABC):
    name: str = ""
    def __init__(self, root: Path, settings: ProjectSettings) -> None
    def push(self, worktree: Path, branch: str) -> None       # git.push(worktree, settings.remote, branch)
    @abstractmethod create_pr(self, branch, title, body) -> PullRequest
    @abstractmethod status(self, pr) -> PrStatus
    @abstractmethod merge(self, pr, head_sha: str, subject: str, strategy: str | None = None) -> str | None
        # strategy None -> self.settings.merge_strategy (výchozí squash, D9);
        # neznámá strategie -> ProviderError("invalid_strategy", ...)
        # konflikt -> MergeFailed("conflict"), jiné selhání -> MergeFailed("merge_failed")
    @abstractmethod comment(self, pr, body: str) -> None
```

Pomocná metoda v ABC: `def _strategy(self, strategy: str | None) -> str`.
`task_id_from_branch` z prototypu přenést také (malé, užitečné pro 2.12), s testem.

### `providers/git.py`

Zkopírovat z `prototype/src/haifa_proto/gitops.py` jen: `_run`, `git`, `git_ok`,
`rev_parse`, `is_ancestor`, `has_remote`, `remote_url`, `push`, `checked_out_in`,
`advance_branch`, `remove_worktree`, `detached_worktree`, `trial_merge`, `merge_commit`.
`ProviderError` importovat z `providers.base` (ne definovat tady). Prefix dočasného
adresáře `aifactory-merge-`. `merge_commit` při konfliktu vyhazuje
`ProviderError("conflict", ...)` jako v prototypu. `trial_merge` a `merge_commit`
používají dočasný detached worktree, takže nesahají na checkout operátora.

### `providers/local.py` — `LocalProvider`

Přenést z prototypu s úpravami:
- `create_pr`: PR = větev; `id=branch`, `url = "<remote_url>#<branch>"` nebo `local:<branch>`.
- `push`: jen když remote existuje.
- `status`: větev neexistuje → `PrStatus(CLOSED)`; neexistuje base →
  `ProviderError("unknown_base")`; tip je předkem base → `PrStatus(MERGED, head_sha=tip)`;
  jinak `PrStatus(OPEN, MERGEABLE|CONFLICT podle trial_merge, head_sha=tip)`.
  Local nikdy nevrací `UNKNOWN` pro otevřený PR (počítá to lokálně).
- `merge(pr, head_sha, subject, strategy=None)`: strategie přes `_strategy`; base
  neexistuje nebo tip ≠ `head_sha` → `MergeFailed("merge_failed")`;
  `git.merge_commit` s `code == "conflict"` → `MergeFailed("conflict", ...)`, jiné
  `ProviderError` → `MergeFailed("merge_failed", ...)`; pak `advance_branch`, a pokud je
  remote, `git.push(root, remote, base)`. Vrací sha nového commitu.
- `comment`: no-op (není komu).

### `providers/github.py` — `GhCli`, `GitHubProvider`

- `GhCli` z prototypu; spustitelný soubor `executable or os.environ.get("AIFACTORY_GH") or "gh"`.
  `FileNotFoundError` → `ProviderError("gh_missing")`; nenulový exit → `GhError`
  (`code="gh_failed"`, drží `stderr`). Těla přes stdin (`--body-file -`).
- `GitHubProvider.__init__(root, settings, gh: GhCli | None = None, *, attempts: int = 5,
  delay: float = 2.0, sleep: Callable[[float], None] = time.sleep)`.
  `attempts >= 1` (jinak `ValueError`). Modulové konstanty `UNKNOWN_ATTEMPTS = 5`,
  `UNKNOWN_DELAY = 2.0`.
- `_status_once(pr)`: `gh pr view <id> --json state,mergeable,headRefOid,mergeCommit`;
  mapování: `MERGED` → `PrStatus(MERGED, head_sha, merge_sha=mergeCommit.oid)`;
  `CLOSED` → `PrStatus(CLOSED, head_sha)`; jinak `OPEN` s mergeability
  `MERGEABLE`→mergeable, `CONFLICTING`→conflict, cokoli jiného (`UNKNOWN`, chybí) →unknown.
  Ne-objekt JSON → `ProviderError("gh_failed")`.
- `status(pr)`: volá `_status_once` nejvýš `attempts`-krát; opakuje jen dokud
  `state == OPEN and mergeability == UNKNOWN`; mezi pokusy `sleep(delay)` (konstantní
  prodleva stačí; žádný sleep po posledním pokusu). Po vyčerpání vrátí `OPEN/UNKNOWN`.
- `create_pr`: jako prototyp (`gh pr create --base <base> --head <branch> --title <t>
  --body-file -`, číslo z poslední neprázdné řádky URL; bez URL → `ProviderError("gh_failed")`).
- `merge(pr, head_sha, subject, strategy=None)`:
  1. `s = self._strategy(strategy)`.
  2. `st = self.status(pr)` (s opakováním). `st.state == MERGED` →
     `MergeFailed("merge_failed", "already merged")`? — NE: vrátit `st.merge_sha`
     (idempotence). `CLOSED` → `MergeFailed("merge_failed", "PR is closed")`.
     `st.mergeability == CONFLICT` → `MergeFailed("conflict", ...)` a `gh pr merge` se nevolá.
     `UNKNOWN` po vyčerpání pokusů → pokračovat na merge (hosting rozhodne).
  3. `gh pr merge <id> --<s> --match-head-commit <head_sha> --subject <subject>`.
  4. Při `GhError`: jeden `_status_once`; je-li `OPEN/CONFLICT` → `MergeFailed("conflict")`,
     jinak `MergeFailed("merge_failed", stderr)`. (Chyba samotného dotazu na stav se
     spolkne a hlásí se `merge_failed` s původním stderr.)
  5. Po úspěchu vrátit `self._status_once(pr).merge_sha`.
- `comment`: `gh pr comment <id> --body-file -` se stdin.

### `providers/__init__.py`

```python
def get_provider(settings: ProjectSettings, root: Path) -> GitProvider:
    "local" -> LocalProvider; "github" -> GitHubProvider;
    "azure" -> ProviderError("unsupported_provider", "azure lands in 2.11")
    jinak -> ProviderError("invalid_config", ...)
```
Reexportovat konstanty, `GitProvider`, `PullRequest`, `PrStatus`, `ProviderError`,
`MergeFailed`, `get_provider` (`__all__`).

## Testy (bez sítě)

### `tests/providers/gh_fake.py` + `conftest.py`
Převzít `prototype/tests/gh_fake.py` (script, `GhLog`, `reply`, `install_fake_gh`,
`write_fake_gh`, `shared_bin_dir`) s přejmenováním env na `AIFACTORY_FAKE_GH_STATE`
a mazáním `AIFACTORY_GH`. Seznam odpovědí se odebírá postupně, poslední se opakuje —
na tom stojí scénář `unknown` → `conflict`. `conftest.py`: session autouse fixture,
která zavolá `write_fake_gh(shared_bin_dir())` a jednou spustí `gh --version` s prázdným
stavem (viz `prototype/tests/conftest.py` řádky ~115–127). Typy plně anotovat (mypy strict).

### `tests/providers/provider_repo.py`
`make_repo(tmp_path, *, with_remote: bool) -> Path`: `git init -b main`, identita,
`commit.gpgsign false`, počáteční commit (`a.txt`); s remote: `git init --bare`
`tmp_path/"origin.git"`, `git remote add origin`, `git push -u origin main`.
Pomocníci `git(...)`, `commit_file(repo, branch, path, text, msg) -> sha` (vytvoří/přepne
větev, zapíše, commitne, vrátí se na main). GIT env izolovat jako `config/config_repo.py`
(`GIT_CONFIG_GLOBAL=os.devnull`, `GIT_CONFIG_NOSYSTEM=1`) přes `monkeypatch`.

### `test_providers_select.py`
- `.factory/config.yaml` s `git_provider: github` načtený přes
  `parse_project_settings` (nebo `ProjectSettings.model_validate(yaml)`) → `get_provider`
  vrací `GitHubProvider`; bez klíče → `LocalProvider`; `azure` → `ProviderError`
  s `code == "unsupported_provider"`; neplatná hodnota → chyba validace konfigurace.
- `merge_strategy` chybí → `settings.merge_strategy == "squash"`.
- `task_id_from_branch`: `factory/M01-S01-T01-2` → `M01-S01-T01`; `main`, `factory/x` → None.

### `test_providers_local.py` (proti dočasnému bare repu)
- `create_pr` → id = větev, url končí `origin.git#<branch>`; bez remote `local:<branch>`.
- `push` pošle větev do bare (`git -C origin.git rev-parse refs/heads/<branch>`).
- `status`: čistá větev → `OPEN/MERGEABLE`; obě strany mění tentýž řádek → `OPEN/CONFLICT`;
  smazaná větev → `CLOSED`; po merge → `MERGED`. Po `status` zůstává checkout čistý
  a `git worktree list` má jen hlavní checkout.
- `merge` bez `strategy` a výchozí konfigurací → na base přibude právě 1 commit s jedním
  rodičem a předmětem `subject`; bare `main` == lokální `main`.
- `merge_strategy="merge"` v settings → merge commit se 2 rodiči.
- explicitní `strategy="merge"` přebije konfiguraci.
- konflikt → `MergeFailed` s `code == "conflict"`, base i bare beze změny.
- `head_sha` ≠ tip → `MergeFailed` s `code == "merge_failed"`.
- neplatná strategie → `ProviderError("invalid_strategy")`.
- `comment` je no-op.

### `test_providers_github.py` (falešný `gh`)
Provider stavět `GitHubProvider(tmp_path, ProjectSettings(git_provider="github"), sleep=sleeps.append)`,
aby testy nečekaly; ověřovat přesné argv a stdin z `GhLog`.
- `create_pr` argv + stdin + cwd; bez URL → `gh_failed`.
- `status` parametrizovaně: MERGEABLE, CONFLICTING, MERGED (merge_sha), CLOSED.
- **unknown se opakuje**: `pr view` = `[UNKNOWN, UNKNOWN, MERGEABLE]` → `OPEN/MERGEABLE`,
  3 volání `pr view`, `sleeps == [delay, delay]`.
- **unknown se vyčerpá**: vždy `UNKNOWN`, `attempts=3` → `OPEN/UNKNOWN`, přesně 3 volání, 2 sleepy.
- **unknown, pak conflict** (Done means): `pr view` = `[UNKNOWN, CONFLICTING]`;
  `status` → `OPEN/CONFLICT`; `merge(...)` → `MergeFailed` s `code == "conflict"`
  a v logu není žádné `pr merge`.
- merge výchozí strategií → argv obsahuje `--squash`, `--match-head-commit <sha>`,
  `--subject <s>`; vrací `mergeCommit.oid` z následného `pr view`.
- `merge_strategy="merge"` v settings → `--merge`.
- `pr merge` selže (exit 1) a následný `pr view` říká CONFLICTING → `code == "conflict"`;
  následný `pr view` MERGEABLE → `code == "merge_failed"` se stderr ve zprávě.
- PR už MERGED → merge vrátí merge_sha bez `pr merge`; CLOSED → `merge_failed`.
- `comment` argv `["pr","comment","7","--body-file","-"]` a stdin.
- chybějící `gh` (`GhCli(tmp_path, executable=str(tmp_path/"nope"))`) → `gh_missing`.
- `attempts=0` → `ValueError`.

## Postup

1. Vytvořit `providers/base.py`, `providers/git.py`, `local.py`, `github.py`, `__init__.py`.
2. Napsat testy a pomocníky v `aifactory/tests/providers/`.
3. Spustit `just test tests/providers`, pak celé `just test`, `just typecheck`, `just lint`
   (při formátovacích chybách `cd aifactory && uv run ruff format src/aifactory/providers tests/providers`).
4. Ověřit `git status`, že se `vendor/` a `prototype/` nezměnily.

## Ověření (Done means)

- `just test` — zelené, včetně nových testů; žádný test nevolá síť.
- `just typecheck` — mypy strict bez chyb.
- `just lint` — ruff check i format čisté.
- `git diff --stat -- vendor prototype` je prázdné.
