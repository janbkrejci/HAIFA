# Plán: task 1.6 — pull request, schválení a merge (`GitProvider` local + github)

Zdroj: `backlog/phase-01/task-1.6.md`, `docs/product-brief.md` (sekce „Běh úkolu“ kroky 4–7, „Backlog v markdownu“ – stav, D6, D8, D9, D11).
Navazuje na 1.5 (`prototype/src/haifa_proto/run.py`, spec `specs/4a10f3b6_task-run-worktree.md`).

## Pevná omezení (nepřekročit)

- `status: done` se do souboru tasku zapisuje **jen** commitem do PR větve při `task approve` (a výjimečně commitem do `base` v `backlog sync` pro PR mergnutý mimo HAIFA). `task run` ani `task return` soubor tasku nikdy nemění.
- Testy nevolají model (falešný harness z `tests/workflow_fakes.py`) ani skutečný GitHub (falešné `gh` na `PATH`).
- `vendor/` se neupravuje. Vše v `prototype/`.
- Mimo rozsah: Azure DevOps, auto-continue, web, rebase/`resolve` workflow u konfliktu (konflikt jen ohlásit).
- Lokální git je 2.37 → **nepoužívat** `git merge-tree --write-tree` (od 2.38). Zkušební merge dělat v dočasném detached worktree.

## Přehled změn

| Soubor | Co |
| --- | --- |
| `src/haifa_proto/config.py` | nové klíče `git_provider`, `merge_strategy`, `require_review`, `remote` |
| `src/haifa_proto/providers/__init__.py` | `get_provider(config, root) -> GitProvider` |
| `src/haifa_proto/providers/base.py` | datové typy + abstraktní `GitProvider`, výjimky |
| `src/haifa_proto/providers/local.py` | `LocalProvider` |
| `src/haifa_proto/providers/github.py` | `GitHubProvider` + jediné místo volání `gh` (`GhCli`) |
| `src/haifa_proto/gitops.py` (nový) | sdílené git operace: `git()`, push, commit do `base` přes dočasný worktree, posun `base`, úklid worktree |
| `src/haifa_proto/taskfile.py` (nový) | úprava souboru tasku: `status: done` + záznam do `## Běhy` |
| `src/haifa_proto/prbody.py` (nový) | sestavení titulku a popisu PR z tasku, `WorkflowRun` a trace |
| `src/haifa_proto/review.py` (nový) | `approve_task`, `return_task`, `sync_backlog` |
| `src/haifa_proto/run.py` | tabulka `task_prs`, refaktor `run_task` (běh na existující větvi), push + PR po `accept` |
| `src/haifa_proto/cli.py` | `task approve`, `task return`, `backlog sync`, PR v `task show` |
| `tests/…` | viz sekce Testy |
| `app_docs/1ecab8c6_task-pr-approval.md` | dokumentace (stejný styl jako `app_docs/4a10f3b6_task-run-worktree.md`) |

Rozdělení do modulů je doporučení; `run.py` má už 600 řádků, proto nové soubory. Importy mezi moduly nesmí být cyklické: `gitops` ← `providers` ← `run` ← `review` ← `cli`. `_git`/`_git_ok` z `run.py` přesunout do `gitops.py` (v `run.py` ponechat alias `_git = gitops.git`, aby se nerozbily testy, pokud je importují — `grep -rn "_git" tests/` před přesunem).

---

## 1. Konfigurace (`config.py`)

Do `FactoryConfig` přidat (flat klíče v `.factory/config.yaml`, všechny volitelné):

```python
git_provider: str = "local"        # "local" | "github"
merge_strategy: str = "squash"     # "squash" | "merge"
require_review: bool = False
remote: str = "origin"             # jméno git remote pro push
```

Validace v `load_config`: neznámá hodnota `git_provider`/`merge_strategy` → `ConfigError(f"{path}: 'git_provider' must be one of local, github")`; `require_review` musí být `bool`; `remote` neprázdný string. Testy v `tests/test_config.py` (výchozí hodnoty, platné hodnoty, chybné hodnoty).

## 2. `providers/base.py`

