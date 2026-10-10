# HAIFA-S01-T11: Commit konfigurace do base (`factory config commit`, `factory config pull`)

## Cíl

Bezpečné „zveřejnění commitu do base“: commit vznikne bez checkoutu (dočasný index +
`commit-tree`) nad sha base, u přímého cíle se nejdřív pushne (bez force) a teprve po úspěšném
push se fast-forwardem posune lokální base (pod zápisovým zámkem trace DB, jen když neběží
žádný živý běh). Na tom stojí `factory config commit` (sdílená konfigurace podle D4, viz
`docs/decisions.md`) a `factory config pull` (ff lokální base na remote). Stejnou cestu později
použije instalace/aktualizace factory (není součástí tasku) — proto je jádro obecné a leží
v `providers/publish.py`, konfiguračně specifická část v `config/commit.py`.

`factory backlog commit` se **nemění**.

## Pevná omezení

- Žádný force push (`--force`, `--force-with-lease`, `+refspec`), žádný posun base jinak než
  fast-forwardem (`update-ref <new> <old>` kde `old` je rodič, nebo `merge --ff-only`).
- `vendor/` a `prototype/` se nemění. Měnit jen `aifactory/`, `justfile`, spec a app_docs.
- Testy nevolají model ani síť (remote = holé repo v `tmp_path`, `gh` = `tests/providers/gh_fake.py`).
- Při čtení stavu používej plumbing, které nebere `index.lock` (viz `config/source.py`
  `READ_ENV`). Zápisy do skutečného indexu jen v kroku „stage před posunem“.

## Existující kód, na který navazuješ

- `config/status.py`: `config_changes(root, sha)` → `[ConfigChange(path, status)]`
  (`modified|added|deleted|untracked`), `is_shared_config_path`. Zdroj seznamu cest.
- `config/source.py`: `git()` (text, `GIT_OPTIONAL_LOCKS=0`), `WorktreeSource`, `repo_root`,
  `resolve_commit`.
- `config/loader.py`: `load_config(source)` → `FactoryConfig` / `ConfigError(issues)`.
- `config/settings.py`: `parse_project_settings(...)`, `load_local(root)` →
  `LocalSettings.trace_db_path(root)`, `ProjectSettings` (`base`, `remote`, `git_provider`).
- `config/run.py`: `worktree_base(root)`.
- `providers/git.py`: `git`, `git_ok`, `rev_parse`, `is_ancestor`, `has_remote`, `fetch`,
  `remote_branches`, `checked_out_in`, `advance_branch`, `push` (s `-u`, s lease = force —
  pro base **nepoužívat**).
- `providers/__init__.py`: `get_provider(settings, root)`; `GitProvider.push(worktree, branch)`,
  `create_pr(branch, title, body)` → `PullRequest(id, url, branch, base, title)`.
- `review/flow.py::_catch_up_base` — vzor fetch + porovnání + ff (`advance_branch`).
- `review/sync.py::_next_sync_branch` — vzor volby první volné `prefix/<n>` větve.
- `run/store.py`: `TaskRunStore(db_path)`, `serialized()` (BEGIN IMMEDIATE = zápisový zámek),
  `_reap`, `_alive(pid)` (pid None = živý), `_select`.
- `run/gitops.py`: `main_root(repo)`, `symbolic_head(path)`.
- `backlog/commit.py` — vzor validace `not_on_base`, výstupu a CLI.
- `cli.py`: `_add_config_commands`, `_config`, `_emit_ok`, `_emit_fail`, `_fail_from_exception`.
- `skill/codes.py` (`_CODES`), `skill/skill.md`; `tests/test_skill.py` skenuje literální
  kódy u volání tříd v `ERROR_CLASSES` a `_emit_fail` v `cli.py`.

## Návrh

### 1. `providers/git.py` — nízkoúrovňové pomocníky (přidat)

