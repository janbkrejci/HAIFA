# Plán: agenti necommitují + `backlog sync` volí volnou větev

Dvě chyby z validace `github-180539` (roster `claude-haiku`):

1. Builder na haiku sám spouští `git commit` → hlídač zápisů (`src/aifactory/run/guard.py:123`, „agent committed, reset to …“) commit vrátí a fáze selže (R2, R3, R4, R10, F2).
2. `factory backlog sync` volí `factory-sync/<n>` jen podle lokálních větví a DB (`_next_sync_branch` v `src/aifactory/review/sync.py`), takže narazí na větev, která už je na remote z dřívějších běhů → `push_failed` (non-fast-forward).

Mimo rozsah: hlídač zápisů (`run/guard.py`) se NEMĚNÍ, modely v rosterech se nemění, `vendor/` a `prototype/` se nemění. Testy nevolají model ani síť.

Všechny cesty níže jsou relativní k `aifactory/`.

---

## Část A — prompty: necommituj, nepushuj, neměň větve

### Kde prompty jsou

- Jediné prompty agentů v `aifactory/` jsou v `validation/template/.factory/prompts/<agent>/{system,user}.md` (planner, builder, reviewer, documenter). V `src/aifactory/` žádné výchozí `.md` prompty nejsou (`engine/prompts.py` jen renderuje; `config/loader.py` je čte z `.factory/prompts/`). Rostery (`validation/rosters/claude-haiku`, `pi-haiku`) prompty nemají – přebírají je ze šablony (`validation/roster.py`).
- Role, které mění soubory (`src/aifactory/engine/defaults/roles.yaml`): `plan`→agent `planner`, `build`/`fix`/`revise`/`resolve`→agent `builder`, `document`→agent `documenter`. Fix, revise a resolve tedy používají prompt builderu. Reviewer (`writes: []`) pravidlo nepotřebuje.
- Inline prompt resolve: `src/aifactory/run/resolve.py:56` už říká „Do not run git add, commit, rebase, merge, reset or checkout; code stages and commits the result.“ – doplnit tam `push` a `branch`/`switch`.

### Změny

Do sekce `## Instructions` v každém z těchto souborů přidej jako poslední odrážku PŘESNĚ tento text (stejný ve všech třech, test ho hledá doslova):

- `validation/template/.factory/prompts/builder/system.md`
- `validation/template/.factory/prompts/planner/system.md` (před sekci `## Subagents`, tj. na konec `## Instructions`)
- `validation/template/.factory/prompts/documenter/system.md`

```
- Git is the workflow's job, not yours. Do not commit: never run `git commit` (nor `git add`, `git stash`, `git reset`, `git rebase` or `git merge`). Do not push: never run `git push`. Do not create, switch or delete git branches (`git switch`, `git checkout`, `git branch`). Leave your changes uncommitted in the working tree — the workflow commits them after you report, using your `commit_message`. A commit of yours is undone and fails the phase.
```

Navíc (posílení pro haiku, které se chytá slova „commit“ u `commit_message`) v `user.md` builderu, planneru a documenteru upravit popis pole `commit_message` v JSON ukázce tak, aby končil větou „… — the workflow makes this commit; do not run git commit yourself>“. Konkrétně:
- `builder/user.md`: `"commit_message": "<imperative one-line git subject for the code you changed — the workflow makes this commit; do not run git commit yourself>"`
- `planner/user.md`: `"commit_message": "<imperative one-line git subject for committing THIS PLAN DOCUMENT, not the work it describes — e.g. 'Add spec for the /health endpoint'; the workflow makes this commit, do not run git commit yourself>"`
- `documenter/user.md`: obdobně jako planner (`… e.g. 'Document the /health endpoint'; the workflow makes this commit, do not run git commit yourself>`).

Pozor: nesahej na `{{spec_path}}` / `{{doc_path}}` ani na strukturu JSON – fake harness validace z vyrenderovaného promptu čte výstupní cesty (`tests/validation/test_validation_prompt_paths.py`). Neměň prompt revieweru (pravidlo haifa-validate).

`src/aifactory/run/resolve.py`, řádek 56–57, nahradit:
```python
"Change no other file. Do not run git add, commit, push, rebase, merge, reset, "
"checkout, switch or branch; code stages, commits and pushes the result.",
```
(ověř, že žádný test netestuje přesné znění – `grep -rn "Do not run git add" tests`; pokud ano, uprav očekávání.)