```python
OPEN, MERGEABLE, CONFLICT, MERGED, CLOSED = "open", "mergeable", "conflict", "merged", "closed"
# "open" = otevřený, mergnutelnost neznámá (GitHub UNKNOWN); MERGEABLE/CONFLICT jsou zpřesnění otevřeného PR.
STRATEGIES = ("squash", "merge")

@dataclass
class PullRequest:
    id: str            # github: číslo PR jako string; local: jméno větve
    url: str           # github: html url; local: "<remote-url>#<branch>" nebo "local:<branch>" bez remote
    branch: str
    base: str
    title: str

@dataclass
class PrStatus:
    state: str          # jedna z konstant výše
    head_sha: str | None = None
    merge_sha: str | None = None

@dataclass
class MergedPr:        # pro backlog sync
    id: str; url: str; branch: str; merge_sha: str | None

class ProviderError(Exception):
    def __init__(self, code: str, message: str): ...   # jako TaskRunError: .code, .message
class ReviewRejected(ProviderError): ...   # code "review_rejected"
class MergeFailed(ProviderError): ...      # code "merge_failed" / "conflict"

class GitProvider(abc.ABC):
    name: str
    def __init__(self, root: Path, config: FactoryConfig) -> None
    def push(self, worktree: Path, branch: str) -> None          # společná impl. v base: gitops.push, local ji přepíše (bez remote = no-op)
    @abstractmethod def create_pr(self, branch, title, body) -> PullRequest
    @abstractmethod def update_pr(self, pr: PullRequest, body: str) -> None
    @abstractmethod def status(self, pr: PullRequest) -> PrStatus
    @abstractmethod def approve(self, pr: PullRequest, body: str) -> None     # ReviewRejected při odmítnutí
    @abstractmethod def merge(self, pr: PullRequest, strategy: str, head_sha: str, subject: str) -> str | None  # vrací merge sha, pokud je známé
    @abstractmethod def comment(self, pr: PullRequest, body: str) -> None
    @abstractmethod def merged_prs(self) -> list[MergedPr]                     # PR z větví `factory/` mergnuté do base
```

`providers/__init__.py`: `get_provider(config, root)` podle `config.git_provider`. Tuto funkci volají `run.py` i `review.py`; testy ji mohou monkeypatchnout.

Pomocná funkce `task_id_from_branch(branch) -> str | None`: `factory/<task-id>-<n>` → `<task-id>` (rsplit na posledním `-`, suffix musí být číslo). Dát do `base.py`.

## 3. `gitops.py`

- `git(cwd, *args, input: str | None = None) -> str` (přesun `_git`), `git_ok(...)`.
- `has_remote(root, remote) -> bool` (`git remote get-url <remote>` exit 0).
- `push(root_or_worktree, remote, branch)`: `git push -u <remote> <branch>`; chyba → `ProviderError("push_failed", stderr)`.
- `checked_out_in(root, branch) -> Path | None`: z `git worktree list --porcelain` najde worktree, kde je `refs/heads/<branch>` checkoutnutá.
- `advance_branch(root, branch, new_sha, old_sha)`: posune větev (`base`) na `new_sha`, který je potomkem `old_sha`:
  - je-li větev checkoutnutá v nějakém worktree W (typicky hlavní checkout): `git -C W merge --ff-only <new_sha>` (aktualizuje i pracovní strom; když selže kvůli rozpracovaným souborům → `ProviderError("dirty_base", …)`, nic se nezměnilo);
  - jinak `git update-ref refs/heads/<branch> <new_sha> <old_sha>`.
- `commit_on_detached(root, start_sha, edit: Callable[[Path], None], message) -> str`: `git worktree add --detach <tmp> <start_sha>` (tmp v `tempfile.mkdtemp`, mimo repo), zavolá `edit(tmp)`, `git add -A && git commit -m`, vrátí sha, v `finally` `git worktree remove --force <tmp>`. Použije se pro `backlog sync` a lokální merge.
- `trial_merge(root, base_sha, branch_sha) -> bool`: detached worktree na `base_sha`, `git merge --no-commit --no-ff <branch_sha>`; exit ≠ 0 → konflikt (`git merge --abort`), odstranit worktree. Vrací `True` = čistě mergnutelné.
- `remove_worktree(root, path)`: `git worktree remove --force <path>` pokud existuje, pak `git worktree prune`. Chybějící adresář není chyba.
- Commity dělané HAIFA musí fungovat i bez globální git identity — v testech je identita nastavená v repu (`make_engine_env`), víc neřešit.