```python
def _run_env(cwd, args, *, env: Mapping[str,str] | None = None, input_bytes: bytes | None = None)
    -> subprocess.CompletedProcess[bytes]   # binární stdin/stdout, env = {**os.environ, **env}

def hash_blob(root: Path, content: bytes) -> str
    # git hash-object -w --stdin  (zapíše objekt, vrátí sha)

def blob_at(root: Path, commit: str, path: str) -> tuple[str, str] | None
    # (mode, blob sha) cesty v commitu: `git ls-tree -z <commit> -- <path>`; None když chybí

def read_blob(root: Path, blob: str) -> bytes   # git cat-file blob <sha>

def commit_tree_with(root: Path, parent: str, changes: Sequence[TreeChange], message: str) -> str
    # TreeChange = (path, mode | None, blob | None); blob None = smazat
    # 1. tmp = tempfile.mkdtemp(prefix="aifactory-index-"); index = tmp/"index"
    # 2. env GIT_INDEX_FILE=index: `git read-tree <parent>`
    # 3. pro každou změnu: `git update-index --add --cacheinfo <mode>,<blob>,<path>`
    #    nebo `git update-index --force-remove -- <path>`
    # 4. tree = `git write-tree`; sha = `git commit-tree <tree> -p <parent> -F -` (zpráva na stdin)
    # 5. finally shutil.rmtree(tmp)
    # Chyba → ProviderError("commit_failed", ...). Skutečný index ani HEAD se nedotkne.

def push_ref(cwd: Path, remote: str, sha: str, branch: str) -> None
    # `git push <remote> <sha>:refs/heads/<branch>` — BEZ -u, bez force.
    # Selhání → ProviderError("push_failed", ...)

def remote_tip(root: Path, remote: str, branch: str) -> str | None
    # po fetch: rev_parse(refs/remotes/<remote>/<branch>) or rev_parse(FETCH_HEAD)

def next_numbered_branch(root: Path, remote: str, prefix: str, extra: Iterable[str] = ()) -> str
    # první volné `<prefix><n>`: lokální refs/heads, refs/remotes/<remote>/, ls-remote (když je
    # remote; None z remote_branches ignoruj), `extra`. Logika jako review/sync._next_sync_branch
    # (tu můžeš nechat beze změny, nebo ji přepsat na volání tohoto helperu — jen pokud testy
    # review projdou beze změny).

def count_commits(root: Path, a: str, b: str) -> int   # git rev-list --count a..b
```

`push()` a `advance_branch()` zůstávají beze změny.

### 2. `run/store.py` — dotaz na živé běhy pod zámkem (přidat)

```python
def live_runs_locked(self) -> list[TaskRunRow]:
    """Running rows whose process is alive. Caller holds ``serialized()``."""
    self._reap()
    return self._select("state = ?", (RUNNING,))

def live_runs(self) -> list[TaskRunRow]:
    with self._txn():
        return self.live_runs_locked()
```
(`_reap` označí mrtvé jako `aborted`; pid None se bere jako živý — beze změny.)

### 3. `providers/publish.py` — obecné zveřejnění commitu do base (nový modul)

Docstring: proč (commit nad base bez checkoutu, push dřív než posun, nic nevracet zpět),
pravidla pro blokátory, a že ho později použije instalace/aktualizace.

```python
DIRECT, PR = "direct", "pr"

@dataclass(frozen=True)
class PlannedFile:
    path: str
    action: Literal["create", "modify", "delete"]
    old_mode: str | None        # mode v base (None = nový)
    old_blob: str | None        # blob v base (None = nový)
    mode: str | None            # nový mode (100755 když je soubor ve stromu spustitelný, jinak 100644; None = delete)
    content: bytes | None       # nový obsah (None = delete)
    def to_json(self) -> dict: {path, action, old_blob, mode, diff, content, binary}
        # content: text utf-8, nebo None + binary=True když nejde dekódovat
        # diff: unified diff (difflib) a/<path> b/<path> proti blobu v base;
        #       binární → "Binary files differ"

@dataclass(frozen=True)
class Blocker:
    code: str; message: str
    def to_json(self) -> {code, message}

@dataclass(frozen=True)
class PublishPlan:
    base: str; base_sha: str; target: str; files: tuple[PlannedFile, ...]
    blockers: tuple[Blocker, ...]; digest: str
    def to_json(self) -> {base, base_sha, target, digest, files:[...], blockers:[...]}

def plan_digest(base: str, base_sha: str, files: Sequence[PlannedFile]) -> str:
    h = hashlib.sha256(b"aifactory-publish-v1\0")
    h.update(base.encode() + b"\0" + base_sha.encode() + b"\0")
    for f in sorted(files, key=lambda f: f.path):
        h.update(f.path.encode() + b"\0" + (f.old_blob or "").encode() + b"\0")
        if f.content is None: h.update(b"D\0")
        else: h.update(b"F" + str(len(f.content)).encode() + b"\0" + f.content)
    return h.hexdigest()
```
Digest nezahrnuje cíl ani zprávu commitu (ani mode).

