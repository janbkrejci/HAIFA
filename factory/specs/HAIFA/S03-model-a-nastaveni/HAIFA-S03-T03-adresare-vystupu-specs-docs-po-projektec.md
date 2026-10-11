# Plán HAIFA-S03-T03: Adresáře výstupů (specs, docs) po projektech

## Cíl

Klíče `specs_dir` a `docs_dir` v `index.md` (projekt, step) i v tasku se dědí jako
`workflow`/`test` (nejbližší nastavená úroveň vyhrává, `null` se přeskakuje) a přebijí
`specs_dir`/`docs_dir` z `.factory/config.yaml`. Spec a dokumentace tasku pak vzniknou
v `<nejbližší specs_dir>/<task-id>-<slug>.md` a `<nejbližší docs_dir>/<task-id>-<slug>.md`;
tyto cesty nese prompt (`- spec file:`, `- documentation file:`, `allowed paths`) i proměnné
`{{spec_path}}`/`{{doc_path}}`. Neplatná hodnota (absolutní, s `..`, prázdná, ne-řetězec)
je issue v `factory backlog check` a běh tasku skončí `TaskRunError` před startem.
Guard pustí zápis dvou výstupních souborů i agentovi, jehož `writes` je neprázdné a soubor
nepokrývá (rozhodnutí „Výstupy po projektech (2026-10-02)“ v `docs/decisions.md`).

Mimo rozsah: dashboard, `workdir` po projektech, agenti/modely po projektech.
Neměnit `.factory/`, `vendor/`, `prototype/`, `docs/`. Testy nevolají model.

## Stávající stav (pro orientaci)

- `backlog/model.py`: `INHERITED_KEYS` – klíče, které loader dává do `Container.defaults`
  a `Task.own`.
- `backlog/loader.py`: `_Loader.load_container` / `load_task` validují `test`,
  `test_timeout` (issue `invalid_field`, hodnota se **ponechá**, aby běh selhal).
- `backlog/derived.py`: `_nearest(task, key)` – nejbližší ne-`None` hodnota
  (task → index nahoru); `effective_test`, `effective_test_timeout`.
- `config/settings.py`: `_relative(value, allow_dot=True)` – validace relativní cesty
  v repu (prázdná / absolutní / `..` → `ValueError`). Použito pro `specs_dir`, `docs_dir`
  v configu.
- `run/scope.py`: `output_paths(task, settings)` bere jen `settings.specs_dir/docs_dir`;
  `TaskScope(task_id, writes, outputs)` a `permits()`.
- `run/guard.py`: `TaskWriteGuard._permitted` = `always_writable` OR
  (`permissions.permitted(path, agent, cfg)` AND `scope.permits(path)`).
  `permissions.permitted`: agent `writes is None` = neomezený (kromě `protected_files`),
  `[]` = žádné zápisy do repa, seznam = jen vyjmenované.
- `run/task.py`: `run_task` volá `output_paths` + `task_scope` (ř. ~413), `task_prompt`,
  `_execute` dává `spec_path`/`doc_path` do proměnných (ř. ~531).
- Seed planner má `writes: [$specs_dir/]` (rozvinuto z configu), documenter `[$docs_dir/]` –
  proto projektový `specs_dir` mimo `specs/` potřebuje výjimku v guardu.

## Změny

### 1. `aifactory/src/aifactory/config/settings.py`

Přidej veřejnou funkci (vedle `check_timeout`), kterou použije loader i scope:

```python
def check_relative_dir(value: object) -> str:
    """A directory inside the repository: a non-empty relative path without ``..``."""
    if not isinstance(value, str):
        raise ValueError(f"must be a path relative to the repository, got {value!r}")
    return _relative(value)
```

(`_relative` už vrací `strip()`nutý text; `.` je povolená jako u configu.) Exportuj ji
tam, odkud se dnes importuje `check_timeout` (`aifactory.config.settings`; do
`aifactory.config.__init__` jen pokud tam je i `check_timeout`).

### 2. `aifactory/src/aifactory/backlog/model.py`

`INHERITED_KEYS` rozšiř o `"specs_dir"` a `"docs_dir"` (za `"workflow"` nebo na konec;
pořadí ovlivní jen výpis v `skill.md` přes `{{inherited_keys}}` – zkontroluj, že žádný
test nečte přesný řetězec; `grep -rn "auto_continue" aifactory/tests/skill`).

### 3. `aifactory/src/aifactory/backlog/loader.py`

- Pomocná funkce vedle `_timeout_issue`:

```python
OUTPUT_DIR_KEYS = ("specs_dir", "docs_dir")

def _dir_issue(key: str, value: object) -> str | None:
    """Why a ``specs_dir``/``docs_dir`` value is invalid; ``None`` when missing or valid."""
    if value is None:
        return None
    try:
        check_relative_dir(value)
    except ValueError as exc:
        return f"field '{key}' must be a directory relative to the repository: {exc}"
    return None
```