## 4. `providers/local.py` — `LocalProvider`

„PR je větev, schválení je lokální merge do `base`.“ Stav PR se dopočítává z gitu + záznamu v `task_prs` (viz §6; provider dostane přístup přes `root`/`config` a volá `run.TaskPrStore`? — **ne**, aby nevznikl cyklus: provider stav z DB nečte, `review.py` ho kombinuje). Konkrétně:

- `push`: když `has_remote(root, config.remote)` → `git push -u`; jinak nic.
- `create_pr(branch, title, body)`: nic neposílá; vrací `PullRequest(id=branch, url=…, branch, base=config.base, title)`. `url` = `"<git remote get-url remote>#<branch>"` pokud remote existuje, jinak `"local:<branch>"`. Popis PR ukládá `run.py` do `task_prs.body` (tj. „PR“ má popis i lokálně).
- `update_pr`: no-op (tělo aktualizuje `run.py` v DB).
- `status(pr)`:
  - větev neexistuje → `CLOSED`;
  - tip větve je předek `base` (`git merge-base --is-ancestor tip base`) **a** větev má aspoň jeden commit navíc proti svému `base_sha` (to ověří volající; provider dostane jen větev → kontrola „má vlastní commity“ se dělá tak, že tip ≠ `git merge-base` s commitem, kde vznikla — jednodušeji: `review.py` volá `status` jen pro PR z `task_prs`, jehož `head_sha` ≠ `base_sha`) → `MERGED`;
  - jinak `trial_merge(root, base, tip)` → `MERGEABLE` / `CONFLICT`.
  - (Squash merge udělaný HAIFA stav nepozná z ancestry → `review.py` věří `task_prs.state == merged`.)
- `approve(pr, body)`: lokálně není komu poslat review → no-op (zapíše se jen komentář do DB, viz §6 `task_pr_comments` — volitelné, stačí no-op). `require_review: true` s local je povolené a je no-op.
- `merge(pr, strategy, head_sha, subject)`:
  1. `old = rev-parse base`; tip větve musí být `head_sha` (jinak `MergeFailed("merge_failed", "branch moved")`).
  2. `commit_on_detached`-varianta: detached worktree na `old`; `squash`: `git merge --squash <tip>` + `git commit -m "<subject>"`; `merge`: `git merge --no-ff -m "<subject>" <tip>`. Konflikt → `git merge --abort`/reset, `MergeFailed("conflict", …)`, `base` nezměněna.
  3. `advance_branch(root, base, new, old)`.
  4. má-li remote: `git push <remote> <base>` (chyba → `ProviderError("push_failed")`, lokální `base` už je posunutá — ohlásit).
  5. vrací `new`. Větev se nemaže (brief: větev maže hosting).
- `comment`: no-op (lokálně nemá kam; `review.py` poznámku návratu drží v `task_runs.note`).
- `merged_prs()`: pro každou lokální větev `refs/heads/factory/*` (a `refs/remotes/<remote>/factory/*`, pokud remote) s tipem, který je předek `base`, vrať `MergedPr(id=branch, url, branch, merge_sha=None)`. Filtr „má vlastní commity“ provede `review.sync_backlog` pomocí `task_prs`/`task_runs.base_sha` (tip ≠ base_sha běhu).

## 5. `providers/github.py` — `GitHubProvider`

Všechna volání `gh` jdou přes jednu třídu:

```python
class GhCli:
    def __init__(self, cwd: Path, executable: str = "gh") -> None
    def run(self, *args: str, stdin: str | None = None) -> str:
        # subprocess.run([executable, *args], cwd=cwd, input=stdin, capture_output=True, text=True)
        # exit != 0 -> GhError(args, returncode, stderr)  (GhError(ProviderError), code "gh_failed")
        # FileNotFoundError -> ProviderError("gh_missing", "gh is not installed or not on PATH")
    def json(self, *args: str) -> Any   # run + json.loads
```

`executable` = env `HAIFA_GH` nebo `"gh"` (volá se holým jménem, `PATH` řeší prostředí). Testy dávají falešné `gh` na začátek `PATH`.

Přesné argv (testy je ověřují 1:1):