```python
def plan_files(root, base_sha, paths: Iterable[str]) -> list[PlannedFile]
    # pro každou cestu: old = blob_at(root, base_sha, path); nový obsah = bajty souboru
    # ve stromu (neexistuje → None). Když nový obsah == starý blob (hash_object bez -w,
    # nebo porovnání bajtů) a mode stejný → cestu vynech. Řazeno podle cesty.

def remote_state(root, remote, base, base_sha) -> tuple[list[Blocker], list[str]]
    # jen přímý cíl s remote: fetch(root, remote, base) (ProviderError fetch_failed propaguj);
    # theirs = remote_tip(...)
    # theirs == base_sha → ok
    # is_ancestor(base_sha, theirs) → Blocker("base_behind", "<remote>/<base> is N commit(s)
    #    ahead of <base>; run factory config pull")
    # is_ancestor(theirs, base_sha) → ok + warning "<base> is N commit(s) ahead of <remote>/<base>;
    #    they are pushed together with this commit"
    # jinak → Blocker("base_diverged", ...)

def run_blocker(store: TaskRunStore) -> Blocker | None
    # store.live_runs() → první živý → Blocker("run_in_progress", "run <id> of <task> (pid N) is
    # running; wait for it or stop it")

@dataclass(frozen=True)
class PublishResult:
    commit: str; pushed: bool; advanced: bool; branch: str | None
    pr: PullRequest | None; warnings: tuple[str, ...]

def publish_direct(root, *, settings, plan, message, store) -> PublishResult:
    # předpoklad: plan.blockers je prázdný (volající to zkontroloval)
    # 1. sha = commit_tree_with(root, plan.base_sha, [(f.path, f.mode, blob) ...], message)
    #    (blob = hash_blob(root, f.content) pro ne-delete)
    # 2. s remote: push_ref(root, remote, sha, base). Selhání → ProviderError push_failed
    #    propaguj; v repu se nic nezměnilo (jen nedosažitelný objekt).
    #    Před push ověř, že lokální refs/heads/<base> je stále plan.base_sha, jinak
    #    ProviderError("base_moved", ...) a nepushuj.
    # 3. posun lokální base (po úspěšném push, nebo hned bez remote):
    #    with store.serialized():
    #      live = store.live_runs_locked()
    #      if live: warning "base not advanced: run ... is running; run factory config pull"
    #      elif refs/heads/<base> != plan.base_sha: warning "base moved meanwhile; not advanced"
    #      else:
    #        where = checked_out_in(root, base)
    #        if where: _stage_matching(where, plan.files)   # viz níže
    #        git update-ref refs/heads/<base> <sha> <plan.base_sha>
    #        advanced = True
    #    Jakákoli výjimka v kroku 3 (ProviderError, RuntimeError, OSError, TaskRunError
    #    trace_db_locked) → jen warning "base not advanced: ...", nic se nevrací zpět, push
    #    zůstává. Bez remote a s neposunutou base vrať také warning s sha commitu.
    # 4. return PublishResult(sha, pushed, advanced, None, None, warnings)

def _stage_matching(checkout, files):
    # cesty, jejichž obsah ve stromu == plánovaný obsah (bajtově; delete = soubor neexistuje)
    # → `git add -A -- <paths>` v checkoutu (jediné místo, kde se píše skutečný index).
    # Ostatní cesty (změněné po plánu) nech být a přidej warning "<path> changed after the plan;
    # it stays as an uncommitted change". Cizí staged/unstaged práce mimo plánované cesty
    # se nedotkne (add jen s explicitními cestami).
    # Pozn.: `update-ref` na base, na kterou ukazuje HEAD, posune HEAD bez dotyku stromu;
    # protože plánované cesty jsou ve stromu i indexu už v novém stavu, checkout je čistý.

def publish_pr(root, *, provider: GitProvider, settings, plan, message, body, prefix) -> PublishResult:
    # 1. sha = commit_tree_with(...) nad plan.base_sha (lokální base)
    # 2. branch = next_numbered_branch(root, remote, prefix)  (prefix "factory-config/")
    # 3. git update-ref refs/heads/<branch> <sha> "" (vytvořit, nesmí existovat)
    # 4. provider.push(root, branch) — pro local bez remote no-op. Selhání → smaž lokální větev
    #    (update-ref -d), propaguj ProviderError push_failed.
    # 5. pr = provider.create_pr(branch, title=first line of message, body)
    #    Selhání → propaguj (větev zůstává, v chybě je název větve).
    # Base ani hlavní checkout se nemění; žádný zámek, žádná kontrola běhů.

def pull_base(root, *, settings, store) -> PullResult  # {base, remote, before, after, updated, warnings}
    # bez remote → ProviderError("no_remote", ...)
    # fetch; theirs = remote_tip; ours = rev_parse(refs/heads/<base>) (None → unknown_base)
    # theirs == ours → updated False
    # is_ancestor(theirs, ours) → updated False + warning "base is N ahead of remote"
    # not is_ancestor(ours, theirs) → ProviderError("base_diverged", ...)
    # where = checked_out_in(root, base); když where a tracked změny
    #   (`git status --porcelain --untracked-files=no`, s READ_ENV) → ProviderError("dirty_base")
    # with store.serialized():
    #   live → ProviderError("run_in_progress", ...)
    #   advance_branch(root, base, theirs, ours)   # merge --ff-only v checkoutu / update-ref
    # updated True
```