- `load_container`: ve smyčce přes klíče, stejně jako `test_timeout`:
  `if key in OUTPUT_DIR_KEYS and (problem := _dir_issue(key, value)) is not None:`
  → `self.issue("invalid_field", problem, index, container.id)`; hodnotu **ponech**
  v `defaults` (komentář „Kept: a task inheriting it must fail …“).
- `load_task`: po kontrole `test_timeout` totéž pro oba klíče z `own`
  (`self.issue("invalid_field", problem, path, task_id)`, hodnotu ponech).
- `factory backlog check` bere `backlog.issues` přes `check_backlog`, takže nic dalšího
  netřeba.

### 4. `aifactory/src/aifactory/backlog/derived.py` (+ export v `backlog/__init__.py`)

```python
def effective_specs_dir(task: Task) -> object:
    """The nearest ``specs_dir``, looked up like ``test``; ``None`` when unset."""
    return _nearest(task, "specs_dir")

def effective_docs_dir(task: Task) -> object:
    return _nearest(task, "docs_dir")
```

Přidej do importu a `__all__` v `aifactory/src/aifactory/backlog/__init__.py`.

### 5. `aifactory/src/aifactory/run/scope.py`

- Aktualizuj docstring modulu: adresáře jsou nejbližší `specs_dir`/`docs_dir` tasku
  (task, step, projekt), jinak z configu; agent s neprázdným `writes` smí zapsat oba
  výstupní soubory i mimo své `writes` (viz guard).
- `output_paths(task, settings)`:

```python
class OutputDirError(ValueError):
    """A ``specs_dir``/``docs_dir`` of the backlog that is not a directory inside the repo."""
    def __init__(self, key: str, value: object, reason: str) -> None: ...  # ulož key, value

def _output_dir(task: Task, key: str, value: object, fallback: str) -> str:
    if value is None:
        return fallback
    try:
        return check_relative_dir(value)
    except ValueError as exc:
        raise OutputDirError(key, value, str(exc)) from exc

def output_paths(task: Task, settings: ProjectSettings) -> OutputPaths:
    name = f"{task.id}-{task_slug(task)}.md"
    specs = _output_dir(task, "specs_dir", effective_specs_dir(task), settings.specs_dir)
    docs = _output_dir(task, "docs_dir", effective_docs_dir(task), settings.docs_dir)
    return OutputPaths(spec=_in_dir(specs, name), doc=_in_dir(docs, name))
```

  (Jednodušší varianta bez vlastní třídy je OK: vyhoď `ValueError` se zprávou
  `"specs_dir '../x' must stay inside the repository …"`; hlavní je, aby `task.py`
  rozlišil chybu a převedl ji na `TaskRunError`.)
- `TaskScope`: přidej `def is_output(self, path: str) -> bool:
  return normalize(path) in self.outputs`.
- Exportuj případný `OutputDirError` v `run/__init__.py` jen pokud se hodí; není nutné.

### 6. `aifactory/src/aifactory/run/guard.py`

`TaskWriteGuard._permitted`:

```python
def _permitted(self, path: str, agent: Any, cfg: Any) -> bool:
    if any(permissions._matches(path, p) for p in permissions.always_writable(cfg)):
        return True
    if not self.scope.permits(path):
        return False
    if permissions.permitted(path, agent, cfg):
        return True
    # docs/decisions.md, "Výstupy po projektech": the two outputs of the task are
    # writable for an agent that may write at all, even outside its own `writes`.
    return (
        self.scope.is_output(path)
        and bool(getattr(agent, "writes", None))
        and not any(permissions._matches(path, p) for p in cfg.defaults.protected_files)
    )
```

- `writes: []` → `bool([])` je `False` → výstup se vrátí.
- `writes is None` už pokrývá `permissions.permitted` (kromě protected – ty zůstávají
  chráněné, pokud je agent nevyjmenuje).
- Doplň do docstringu modulu jednu větu o této výjimce.
- `ConflictWriteGuard` se nemění.

### 7. `aifactory/src/aifactory/run/task.py`

V `run_task` obal výpočet:

```python
try:
    outputs = output_paths(task, settings)
except ValueError as exc:  # OutputDirError
    raise TaskRunError("invalid_output_dir", f"task {task_id}: {exc}") from exc
scope = task_scope(task, outputs)
```

Musí to proběhnout před `store.claim` a vytvořením worktree (to už platí – je to uvnitř
bloku s `base_copy`). Prompt i proměnné `spec_path`/`doc_path` už berou `outputs`, takže
nic dalšího. Platí i pro resolve běh (`resolve_onto`) – neplatný adresář ho také zastaví;
to je v pořádku.

Volitelné: `aifactory/src/aifactory/skill/skill.md` – pod popis zděděných klíčů jedna věta,
že `specs_dir`/`docs_dir` přebijí config (`{{inherited_keys}}` je vypíše automaticky).

## Testy

Vše s falešným harnessem (`run_repo.fake_env`, `make_run_repo`, `ok`). `run_task` čte
backlog z commitnutého `base` → změny backlogu v testu **commitni** (`commit_all`).

### `aifactory/tests/run/test_task_output_dirs.py` (nový)