| Operace | argv | stdin | výstup |
| --- | --- | --- | --- |
| `create_pr` | `pr create --base <base> --head <branch> --title <title> --body-file -` | body | stdout = URL; `id` = poslední segment URL (číslo) |
| `update_pr` | `pr edit <id> --body-file -` | body | – |
| `status` | `pr view <id> --json state,mergeable,headRefOid,mergeCommit` | – | JSON |
| `approve` | `pr review <id> --approve --body-file -` | body | exit≠0 → `ReviewRejected("review_rejected", stderr)` |
| `merge` | `pr merge <id> --squash` nebo `--merge`, `--match-head-commit <head_sha>`, `--subject <subject>` | – | exit≠0 → `MergeFailed("merge_failed", stderr)`; potom `status` pro `merge_sha` |
| `comment` | `pr comment <id> --body-file -` | body | – |
| `merged_prs` | `pr list --state merged --base <base> --json number,url,headRefName,mergeCommit --limit 200` | – | filtr `headRefName` začíná `factory/` |

Mapování `status`: `state` `MERGED`→`MERGED` (merge_sha = `mergeCommit.oid`), `CLOSED`→`CLOSED`, `OPEN` + `mergeable` `MERGEABLE`→`MERGEABLE`, `CONFLICTING`→`CONFLICT`, jinak `OPEN`. `head_sha` = `headRefOid`.

Push dělá git (`gitops.push`), ne `gh`. `--delete-branch` se nepoužívá (větev maže hosting dle nastavení).

## 6. `run.py` — PR po běhu, běh na existující větvi

### 6a. Tabulka `task_prs` (do `_SCHEMA`, trace DB hlavního checkoutu)

```sql
CREATE TABLE IF NOT EXISTS task_prs (
  task_id TEXT NOT NULL,
  branch TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  pr_id TEXT NOT NULL,
  url TEXT NOT NULL,
  base TEXT NOT NULL,
  base_sha TEXT NOT NULL,     -- base_sha prvního běhu na větvi
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  state TEXT NOT NULL,        -- open | merged | closed (poslední známý)
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  merged_at TEXT,
  merge_sha TEXT
);
CREATE INDEX IF NOT EXISTS task_prs_task ON task_prs(task_id);
```

`TaskRunStore` dostane metody: `save_pr(row)`, `update_pr(branch, **fields)`, `pr_for_branch(branch)`, `open_pr(task_id)` (nejnovější `state='open'`), `prs_for_task(task_id)`, `runs_on_branch(branch)`. Dataclass `TaskPrRow` s `to_json()`.

### 6b. Refaktor `run_task`

Rozdělit tělo na:

1. `_prepare(root, config, task_id, note, force, cfg, store) -> _Prepared` (task, backlog, scope, workflow, prompt, base_sha, cfg) — dnešní kontroly beze změny.
2. `_execute(root, config, prepared, store, *, branch: str | None, code) -> TaskRunResult`:
   - `branch is None` → dnešní chování (`next_branch`, `git worktree add -b <branch> <wt> <base_sha>`);
   - `branch` zadaná (return) → `git worktree add <wt> <branch>` (bez `-b`, checkout existující větve). `row.base_sha` = `base_sha` z `task_prs` (fork point), `row.branch` = `branch`.
3. Po `state == SUCCEEDED` zavolat `_publish(root, config, store, row, task, wf, provider)`:
   - `provider.push(worktree, branch)`;
   - existuje-li `task_prs` pro větev: nové tělo → `provider.update_pr`, `store.update_pr(body=…, updated_at=…)`;
   - jinak `provider.create_pr(branch, title, body)` → `store.save_pr(...)` se `state='open'`.
   - Výjimka `ProviderError` → **běh zůstává `succeeded`** (workflow prošlo), ale `TaskRunResult.pr_error = f"{code}: {message}"`, CLI vrátí exit 1 a vypíše chybu. Worktree zůstává.
4. `TaskRunResult` dostane pole `pr: TaskPrRow | None = None`, `pr_error: str | None = None`; `ok` = `state == SUCCEEDED and pr_error is None`.

Veřejné API: `run_task(repo, task_id, *, note=None, force=False, cfg=None, code=None, provider: GitProvider | None = None)` (provider pro testy; default `get_provider`), a nové `run_on_branch(repo, task_id, branch, *, note, cfg=None, code=None, provider=None)` pro `task return` (dependency check přeskočit — `force=True`; kontrola „neběží“ platí).