Kódy chyb publish vrstvy: `ProviderError` s kódy `commit_failed`, `push_failed`,
`fetch_failed`, `base_moved`, `base_diverged`, `run_in_progress`, `dirty_base`, `no_remote`,
`unknown_base` (literály u volání `ProviderError(...)` → test_skill je najde).

### 4. `config/commit.py` — konfigurační vrstva (nový modul)

```python
class ConfigCommitError(Exception):
    def __init__(self, code, message, *, data: dict | None = None, issues: list[dict] = ()): ...

CONFIG_BRANCH_PREFIX = "factory-config/"

@dataclass(frozen=True)
class ConfigCommitResult:
    plan: PublishPlan; committed: bool; commit: str | None; pushed: bool; advanced: bool
    branch: str | None; pr: PullRequest | None; dry_run: bool; warnings: tuple[str, ...]
    def to_json(self) -> {**plan.to_json(), "dry_run", "committed", "commit", "pushed",
                          "advanced", "branch", "pr": {id,url,branch} | None, "paths": [...]}

def plan_config_commit(repo: Path, *, pr: bool) -> tuple[PublishPlan, Context, list[str]]:
    main = gitops.main_root(repo)   # TaskRunError → ConfigCommitError invalid_config
    # konfigurace pracovního stromu: cfg = load_config(WorktreeSource(main));
    #   ConfigError → blocker invalid_config (issues uchovej pro chybu)
    #   settings: cfg.settings; když load selže, base = worktree_base(main) a remote/provider
    #   z parse_project_settings nad config.yaml, jinak z commitu base, jinak defaulty
    base = settings.base; base_sha = rev_parse(refs/heads/<base>) (None → ConfigCommitError
    #   unknown_base)
    changes = config_changes(main, base_sha)     # jen sdílené cesty (D4), nikdy local.yaml
    files = plan_files(main, base_sha, [c.path for c in changes])
    blockers:
      - invalid_config (pracovní strom neprošel load_config)
      - přímý cíl: not_on_base (symbolic_head(main) != refs/heads/<base>)
      - přímý cíl: run_in_progress (run_blocker(TaskRunStore(load_local(main).trace_db_path(main))))
      - přímý cíl s remote a s neprázdnými files: remote_state(...) → base_behind / base_diverged
        (+ warning „ahead“). fetch_failed → ConfigCommitError fetch_failed.
    digest = plan_digest(base, base_sha, files)

def commit_config(repo: Path, *, pr=False, dry_run=False, expect: str | None = None,
                  message: str | None = None) -> ConfigCommitResult:
    plan, ctx, warnings = plan_config_commit(repo, pr=pr)
    if dry_run: return result(committed=False, dry_run=True)    # vždy ok, blokátory v datech
    if expect is not None and expect != plan.digest:
        raise ConfigCommitError("plan_changed", "the plan changed since --expect; review it again",
                                data=plan.to_json())
    if not plan.files: return result(committed=False)
    if plan.blockers:
        b = plan.blockers[0]
        raise ConfigCommitError(b.code, b.message, data=plan.to_json(), issues=<config issues>)
    subject = (message or "").strip() or f"config: {len(files)} file(s) from factory"
    přímý: publish_direct(...); PR: publish_pr(provider=get_provider(settings, main),
           body = "Shared factory configuration from the main checkout:\n\n" + "- action path" řádky
           + f"\n\nPlan digest: {digest}")
    ProviderError → ConfigCommitError(exc.code, exc.message, data=plan.to_json())

def pull_config(repo: Path) -> PullResult:   # settings stejně jako výše; store; pull_base
    ProviderError → ConfigCommitError(exc.code, exc.message)
```