### Test

Nový soubor `tests/validation/test_agent_prompts_no_git.py` (bez modelu, bez sítě, jen čtení souborů):

```python
"""Every agent that changes files is told to leave git to the workflow."""
from pathlib import Path
import pytest, yaml
from validation.sandbox import AIFACTORY_DIR   # už existuje, použij stejně jako test_validation_prompt_paths.py

ROLES = AIFACTORY_DIR / "src/aifactory/engine/defaults/roles.yaml"
PROMPTS = AIFACTORY_DIR / "validation/template/.factory/prompts"
WRITING_ROLES = ("plan", "build", "fix", "revise", "resolve", "document")
RULE_FRAGMENTS = (
    "Do not commit: never run `git commit`",
    "Do not push: never run `git push`",
    "Do not create, switch or delete git branches",
    "the workflow commits them",
)

def writing_agents() -> set[str]:
    roles = yaml.safe_load(ROLES.read_text("utf-8"))["roles"]
    return {roles[r]["agent"] for r in WRITING_ROLES}

def test_writing_agents_are_known() -> None:
    assert writing_agents() == {"planner", "builder", "documenter"}

@pytest.mark.parametrize("agent", sorted(writing_agents()))
def test_prompt_forbids_git(agent: str) -> None:
    text = (PROMPTS / agent / "system.md").read_text("utf-8")
    for fragment in RULE_FRAGMENTS:
        assert fragment in text, (agent, fragment)
```
Ověř, jak ostatní testy v `tests/validation/` importují `AIFACTORY_DIR` (je v `validation/sandbox.py`); pokud tam neexistuje stejné jméno, spočítej cestu přes `Path(__file__).resolve().parents[2]`. Přidej i jednoduchý test, že `resolve_prompt` (z `aifactory.run.resolve`) obsahuje `push` a `branch` – jen pokud se dá zavolat snadno s `Task` z existujících fixture; jinak vynech.

Hlídač se nemění – existující testy hlídače (commit agenta → reset + selhání fáze) musí dál procházet beze změny.

---

## Část B — `backlog sync` zvolí větev, která neexistuje lokálně ani na remote

### Změny

1. `src/aifactory/providers/git.py` – nová funkce:
```python
def remote_branches(root: Path, remote: str, prefix: str) -> list[str] | None:
    """Branch names under `prefix` on `remote` (``git ls-remote --heads``); None when unreachable."""
    result = _run(root, ("ls-remote", "--heads", remote, f"refs/heads/{prefix}*"), None)
    if result.returncode != 0:
        return None
    names = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            names.append(parts[1].removeprefix("refs/heads/"))
    return names
```

2. `src/aifactory/review/sync.py` – `_next_sync_branch(ctx)` rozšířit o známá jména z:
   - lokálních větví `refs/heads/factory-sync/*` (už je),
   - remote-tracking refů `refs/remotes/<remote>/factory-sync/*` (`for-each-ref --format=%(refname:short)` vrací `origin/factory-sync/3` → odstranit prefix `<remote>/`),
   - `ctx.store.sync_branches()` (už je),
   - `pgit.remote_branches(ctx.main, remote, SYNC_PREFIX)` když `pgit.has_remote(ctx.main, remote)`.
   `remote = ctx.rc.config.settings.remote`. Výsledek = `SYNC_PREFIX + str(max(čísla) + 1)`.
   Když `remote_branches` vrátí `None` (remote nedostupný), nepadat: vrátit se k lokální znalosti a přidat warning do `result.warnings` (např. `f"cannot list {remote} branches; sync branch chosen from local refs"`). Proto změň signaturu na `_next_sync_branch(ctx: _Ctx, warnings: list[str]) -> str` a volej `_next_sync_branch(ctx, result.warnings)`.
   Pro jistotu ještě finální kontrola, že zvolená větev není lokálně (`pgit.rev_parse(ctx.main, f"refs/heads/{name}") is None`) – jinak n+1 ve smyčce (defenzivní, levné).
   Aktualizuj docstring modulu: „on a branch `factory-sync/<n>` that exists neither locally nor on the remote“.

   Znovupoužití již otevřeného sync PR (`existing`) se nemění.