Aktualizovat docstring modulu (už se pushuje a zakládá PR; soubor tasku se stále nemění).

### 6c. Popis PR — `prbody.py`

`pr_title(task) = f"{task.id}: {task.title}"`.

`pr_body(task, runs: list[TaskRunRow], wf: WorkflowRun | None, trace_db: Path) -> str` (markdown, česky), sekce v tomto pořadí:

```
<!-- haifa: task=<id> branch=<branch> -->
## Zadání
<task.body.strip()>  (+ poznámky všech běhů na větvi: "Poznámka k běhu <run_id>: …")
## Agenti
- `<step key>` (<owner>, <harness>/<model>): <envelope.summary>      # z wf.records + wf.envelopes
## Gates a testy
- gate `<gate>` v `<phase>`: prošla | neprošla (<violations>)          # SELECT z gate_results WHERE adw_id=<run_id> (poslední attempt na fázi)
- test `<key>`: passed/failed (…)                                        # envelopes, jejichž výsledek má pole `passed`
(žádné → "- nic neběželo")
## Review
- `<key>`: schváleno | neschváleno; blokující: …                         # envelopes s polem `approved`
(žádné → "- review neběželo")
## Náklady
- běh <run_id>: $X.XX, N tokenů                                          # sessions.total_cost/total_tokens WHERE adw_id=run_id
- celkem: $X.XX
```

Náklady se sčítají přes všechny běhy na větvi (`runs_on_branch`). Chybějící trace řádek → `$0.00`. Čtení trace přes `sqlite3` read-only, tolerovat chybějící tabulky (`sqlite3.OperationalError` → prázdné). Funkce `branch_cost(trace_db, run_ids) -> (float, int)` exportovat — použije ji i záznam do `## Běhy`.

## 7. `taskfile.py` — `status: done` a `## Běhy`

`mark_done(text: str, entry: str) -> str` (čistě textová úprava, zachovat zbytek souboru bajt po bajtu):
- v YAML hlavičce (mezi prvními `---`) nahradit řádek `^status:\s*.*$` za `status: done`; když chybí, vložit `status: done` na konec hlavičky;
- sekce `## Běhy`: existuje → vložit `entry` jako nový řádek na konec sekce (před další `## ` nadpis nebo konec souboru, bez prázdných řádků navíc; komentář `<!-- … -->` ponechat); neexistuje → připojit `\n## Běhy\n\n<entry>\n`;
- idempotence: je-li už `status: done` a `entry` (podle URL PR) v sekci je, vrátit text beze změny.

`run_entry(date, workflow, pr_url, cost) -> str`: `- 2026-09-26 · workflow build-commit · PR <url> · náklady $0.00`. Datum = dnešní lokální datum (`datetime.date.today().isoformat()`), workflow = `task_runs.workflow` posledního úspěšného běhu na větvi.

Test: `tests/test_taskfile.py` (status todo→done, chybějící sekce, existující sekce s komentářem, další sekce za Běhy, idempotence, zbytek souboru nezměněn; parse přes `backlog.parse_frontmatter` vrací `status == "done"`).

## 8. `review.py` — approve, return, sync

Chyby: `ReviewError(code, message)` (stejný tvar jako `TaskRunError`; CLI používá `_task_error`).

### `approve_task(repo, task_id, *, provider=None, cfg=None) -> ApproveResult`

1. `root`, `config`, `store`. `pr = store.open_pr(task_id)` → žádný → `ReviewError("no_pr", …)`. Task nesmí právě běžet (`store.running`) → `already_running`.
2. `status = provider.status(pr)`:
   - `MERGED`/`CLOSED` → `ReviewError("pr_not_open", …)` (u `MERGED` doporučit `backlog sync`);
   - `CONFLICT` → `ReviewError("conflict", "PR nejde mergovat, … rebase nebo workflow resolve")` — nic se nemění.