`config/__init__.py`: exportuj `ConfigCommitError`, `commit_config`, `pull_config`,
`plan_config_commit` (importy dej lokálně/bez cyklu: `providers` importuje
`config.settings`; `config/commit.py` importuj v `__init__` jen pokud nevznikne cyklický
import — jinak ho importuj v CLI přímo z `aifactory.config.commit`).

### 5. `cli.py`

V `_add_config_commands` přidej:

```
commit  help: "commit uncommitted shared .factory/ config to base (push first, then move base)"
        description: vysvětli: cesty z config status (config.yaml, agents.yaml, roles.yaml,
        prompts/, workflows/; nikdy local.yaml); commit bez checkoutu nad base; přímý cíl
        vyžaduje checkout na base, fetch, odmítne base_behind/base_diverged, push bez force,
        lokální base se posune až po push a jen když neběží běh; --pr otevře PR z
        factory-config/<n> a base nemění; --dry-run vrátí plán (files, blockers, digest);
        --expect DIGEST odmítne změněný plán (plan_changed).
  --repo PATH, --dry-run, --pr, --expect DIGEST, -m/--message TEXT, --json
pull    help: "fast-forward local base to the remote base"
        description: fetch; ff jen když nic neběží; rozejitou base (base_diverged) a špinavý
        checkout (dirty_base) odmítne a nic nezmění.
  --repo PATH, --json
```
`--base` přidávej jen ke `status`/`show` (jako dnes). `_config` rozvětvi na `commit`/`pull`.

`_config_commit(args)`: `commit_config(_backlog_root(args.repo), pr=..., dry_run=..., expect=...,
message=...)`; `ConfigCommitError` → `_emit_fail(exc.code, exc.message, exit_code=2,
data=exc.data, issues=exc.issues)` (s `--json`), jinak text na stderr a exit 2;
`ConfigError` → `_fail_from_exception`. Úspěch: `_emit_ok(result.to_json(), result.warnings)`.
Text: dry-run vypíše `action path` řádky, blokátory a digest; jinak `committed N file(s) to
<base> (<sha12>, pushed|not pushed, base advanced|not advanced)` nebo `opened <url> from
<branch>` nebo `nothing to commit in the configuration`; warnings na stderr.
Exit kód: všechny chyby 2.

`_config_pull(args)`: obdobně; data `{base, remote, before, after, updated}`.

Aktualizuj modulový docstring (`Implemented: ... config commit, config pull ...`).

### 6. `skill/codes.py` a `skill/skill.md`

Nové kódy (exit "2"):
- `base_behind` — "the remote base has commits the local base lacks (run factory config pull)"
- `base_diverged` — "local base and the remote base have diverged; nothing changed"
- `run_in_progress` — "a run with a live process is in progress in the repository"
- `plan_changed` — "config commit --expect: the plan's digest differs; review the plan again"
- `no_remote` — "config pull: no remote is configured"

Uprav významy: `not_on_base` → "backlog/config commit: the main checkout is not on the base
branch"; `commit_failed` → "backlog/config commit: the commit could not be created";
`dirty_base` → zůstává. Pokud zavedeš jiný kód, přidej ho sem (test_skill to vynutí).