3. Nic dalšího v `review/flow.py` ani providerech neměň. GitHub provider pushuje přes stejné `git.push`, takže oprava platí i pro něj.

### Test

Do `tests/run/test_backlog_sync.py` přidej test (vzor bare remote: `tests/run/test_task_pr_flow.py:227` `test_approve_catches_up_base`):

```python
def test_sync_skips_branch_that_exists_on_remote(
    repo: Path, script: Script, capsys: Capsys, tmp_path: Path
) -> None:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)],
                   check=True, capture_output=True)
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "-u", "origin", "main")
    # a factory-sync/1 left on the remote by an earlier run, unknown locally and to the DB,
    # on a commit that is not an ancestor of what sync will push
    git(repo, "switch", "-q", "-c", "stale")        # nebo přes klon / worktree
    write(repo, "stale.txt", "old\n"); git(repo, "add", "stale.txt")
    git(repo, "commit", "-q", "-m", "old sync")
    git(repo, "push", "-q", "origin", "stale:refs/heads/factory-sync/1")
    git(repo, "switch", "-q", "main"); git(repo, "branch", "-D", "stale")
    stale = git(origin, "rev-parse", "factory-sync/1")

    run_and_merge_outside(repo, script)
    git(repo, "push", "-q", "origin", "main")

    code, data = sync(capsys, repo)

    assert code == 0, data
    assert data["created"] is True
    pr = data["pr"]; assert isinstance(pr, dict) and pr["branch"] == "factory-sync/2"
    assert git(origin, "rev-parse", "factory-sync/1") == stale      # untouched
    assert git(origin, "rev-parse", "factory-sync/2") == git(repo, "rev-parse", "factory-sync/2")
    assert "status: done" in git(repo, "show", f"factory-sync/2:{TASK_FILE}")
```
Poznámky k testu:
- Pozor na `write` helper – ověř jeho signaturu v `tests/run/run_repo.py`; commit stale větve dělej tak, aby pracovní strom repa zůstal čistý (případně přes `git worktree add` do `tmp_path` nebo přes klon originu). Repo nesmí mít po tom lokální `factory-sync/*` ani `refs/remotes/origin/factory-sync/*` (jinak test neověří ls-remote cestu) – pokud `push` vytvoří remote-tracking ref, smaž ho `git update-ref -d refs/remotes/origin/factory-sync/1`.
- Ověř tvar `data["pr"]` (`SyncPrRow.to_json()`) – pokud nemá klíč `branch`, kontroluj `data["url"]`, který u local provideru s remote je `f"{origin}#factory-sync/2"`.
- Přidej `import subprocess` do hlavičky.
- Ověř, že bez opravy test padá (`push_failed`) – spusť ho jednou před změnou v `sync.py`.
- Volitelně druhý test: `remote_branches` na nedostupném remote (`git remote add origin /nonexistent`) vrátí `None` – jednotkově v `tests/providers/`.

Existující testy (`SYNC = "factory-sync/1"`, `factory-sync/2` se nesmí vytvořit při reuse) musí projít beze změny.

---

## Ověření (vše z kořene HAIFA)

1. `just test tests/validation/test_agent_prompts_no_git.py tests/run/test_backlog_sync.py tests/validation/test_validation_prompt_paths.py`
2. `just test` – celé, exit 0.
3. `just typecheck` a `just lint` – exit 0 (`ruff format` nové soubory).
4. `just validate --remote local` – ve výsledku žádný scénář `failed`. (Pokud běh trvá, spusť ho na pozadí; posuzuj exit status a výsledný souhrn, ne slova ve výstupu.)

## Soubory

- `validation/template/.factory/prompts/builder/system.md`, `builder/user.md`
- `validation/template/.factory/prompts/planner/system.md`, `planner/user.md`
- `validation/template/.factory/prompts/documenter/system.md`, `documenter/user.md`
- `src/aifactory/run/resolve.py` (text resolve promptu)
- `src/aifactory/providers/git.py` (`remote_branches`)
- `src/aifactory/review/sync.py` (`_next_sync_branch`, docstring)
- `tests/validation/test_agent_prompts_no_git.py` (nový)
- `tests/run/test_backlog_sync.py` (nový test)