3. `require_review` → `provider.approve(pr, "Schváleno v HAIFA")`; `ReviewRejected` → `ReviewError("review_rejected", <stderr hostingu>)`, **žádný commit, žádný merge**.
4. Done commit do PR větve:
   - worktree: nejnovější běh na větvi, jehož `worktree` existuje a má větev checkoutnutou; jinak dočasný `git worktree add <tmp> <branch>` (tmp pod `worktrees_dir/approve-<id>`), odstraní se v kroku 6;
   - cesta souboru tasku ve worktree: `task.path` z backlogu načteného z tipu větve (`load_base_backlog(root, config, <branch tip>, tmpdir)`), relativně ke kořeni;
   - `mark_done(text, run_entry(...))`; změnil-li se text → `git add <path>`, `git commit -m "<task-id>: status done"` (jediný commit), `provider.push`. Nezměnil-li se (opakované approve po selhaném merge) → žádný nový commit.
   - `head = rev-parse HEAD`.
5. `merge_sha = provider.merge(pr, config.merge_strategy, head, subject=f"{pr.title}")`. `ProviderError` → `ReviewError(code, message)`; done commit zůstává v PR (merge přijde, „jakmile to branch protection dovolí“ = zopakovat `task approve`), worktree zůstává.
6. Po úspěchu: `store.update_pr(branch, state='merged', merged_at=now, merge_sha=…)`; smazat worktree všech běhů na větvi + dočasný (`gitops.remove_worktree`). Lokální větev nemazat.
7. Vrátit `ApproveResult(task_id, pr: TaskPrRow, merge_sha, removed_worktrees: list[str], reviewed: bool)`.

### `return_task(repo, task_id, note, *, cfg=None, code=None, provider=None) -> TaskRunResult`

1. `note` prázdná → `ReviewError("missing_note")`. `pr = store.open_pr(task_id)` → jinak `no_pr`. `provider.status(pr)` musí být `OPEN|MERGEABLE|CONFLICT`, jinak `pr_not_open`.
2. Odstranit předchozí worktree běhů na větvi (větev může být checkoutnutá jen v jednom worktree). Má-li worktree necommitnuté změny (`git status --porcelain` neprázdné) → `ReviewError("dirty_worktree", path)` a nic nedělat.
3. `provider.comment(pr, f"Vráceno k přepracování:\n\n{note}")`.
4. `run.run_on_branch(repo, task_id, pr.branch, note=note, …)` → push + `update_pr` (tělo s novými náklady, shrnutím a poznámkou) v rámci `_publish`.
5. Soubor tasku se nemění (test to ověří).

### `sync_backlog(repo, *, provider=None, cfg=None) -> SyncResult`

1. Má-li remote: `git fetch <remote> <base>`; je-li `<remote>/<base>` napřed před lokální `base` → `advance_branch` (ff). Rozejdou-li se → `ReviewError("base_diverged")`.
2. `merged = provider.merged_prs()`; pro každý: `task_id = task_id_from_branch(branch)`; přeskočit, pokud task v backlogu `base` neexistuje, je `done`/`cancelled`; u `local` navíc přeskočit větev bez vlastních commitů (tip == `base_sha` z `task_prs`/`task_runs`; větev bez záznamu v DB přeskočit).
3. Nic → `SyncResult(updated=[])`, žádný commit.
4. Jinak **jeden** commit do `base` přes `commit_on_detached(root, base_sha, edit, "backlog sync: <id>[, <id>…] done")`, kde `edit` provede `mark_done` pro každý task (entry s URL PR, workflow z `task_runs` pokud je, jinak `?`, náklady z trace nebo `$0.00`), potom `advance_branch`, potom `git push <remote> <base>` pokud remote existuje (odmítnutí → `push_failed`, ohlásit).
5. `store.update_pr(branch, state='merged', …)` tam, kde řádek existuje. Worktree mergnutých větví smazat (po merge se worktree maže).

## 9. CLI (`cli.py`)

- `task approve <task-id> [--repo] [--json]` → `review.approve_task`. Text: `approved M01-S01-T01: merged PR <url> (<strategy>) into main, removed 1 worktree`; JSON `{"ok": true, "task_id", "pr": {...}, "merge_sha", "reviewed", "removed_worktrees"}`. Chyba → `_task_error(code, message)`, exit 1.
- `task return <task-id> --note TEXT [--repo] [--json]` (`--note` povinné, `required=True`) → `review.return_task`; výstup jako `task run` + PR URL. Engine narace na stderr při `--json` (stejně jako `_task_run`).
- `task run`: po úspěchu vypsat i PR (`pr <url>`), při `pr_error` chybu na stderr a exit 1; JSON přidá `"pr"` a `"pr_error"`.
- `task show`: JSON přidá `"prs": [TaskPrRow.to_json()]`; text řádek `pr <state> <url> (<branch>)`.
- `backlog sync [--repo] [--json]` → `review.sync_backlog`; text `synced: <ids>` nebo `nothing to sync`; JSON `{"ok": true, "updated": [{"task_id","branch","url"}], "commit": sha|null}`.
- Help `task` musí vypsat `run, show, approve, return` (upravit `test_task_help_lists_run_and_show`).