`tests/test_skill.py`: přidej `"ConfigCommitError"` do `ERROR_CLASSES`.

`skill.md`:
- V „Calling convention“ odrážce o base commitu doplň: `.factory/` změny commitni přes
  `factory config commit --json` (backlog přes `factory backlog commit`).
- Nová sekce `### Commit configuration` v `## Procedures` (za `### Check`):
  1. `factory config commit --dry-run --json` → `data.files` (`path`, `action`, `diff`,
     `content`), `data.blockers` (`code`, `message`), `data.digest`.
  2. Projdi plán, pak `factory config commit --expect <digest> [-m TEXT] --json`; `plan_changed`
     = base nebo soubory se mezitím změnily → znovu dry-run.
  3. Přímý cíl: checkout na base (`not_on_base`), nic neběží (`run_in_progress`), base není
     pozadu (`base_behind` → `factory config pull --json`) ani rozejitá (`base_diverged` →
     ručně). Push bez force; `push_failed` = nic se nezměnilo. Base se posune až po push;
     když posun selže, `warnings` to řeknou a `factory config pull` to dorovná.
  4. `--pr`: větev `factory-config/<n>`, push, PR (`data.pr`); base ani checkout se nemění.
  5. Bez změn `data.committed: false`.
  6. `factory config pull --json`: ff base na remote; `base_diverged`, `dirty_base`,
     `run_in_progress`, `no_remote` nic nemění.
  (Sekce „Commands“ se generuje z argparse — popisy musí zmínit všechny volby; test
  `test_every_command_is_in_skill` hlídá `--repo`, `--dry-run`, `--pr`, `--expect`, `-m`,
  `--message`, `--json`.)
- V `### Check` můžeš doplnit, že akce `config_commit`/`config_pull` odpovídají těmto
  příkazům (text „it is a name for the dashboard, not a command of this CLI“ uprav).

## Testy

Helpery: `tests/config/config_repo.py` (`make_repo`, `write`, `git`, `commit_all`) a
`tests/providers/provider_repo.py::isolate_git(monkeypatch)` (identita pro `commit-tree`
volaný z produkčního kódu — v testech configu nastav `GIT_AUTHOR_*`/`GIT_COMMITTER_*`,
`GIT_CONFIG_GLOBAL=os.devnull`, `GIT_CONFIG_NOSYSTEM=1` přes monkeypatch; klidně přidej do
`config_repo.py` helper `isolate(monkeypatch)` a `add_bare_remote(repo, tmp_path)` →
`git init --bare -b main origin.git`, `remote add origin`, `push -u origin main`).
Volání CLI přes `tests/cli_json.py::run_json(capsys, [...])`.

Snímek stavu pro „nic se nezměnilo“:
```python
def snapshot(repo) -> tuple[str, bytes, dict[str, bytes]]:
    refs = git(repo, "for-each-ref", "--format=%(refname) %(objectname)")
    index = (repo/".git"/"index").read_bytes()
    files = {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*")
             if p.is_file() and ".git" not in p.relative_to(repo).parts}
```
(trace DB může vzniknout — nastav `local.yaml` s `trace_db` mimo repo, nebo ji ze snímku
vyřaď; `.factory/local.yaml` je v `.gitignore` sample repa.)

Nový soubor `aifactory/tests/config/test_config_publish.py` (nebo rozděl na
`test_config_commit_cli.py` + `test_config_pull.py`):

1. **commit a push**: repo + holý remote; změň `.factory/agents.yaml`, přidej
   `.factory/workflows/x.yaml`, smaž prompt; `config commit --dry-run --json` → files s akcemi
   modify/create/delete, `blockers == []`, digest 64 hex; `config commit --expect <digest> -m msg`
   → `committed`, `pushed`, `advanced`; `git rev-parse main` == `origin/main` v bare ==
   `data.commit`; `git show --name-only` obsahuje přesně plánované cesty; obsah blobů ==
   bajty; `git status --porcelain` čistý pro `.factory/`; `config status` je `clean`.
   Digest nezávisí na `--pr`/zprávě (dry-run s `--pr` dá stejný digest).