Fixtures jako v `test_task_run.py` (`script`, `repo`).

1. `test_project_specs_dir_receives_spec` – přepiš `backlog/M01-core/index.md` na
   `---\nid: M01\ntitle: Core\nworkflow: plan-commit\nspecs_dir: docs/M07/specs\ndocs_dir: docs/M07/app\n---\n`
   a přepiš `.factory/agents.yaml` (v testovacím repu, ne v HAIFA) tak, aby planner měl
   `writes: [specs/]` (`  - name: planner\n    writes: [specs/]\n`), commit.
   Planner zapíše `docs/M07/specs/M01-S01-T01-schema.md`, `ok(artifacts=[that])`.
   Ověř: `run.state == "succeeded"`, soubor je na větvi (`git show branch:path`), prompt
   obsahuje `spec=docs/M07/specs/M01-S01-T01-schema.md` a
   `doc=docs/M07/app/M01-S01-T01-schema.md` a `- spec file: docs/M07/specs/...`.
2. `test_step_and_task_override_project` – projekt `specs_dir: docs/M07/specs`, step
   `specs_dir: docs/S01` → spec v `docs/S01/...`; task `specs_dir: docs/T` → v `docs/T/...`;
   step `docs_dir` nenastaven → doc z configu (`app_docs/...`). Stačí kontrolovat
   `script.calls[0].prompt` (planner nic nemusí zapsat, `ok()`).
3. `test_planner_write_outside_writes_and_outputs_is_reverted` – stejné nastavení jako 1,
   planner zapíše výstup **i** `docs/M07/specs/other.md` (mimo své `writes` i mimo výstupy;
   je ale nutné, aby cesta byla v task scope, jinak to testuje jen scope – proto přidej do
   writes stepu i `docs/M07/`, tj. `writes: [src/app/, docs/M07/]`). Ověř `state == "failed"`,
   `other.md` neexistuje ve worktree, `"docs/M07/specs/other.md"` je v `run.error`.
   Druhá varianta téhož testu (nebo samostatný test): zápis do `src/other.py` mimo scope →
   failed (pokrývá „ostatní cesty mimo writes se dál vrací“).
4. `test_agent_with_empty_writes_cannot_write_outputs` – planner `writes: []`, zapíše spec
   do `docs/M07/specs/...` → `failed`, soubor vrácen, cesta v chybě.
5. `test_invalid_output_dir_stops_before_start` – parametrizuj `"../x"`, `"/abs"`, `5`
   na indexu projektu (nebo tasku), commit, `pytest.raises(TaskRunError)` s
   `code == "invalid_output_dir"`, `script.calls == []`, nevznikl worktree ani větev
   (zkopíruj `assert_nothing_created` z `test_task_run.py` nebo ho importuj, pokud jde).

Pozn.: existující `test_outputs_are_named_by_task` a `test_write_outside_writes_is_reverted`
musí dál projít (agenti tam mají `writes` neuvedené = `None`).

### `aifactory/tests/backlog/test_backlog_output_dirs.py` (nový)

Vzor `test_backlog_check.py` / `test_backlog_test_timeout_field.py` (`sample_repo`,
`rewrite`, `write` z `backlog_repo`).

1. `../x` v `index.md` projektu → `check_backlog(load_backlog(root))` má jeden
   `invalid_field`, `path == "backlog/M01-core/index.md"`, `"specs_dir"` ve zprávě; hodnota
   zůstala v `defaults`.
2. Totéž pro `docs_dir: /abs` v tasku (`path == T01`).
3. Platná `docs/M07/specs` → žádné issue; `effective_specs_dir(task)` vrátí nejbližší
   hodnotu (task > step > projekt), `null` na tasku se přeskočí.
4. CLI: `main(["backlog", "check", "--json"])` (podle vzoru v
   `test_backlog_test_timeout_field.py`, `read_envelope`) se `specs_dir: ../x` → exit 1,
   issue `invalid_field`.

### Další

- Jednotkový test `TaskScope.is_output` / `output_paths` fallback na config může přijít
  do testu výše (bez gitu).

## Ověření

```
just test
just typecheck
just lint
```

(Pokud recepty běží z kořene repa nad `aifactory/`, spusť je z kořene worktree.)
Cílené: `cd aifactory && uv run pytest tests/run/test_task_output_dirs.py tests/backlog/test_backlog_output_dirs.py tests/run/test_task_run.py tests/backlog -q`.

## Soubory

- upravit: `aifactory/src/aifactory/config/settings.py`, `backlog/model.py`,
  `backlog/loader.py`, `backlog/derived.py`, `backlog/__init__.py`, `run/scope.py`,
  `run/guard.py`, `run/task.py` (volitelně `skill/skill.md`)
- nové: `aifactory/tests/run/test_task_output_dirs.py`,
  `aifactory/tests/backlog/test_backlog_output_dirs.py`
- dokumentaci `app_docs/HAIFA-S03-T03-adresare-vystupu-specs-docs-po-projektec.md` píše
  documenter.