## 10. Testy (`prototype/tests/`)

Sdílené fixtures do `tests/task_repo.py`:
- `add_bare_remote(repo, tmp_path) -> Path`: `git init --bare remote.git`, `git remote add origin`, `git push -u origin main`.
- Fake `gh`: `tests/gh_fake.py` s `install_fake_gh(tmp_path, monkeypatch, responses: dict[str, FakeResponse]) -> GhLog`. Zapíše spustitelný Python skript `<tmp>/bin/gh` (shebang `#!<sys.executable>`), který každé volání připíše jako JSON řádek `{"argv": sys.argv[1:], "stdin": ..., "cwd": ...}` do `calls.jsonl` a odpověď vybere podle prvních dvou argumentů (`"pr create"`, `"pr view"`, …) z `responses.json` (`stdout`, `exit`, `stderr`). `monkeypatch.setenv("PATH", f"{bin}{os.pathsep}{PATH}")`. `GhLog.calls()` vrací seznam.

Nové testovací soubory:

1. `tests/test_providers_github.py` — pro každou operaci ověří přesný argv (tabulka §5), stdin tělo, mapování JSON → `PrStatus` (MERGEABLE, CONFLICTING, UNKNOWN→open, MERGED s merge sha, CLOSED), `create_pr` parsuje číslo z URL, `approve` s exit 1 → `ReviewRejected` s textem stderr, `merge` `--squash` vs `--merge`, `merged_prs` filtruje ne-`factory/` větve, chybějící `gh` (`HAIFA_GH=/nonexistent`) → `gh_missing`.
2. `tests/test_providers_local.py` — `status` open→mergeable, conflict (dvě větve měnící týž řádek), merged po ručním `git merge`, closed po smazání větve; `merge` squash (jeden nový commit na `main`, rodič starý main), merge (dva rodiče), konflikt nechá `main` beze změny; `main` checkoutnutý v hlavním checkoutu se posune a pracovní strom obsahuje soubory; push do bare remote.
3. `tests/test_taskfile.py` — §7.
4. `tests/test_pr_flow_local.py` — **end-to-end s bare remote** (provider `local`, `.factory/config.yaml` bez `git_provider` = výchozí):
   - `run_task(T01)` → větev je v bare remote (`git -C remote.git rev-parse factory/M01-S01-T01-1`), `task_prs` má řádek `open`, body obsahuje `## Zadání`, „Add a health check.“, `## Agenti` se summary buildera, `## Gates a testy`, `## Review`, `## Náklady`; soubor tasku v `main` i na větvi má `status: todo`.
   - Náklady: v jednom testu vložit do trace `UPDATE sessions SET total_cost=0.42 WHERE adw_id=<run_id>` a ověřit `$0.42` v `pr_body` / záznamu Běhy.
   - `return_task(T01, "use port 8081")` → nový řádek `task_runs` na **téže** větvi, prompt obsahuje `## Note\nuse port 8081`, větev v remote posunutá, `task_prs.body` obsahuje poznámku, soubor tasku na větvi i v `main` pořád `status: todo`, starý worktree smazán.
   - `approve_task(T01)` → v `main` (lokálně i v bare remote) je `src/app/health.py` i `status: done`, sekce `## Běhy` má řádek s dnešním datem, `build-commit`, URL PR a `náklady $`; squash = na `main` přibyl právě 1 commit; na PR větvi je právě 1 commit navíc měnící jen soubor tasku; worktree běhů neexistují; `task_prs.state == "merged"`; hlavní checkout `git status --porcelain` prázdný.
   - Vrácený PR stav nemění: po `return` bez `approve` `main` pořád `status: todo` (samostatné assert).
   - `backlog sync` po ručním merge: `run_task(T01)`, pak ruční `git merge --no-ff factory/M01-S01-T01-1` v hlavním checkoutu (+ push), `sync_backlog` → přesně jeden nový commit na `main` měnící jen soubor tasku, `status: done`, záznam v `## Běhy`; druhé volání `sync_backlog` nic nedělá (`updated == []`).
   - `merge_strategy: merge` v configu → merge commit se dvěma rodiči.
   - Konflikt: po `run_task` commitnout do `main` změnu téhož souboru → `approve_task` skončí `conflict`, `main` beze změny, na větvi žádný done commit.
   - Běh, který nesplní accept → žádný push, žádný `task_prs` řádek.