2. **odmítnutý push**: bare remote s `hooks/pre-receive` (`#!/bin/sh\nexit 1`, chmod 755);
   snímek před → `push_failed` (exit 2) → snímek po je bajtově stejný (refy, `.git/index`,
   soubory), bare `main` nezměněn.
3. **base_behind / base_diverged**: druhý klon bare pushne commit → commit vrátí
   `base_behind`; navíc lokální commit na main (bez push) → `base_diverged`; nic se nezmění.
4. **plan_changed**: dry-run → digest; pak `commit_all` nesouvisejícího souboru do main →
   `--expect <starý>` vrátí `plan_changed`; dry-run znovu dá jiný digest a commit s ním projde.
5. **živý / mrtvý běh**: do `TaskRunStore(load_local(repo).trace_db_path(repo))` vlož
   `TaskRunRow` ve stavu `running` s `pid=os.getpid()` → `run_in_progress`, nic nezměněno;
   s pid ukončeného procesu (`subprocess.Popen(["true"]); p.wait(); p.pid`) → commit projde
   a řádek je `aborted`. (Pole `TaskRunRow` zjisti v `run/store.py`; použij `store.claim(row)`.)
6. **cizí staged a unstaged práce přežije**: `README.md` změněný a `git add`, další soubor
   změněný bez stage, a mimo plán i staged změna jiného souboru; po commitu je `git diff
   --cached --name-only` == jen cizí soubory, jejich obsah v indexu i stromu stejný, commit je
   neobsahuje.
7. **repo bez remote**: commit → `pushed: false`, `advanced: true`, `main` == commit.
8. **not_on_base**: checkout jiné větve → `not_on_base`; s `--pr` stejná situace projde.
9. **nevalidní pracovní strom**: rozbitý `agents.yaml` → `invalid_config` s `issues`; dry-run
   ho ukáže v `blockers`.
10. **bez změn**: `committed: false`, `files: []`.
11. **PR přes gh_fake** (v `tests/providers/` nebo config testu s
    `from gh_fake import install_fake_gh, reply`): `config.yaml` s `git_provider: github`
    commitnutý, bare remote, `pr create` → `reply("https://github.com/o/r/pull/9\n")`;
    `config commit --pr --json` → `branch == "factory-config/1"`, `pr.url`, bare má větev
    s commitem (rodič = base sha), lokální `main`, HEAD, index a strom beze změny; volání
    `gh pr create --base main --head factory-config/1`. Druhý PR → `factory-config/2`.
    (Pokud `get_provider`/`GitHubProvider` vyžaduje `check`, viz testy providerů; použij
    `prepare_shared_gh` fixture jako v `test_providers_github.py`.)
12. **config pull**: (a) remote o commit napřed → `updated: true`, `main` == remote,
    pracovní strom obsahuje novou verzi; (b) rozejité → `base_diverged`, nic nezměněno;
    (c) tracked změna v checkoutu na base → `dirty_base`, nic nezměněno; (d) živý běh →
    `run_in_progress`; (e) bez remote → `no_remote`.

Jednotkově v `tests/providers/` (např. `test_providers_publish.py`): `commit_tree_with`
nezmění `.git/index` ani HEAD, vytvoří commit s rodičem a přesnými bajty (vč. binárního obsahu
a smazání); `push_ref` bez force odmítne non-ff (`push_failed`); `plan_digest` se mění se sha
base, starým blobem i obsahem a ne se zprávou.

`tests/test_skill.py`: `ConfigCommitError` v `ERROR_CLASSES`; existující testy pokryjí nové
příkazy a kódy.

## Ověření

Z kořene worktree:
- `just test` (případně nejdřív `cd aifactory && uv run pytest tests/config tests/providers tests/test_skill.py -q`)
- `just typecheck` (mypy strict — typuj vše, i testy)
- `just lint` (ruff check + `ruff format --check`; spusť `uv run ruff format` na nové soubory)
- Ručně: `uv run factory --skill | grep -n "config commit\|config pull"`.

## Dokumentace

`app_docs/HAIFA-S01-T11-commit-konfigurace-do-base-factory-confi.md`: krátký popis příkazů,
toku (plán → commit-tree → fetch/blokátory → push → posun pod zámkem), kódů a výstupu JSON.

## Mimo rozsah

Instalace a aktualizace factory, API a dashboard, změna `factory backlog commit`, `check`.