5. `tests/test_pr_flow_github.py` — `git_provider: github`, bare remote jako `origin`, fake `gh`:
   - `run_task` → argv `pr create --base main --head factory/M01-S01-T01-1 --title "M01-S01-T01: Health check" --body-file -`, stdin obsahuje `## Zadání`; `task_prs.pr_id == "7"` (URL `https://github.com/o/r/pull/7`).
   - `approve_task` s `require_review: false` → žádné `pr review`; volání v pořadí `pr view`, `pr merge 7 --squash --match-head-commit <sha> --subject …`; done commit je pushnutý na větev v remote.
   - `require_review: true` a `pr review` vrací exit 1 se stderr „Can not approve your own pull request“ → `ReviewError("review_rejected")` s tímto textem, **žádné** `pr merge` v logu, na větvi žádný done commit, worktree zůstává.
   - `require_review: true` úspěch → `pr review 7 --approve --body-file -` před `pr merge`.
   - `pr view` vrací `CONFLICTING` → `conflict`, žádný merge.
   - `return_task` → `pr comment 7 --body-file -` (stdin s poznámkou) a `pr edit 7 --body-file -`.
   - `sync_backlog` s `pr list` vracejícím `[{"number":7,"url":…,"headRefName":"factory/M01-S01-T01-1","mergeCommit":{"oid":…}}, {"headRefName":"feature/x",…}]` → argv `pr list --state merged --base main --json number,url,headRefName,mergeCommit --limit 200`, jeden commit do `main` (a push do bare remote) jen pro T01.
6. `tests/test_cli_task.py` / `tests/test_cli_backlog.py` — `task approve`/`task return`/`backlog sync` přes `main([...])` s `--json` (tvar výstupu, exit kódy), `task return` bez `--note` → argparse chyba (SystemExit 2), `task approve` bez PR → `no_pr`, exit 1.
7. `tests/test_config.py` — nové klíče.
8. Existující testy 1.5 musí projít beze změny chování (výchozí provider `local` bez remote = žádný push, jen řádek v `task_prs`). Pokud některý test porovnává přesně tabulky v trace DB nebo počet commitů, upravit minimálně.

Všechny testy běží offline, bez modelu (fake harness `engine_env.script`).

## 11. Dokumentace

`app_docs/1ecab8c6_task-pr-approval.md`: konfigurace (`git_provider`, `merge_strategy`, `require_review`, `remote`), tok run → PR → return/approve → merge → úklid, tabulka `task_prs`, rozdíl local vs github, příkazy CLI, odchylky od briefu pro zprávu 1.10:
- approve review jen při `require_review: true` (self-approval GitHub nedovolí);
- pořadí approve review → done commit → merge (brief krok 5); při zapnutém „dismiss stale reviews“ by nový commit approve zneplatnil — zaznamenat jako otevřený bod;
- lokální provider větve nemaže; stav squash-merge zná jen z `task_prs`;
- konflikt se jen ohlásí (rebase/`resolve` není v 1.6).

## 12. Ověření

Z kořene repa (exit status 0 u každého):

```bash
just test            # cd prototype && uv run pytest
just proto-typecheck || (cd prototype && uv run mypy)     # mypy strict přes src i tests
cd prototype && uv run ruff check . && uv run ruff format --check .
uv run --project prototype haifa-proto task --help       # vypíše run, show, approve, return
uv run --project prototype haifa-proto backlog --help    # vypíše sync
```

(Přesná jména recipe v `justfile` řádky 112–128 — ověřit `just --list`.) `git status` po testech: nic mimo `prototype/`, `app_docs/`, `specs/`; `vendor/` beze změny (`git diff --stat vendor/` prázdné).
