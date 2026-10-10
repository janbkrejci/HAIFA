# Plán 2.5: knihovna backlogu v `aifactory`, `factory backlog check` a `factory backlog list`

## Cíl

Přenést načtení a validaci backlogu z prototypu (`prototype/src/haifa_proto/backlog.py`, `taskfile.py`)
do balíčku `aifactory` jako podbalíček `aifactory.backlog` a implementovat v CLI `factory`:

- `factory backlog check [--json] [--repo PATH]`
- `factory backlog list [--json] [--repo PATH] [--status S] [--module M]`

Podle sekce „Backlog v markdownu“ v `docs/product-brief.md`: strom modul → step → task podle `levels`
v `.factory/config.yaml`, task = markdown soubor s YAML hlavičkou, `index.md` na modul a step s výchozími
hodnotami, které tasky dědí, odvozené stavy `ready`/`blocked`, dopočítané „blokuje“, validace.

**Mimo rozsah:** `task add|edit|show|list|link` (2.6), zápis `done` z CLI (2.12), `backlog sync` (2.13),
spouštění tasků, web.

**Pevná omezení:**
- `vendor/` a `prototype/` se **nemění** (ani testy prototypu). Kód se kopíruje a upravuje v `aifactory/`.
- Knihovna soubory backlogu **jen čte** (kromě čistě textových funkcí v `taskfile.py`, které vrací nový
  text a nic nezapisují). „Blokuje“ (`blocks`) se počítá v paměti, nikdy se neukládá.
- Stavy `running`, `failed`, `in review` nejsou platné hodnoty `status`.
- Nepřidávat závislosti do `aifactory/pyproject.toml` (už je tam `pyyaml`, `pydantic`; dev `types-PyYAML`,
  `mypy --strict`, `ruff` line-length 100, pravidla E,F,I,UP,B).
- `docs/product-brief.md`, `BACKLOG.md`, kořenový `backlog/`, `adws/` neupravovat.

## Stávající stav (co je potřeba vědět)

- `aifactory/src/aifactory/cli.py`: argparse; `backlog` je v `SUBCOMMANDS`, ale `main()` pro něj vrací 2
  a „not implemented yet“. Vzor pro podpříkazy: `_add_config_commands` / `_config` (parser se uloží přes
  `set_defaults(<x>_parser=...)`, holý příkaz bez podpříkazu vypíše nápovědu a vrátí 0). Importy uvnitř
  handlerů jsou líné (import v těle funkce) – zachovat.
- `aifactory/src/aifactory/config/settings.py`: `ProjectSettings` (pydantic, frozen) už má
  `backlog_dir: str = "backlog"` a `levels: tuple[str, ...] = ("module", "step", "task")` včetně validace
  (≥ 2 úrovně, unikátní, neprázdné). `CONFIG_FILE = ".factory/config.yaml"`.
  `parse_project_settings(text, label, issues) -> ProjectSettings | None` – `text=None` (soubor chybí)
  dá výchozí hodnoty; problémy přidá do `issues: list[ConfigIssue]`.
- `aifactory.config`: `ConfigError(issues)`, `ConfigIssue(path, message)`, `repo_root(start)` (git
  top-level, jinak `ConfigError`), `WorktreeSource(root).read_text(rel)` / `.label(rel)`.
- **Nepoužívat** `load_config`/`load_worktree_config` – vyžadují `agents.yaml` atd. Backlog potřebuje jen
  `ProjectSettings` z pracovního stromu.
- `aifactory/tests/test_smoke.py::test_subcommands_not_implemented` čeká pro `backlog` kód 2 → **upravit**.
- Testy importují pomocné moduly přímo jménem (např. `from config_repo import ...` v `tests/config/`),
  adresáře testů nemají `__init__.py` → **názvy testovacích souborů a helperů musí být v celém
  `aifactory/tests/` unikátní**.
- Ověření z kořene repa: `just test`, `just typecheck`, `just lint` (běží v `aifactory/`).

## Soubory

| Soubor | Akce |
|---|---|
| `aifactory/src/aifactory/backlog/__init__.py` | nový – docstring + re-export veřejného API (`__all__`) |
| `aifactory/src/aifactory/backlog/model.py` | nový – konstanty, `Issue`, `Container`, `Task`, `Node`, `Unmet`, `Backlog` |
| `aifactory/src/aifactory/backlog/frontmatter.py` | nový – `FrontmatterError`, `parse_frontmatter` |
| `aifactory/src/aifactory/backlog/loader.py` | nový – `load_settings`, `_Loader`, `load_backlog`, iterátory |
| `aifactory/src/aifactory/backlog/derived.py` | nový – dědění, `is_done`, `unmet`, `derived_state`, `blocks`, `progress` |
| `aifactory/src/aifactory/backlog/validate.py` | nový – `check_backlog` a jednotlivé kontroly, detekce cyklů |
| `aifactory/src/aifactory/backlog/render.py` | nový – filtry, JSON serializace, textový strom |
| `aifactory/src/aifactory/backlog/taskfile.py` | nový – 1:1 port `prototype/src/haifa_proto/taskfile.py` (jen text) |
| `aifactory/src/aifactory/cli.py` | upravit – podpříkazy `backlog check` a `backlog list` |
| `aifactory/tests/test_smoke.py` | upravit – `backlog` už je implementovaný |
| `aifactory/tests/backlog/fixtures/sample/...` | nový – vzorový repozitář (viz níže) |
| `aifactory/tests/backlog/backlog_repo.py` | nový helper – `sample_repo(tmp_path)`, `rewrite()`, `write()` |
| `aifactory/tests/backlog/test_backlog_frontmatter.py` | nový |
| `aifactory/tests/backlog/test_backlog_load.py` | nový – načtení, úrovně, dědění, stavy, blocks |
| `aifactory/tests/backlog/test_backlog_check.py` | nový – každá validace na rozbité kopii |
| `aifactory/tests/backlog/test_backlog_render.py` | nový – filtry, JSON, strom |
| `aifactory/tests/backlog/test_backlog_taskfile.py` | nový – port testů `prototype/tests/test_taskfile.py` |
| `aifactory/tests/backlog/test_backlog_cli.py` | nový – CLI, návratové kódy, `--json` |

Pozn.: helpery řeš jako obyčejný modul (`backlog_repo.py`) volaný z testů, stejně jako
`tests/config/config_repo.py`. `conftest.py` v `tests/backlog/` nezakládej.

## Datový model a chování

Přenes logiku z prototypu (přečti `prototype/src/haifa_proto/backlog.py` celé) s těmito změnami:

### model.py

```python
VALID_STATUSES = ("todo", "done", "cancelled")
DERIVED_STATES = ("ready", "blocked")            # jen dopočítané, nikdy v souboru
INHERITED_KEYS = ("owner", "source", "target", "test", "workflow", "writes", "auto_continue")
LIST_FIELDS = ("depends_on", "related", "writes")
INDEX_FILE = "index.md"
```

- **Změna proti prototypu:** `writes` se dědí (je v `INHERITED_KEYS`). Klíč testovacího příkazu v hlavičce je
  `test` (řetězec nebo seznam – necháme hodnotu tak, jak je).
- `Issue(code, message, path, id=None)` + `to_dict()`; `path` je relativní k rootu repa, posix
  (např. `backlog/M01-core/S01-model/M01-S01-T02-loader.md`).
- `Container(id, title, level, path, defaults, extra, parent, children, tasks, body)`.
- `Task(id, title, status, level, path, parent, own, depends_on, related, writes, body)` – `writes` je
  jen vlastní hodnota z hlavičky; `own` obsahuje z hlavičky jen klíče z `INHERITED_KEYS`
  (včetně `writes`, pokud je v hlavičce).
- `Backlog(root: Path, settings: ProjectSettings, containers, issues, by_id)` – **pole `settings`**
  (typ `aifactory.config.ProjectSettings`) místo prototypového `config`.
- Dataclasses jako v prototypu (ne pydantic).

### frontmatter.py

`parse_frontmatter(text) -> tuple[dict[str, object], str]` a `FrontmatterError` beze změny z prototypu.

### loader.py

- `load_settings(root: Path) -> ProjectSettings`: přečte `root/.factory/config.yaml` přes
  `WorktreeSource(root)`, zavolá `parse_project_settings(text, source.label(CONFIG_FILE), issues)`;
  když vrátí `None`, vyhodí `ConfigError(issues)`. Chybějící soubor = výchozí nastavení.
- `load_backlog(root: Path, settings: ProjectSettings | None = None) -> Backlog` – když `settings` chybí,
  zavolá `load_settings(root)`. Jinak 1:1 prototypový `_Loader` s `self.levels = settings.levels` a
  `settings.backlog_dir`. Hloubka stromu: kontejnerové úrovně = `levels[:-1]`, tasky jsou soubory
  v adresářích předposlední úrovně; `levels[-1]` je název úrovně tasku.
- Kódy chyb při načítání (zachovat): `missing_backlog_dir`, `missing_index`, `invalid_frontmatter`,
  `missing_field` (id/title u `index.md`, id/title/status u tasku), `invalid_field` (ne-řetězec,
  prázdný řetězec, ne-seznam řetězců u `depends_on`/`related`/`writes`), `invalid_status`,
  `misplaced_file`, `misplaced_dir`.
- **Doplnit:** `writes` v `index.md` musí být seznam řetězců, jinak `invalid_field` s cestou k `index.md`
  (hodnota se pak do `defaults` nedá).
- Skryté soubory/adresáře (`.`) se přeskakují, vše se prochází seřazené podle jména.
- `iter_containers`, `iter_nodes`, `iter_tasks` jako v prototypu. `by_id` přes `setdefault` (první vyhrává).

### derived.py

Z prototypu beze změny sémantiky: `ancestors`, `effective(task)` (nejvyšší předek první, bližší
přepisují, task vyhrává; vrací jen `INHERITED_KEYS` – takže i `writes`), `effective_workflow`,
`descendant_tasks`, `active_tasks` (bez `cancelled`), `is_done(node)` (task: `status == "done"`;
kontejner: má aspoň jeden aktivní task a všechny aktivní jsou `done` → **step je hotový, když jsou
hotové všechny jeho tasky**), `unmet(backlog, task)` (důvody `unknown`, `cancelled`, `not_done`,
`empty`, `incomplete` + `missing`), `derived_state` (`done`/`cancelled` → sám; `todo` → `blocked`
pokud `unmet` neprázdné, jinak `ready`; jiný → `invalid`), `blocks` (reverz `depends_on`), `progress`.

Doplnit `effective_writes(task) -> list[str]` (effective `writes`, nebo `[]`).

### validate.py

`check_backlog(backlog) -> list[Issue]`: načítací problémy + `duplicate_id`, `unknown_ref`
(`depends_on` i `related`, míří na task i kontejner – tedy step/modul), `id_prefix`, `cycle`
(Tarjan přes `dependency_graph`, kde kontejner → jeho aktivní tasky, zpráva
`dependency cycle: A -> B -> A`, cesta = soubor prvního uzlu). Seřadit podle `(path, code, message)`.
Kód převzít z prototypu (`_check_duplicates`, `_check_refs`, `_check_prefixes`, `dependency_graph`,
`_strongly_connected`, `_cycle_path`, `_check_cycles`).

Cesta u chyby kontejneru ukazuje na adresář (`missing_index`) nebo `index.md` (ostatní) – prototyp
u `duplicate_id`/`id_prefix`/`cycle` kontejneru používá `container.path` (adresář). **Upravit:** pro
kontejner s `index.md` použij cestu k `index.md` (přidej do `Container` pole `index_path: str | None`,
naplň relativní cestou k `index.md`, když existuje), aby `backlog check` vždy ukazoval na soubor.

### render.py

- `counts(backlog) -> dict[str, int]` (počet na úroveň, klíče = `levels`).
- `STATUS_FILTERS = ("todo", "done", "cancelled", "ready", "blocked")`.
  `task_matches(backlog, task, status: str | None) -> bool`: `None` → True; jinak
  `task.status == status or derived_state(backlog, task) == status`.
- `select_modules(backlog, module: str | None) -> list[Container]`: `None` → všechny top-level
  kontejnery; jinak ty, jejichž `id == module` nebo jméno adresáře (`Path(path).name`) `== module`.
  Nic nenalezeno → `LookupError` (CLI z toho udělá chybu `unknown_module`).
- Filtrovaný strom: kontejner se zobrazí, pokud nefiltrujeme podle stavu, nebo pokud má aspoň jeden
  potomek-task, který vyhovuje; tasky se zobrazí jen vyhovující. `progress` a `done` kontejneru se vždy
  počítají ze **všech** jeho tasků (filtr mění jen to, co se vypíše).
- `issues_to_json(backlog, issues) -> {"ok": bool, "errors": [issue...], "counts": {...}}`.
- `task_to_json` jako v prototypu, navíc `"owner"` není potřeba zvlášť (je v `effective`), `"writes"`
  = `effective_writes(task)`, `"own_writes"` = `task.writes`.
- `container_to_json`: `kind`, `id`, `title`, `level`, `path`, `progress: {"done": d, "total": t}`,
  `done: bool` (= `is_done`), `defaults` (JSON-ifikované), `blocks`, `children` (podkontejnery pak tasky).
- `backlog_to_json(backlog, issues, *, status=None, module=None)` →
  `{"ok": not issues, "levels": [...], "backlog_dir": ..., "filters": {"status": ..., "module": ...},
  "items": [...], "issues": [...]}`.
- `format_tree(backlog, *, status=None, module=None) -> list[str]` – dva mezery na úroveň:
  - kontejner: `"{id} {title}  [{done}/{total}]"` + `"  done"` pokud `is_done` + `"  (blocks: a, b)"`;
    kontejner bez id: `"? {path}"`.
  - task: `"{id} {title}  {state}"`; u `blocked` `" (waits for: ...)"` jako v prototypu
    (`incomplete` → `X [a, b]`, `not_done` → `X`, jinak `X (reason)`); u `invalid` `" (status: 'x')"`;
    pak `blocks` suffix.
- `_jsonable` z prototypu (datumy → ISO).

### taskfile.py

Zkopírovat `prototype/src/haifa_proto/taskfile.py` beze změny logiky (`RUNS_HEADING`, `run_entry`,
`has_entry`, `mark_done`). Nikde se z CLI nevolá (zápis `done` je 2.12). Testy přenést z
`prototype/tests/test_taskfile.py` (přejmenovat importy na `aifactory.backlog.taskfile`).

### `__init__.py`

Re-export: `Backlog, Container, Task, Node, Issue, Unmet, FrontmatterError, VALID_STATUSES,
INHERITED_KEYS, STATUS_FILTERS, parse_frontmatter, load_settings, load_backlog, iter_nodes, iter_tasks,
iter_containers, effective, effective_workflow, effective_writes, is_done, unmet, derived_state, blocks,
progress, check_backlog, counts, backlog_to_json, issues_to_json, format_tree, select_modules`.
Nepřidávat `taskfile` do re-exportu (import `aifactory.backlog.taskfile`).

## CLI (`aifactory/src/aifactory/cli.py`)

V `build_parser` přidat větev `elif name == "backlog": _add_backlog_commands(child)`.

```
factory backlog check [--json] [--repo PATH]
factory backlog list  [--json] [--repo PATH] [--status {todo,done,cancelled,ready,blocked}] [--module ID|DIR]
```

- `--repo PATH`: kořen repa s `.factory/config.yaml`. Bez něj: `repo_root(Path.cwd())`, při
  `ConfigError` (není git) použij `Path.cwd()`.
- Holé `factory backlog` vypíše nápovědu `backlog` a vrátí 0.
- JSON vypisovat `json.dumps(..., ensure_ascii=False, indent=2)`.
- Neplatný config (`ConfigError` z `load_settings`): text → `factory backlog <cmd>: <exc>` na stderr;
  JSON → `{"ok": false, "errors": [{"code": "invalid_config", "message": ..., "path": <issue.path>,
  "id": null}, ...]}` (jedna položka na `ConfigIssue`); **exit 2**.

**`backlog check`:**
- bez chyb: `OK: 2 module, 3 step, 6 task` (počty podle `levels`), exit 0.
- s chybami: řádek na chybu `"{path}: {code}: {message}"`, pak `"{n} error(s)"`, exit 1.
- `--json`: `issues_to_json`, exit 0/1 stejně.

**`backlog list`:**
- načte, spustí `check_backlog` (issues jdou do JSON a do varování).
- `--module` neznámý → text `factory backlog list: unknown module 'X'` na stderr / JSON
  `{"ok": false, "errors": [{"code": "unknown_module", ...}]}`, exit 2.
- text: řádky `format_tree`; když chybí adresář backlogu → stderr
  `error: backlog directory '<dir>' not found`, exit 1; jinak při problémech stderr
  `N problem(s), run 'factory backlog check'`, exit 0.
- `--json`: `backlog_to_json(...)`, exit 1 jen při `missing_backlog_dir`, jinak 0.

Aktualizovat docstring modulu (`Implemented: harness check, config status/show, backlog check/list`)
a v `main()` přidat `if command == "backlog": return _backlog(args)`.

`test_smoke.py::test_subcommands_not_implemented`: přidat `"backlog"` do přeskočených a
`assert main(["backlog"]) == 0`.

## Testovací data

`aifactory/tests/backlog/fixtures/sample/` = kopie `prototype/tests/fixtures/backlog/` (včetně
`.factory/config.yaml` s `levels: [module, step, task]` a `backlog_dir: backlog`) s těmito změnami:
- `backlog/M01-core/index.md`: přidat `writes: [src/]`.
- `M01-S02-T01-endpoint.md` si ponechá vlastní `writes: [src/api/]` (přepisuje zděděné).
- `backlog/M01-core/S02-api/index.md` má `workflow: plan-build-test` (už má) – step přepisuje modul.

Očekávané stavy vzorku: `M01-S01-T01` done, `M01-S01-T02` ready (workflow `plan-build-test-review`
vlastní, writes `[src/]` zděděné, owner `alice`, test `uv run pytest`), `M01-S02-T01` ready
(závisí na stepu `M01-S01`… **pozor:** `M01-S01` má T02 `todo` → step není hotový → T01 je `blocked`,
`unmet` = `incomplete` s `missing [M01-S01-T02]`; workflow `plan-build-test` ze stepu, writes
`[src/api/]`), `M01-S02-T02` cancelled, `M02-S01-T01` ready (owner `bob`, writes `[]`),
`M02-S01-T02` blocked (čeká na `M01-S02-T01`). `blocks`: `M01-S01` → `[M01-S02-T01]`,
`M01-S01-T01` → `[M01-S01-T02, M02-S01-T01]`, … Builder si hodnoty ověří načtením a testy napíše
podle skutečného chování, které odpovídá pravidlům výše.

`backlog_repo.py`: `FIXTURE = Path(__file__).parent / "fixtures" / "sample"`,
`sample_repo(tmp_path) -> Path` (`shutil.copytree` do `tmp_path / "repo"`), `rewrite(path, old, new)`
(assert, že `old` v textu je), `write(root, rel, text)`. Vzorek není git repo – testy CLI používají
`--repo`.

## Testy (co musí pokrýt)

`test_backlog_frontmatter.py`: validní hlavička + tělo; chybí úvodní `---`; neuzavřená; neplatný YAML;
hlavička není mapping; prázdná hlavička → `{}`.

`test_backlog_load.py`:
- vzorek: počty (`2 module, 3 step, 6 task`), vzorek je bez chyb (`check_backlog == []`).
- dědění: owner/test/source/target z modulu, workflow ze stepu přepisuje modul, task přepisuje step,
  `writes` zděděné i přepsané (`effective_writes`).
- `derived_state` pro všechny tasky vzorku; `is_done` stepu `M01-S01` false, po přepsání T02 na `done`
  true, a pak `M01-S02-T01` je `ready`; kontejner jen s `cancelled` tasky → `is_done` false a závislost
  na něm je `empty`.
- `blocks` reverz.
- jiné `levels`: config `levels: [epic, task]` (dvě úrovně: `backlog/E1/index.md` + tasky přímo v
  něm) a `levels: [area, module, step, task]` (čtyři) – postav v `tmp_path`, ověř `level` názvy a počty.
- `levels` z configu určuje názvy v `counts` a v `Task.level`.
- chybějící `.factory/config.yaml` → výchozí levels; neplatný config (`levels: [x]`) → `ConfigError`.

`test_backlog_check.py` (každý případ na čerstvé kopii přes `rewrite`/`write`, ověřit `code` **a**
`path` = soubor):
`duplicate_id`, `unknown_ref` (depends_on na neexistující task i na neexistující step, `related`),
`cycle` (task↔task; task → vlastní step; zpráva obsahuje `->`), `invalid_status` (`status: running`),
`missing_field` (chybí `status`, chybí `title`, chybí `id` v `index.md`), `invalid_field`
(`depends_on: M01` jako řetězec; `writes: src/` v `index.md`), `invalid_frontmatter`, `missing_index`,
`misplaced_file` (task v adresáři modulu), `misplaced_dir`, `id_prefix`, `missing_backlog_dir`.

`test_backlog_render.py`: `format_tree` obsahuje očekávané řádky (`done`, `blocked (waits for: ...)`,
`[1/2]`); filtr `status="ready"` vynechá blocked/done a kontejnery bez shody; `status="todo"` bere
ready i blocked; `module="M02"` a `module="M02-ui"` vrátí jen M02; neznámý modul → `LookupError`;
`backlog_to_json` struktura (`levels`, `filters`, `items[0]["progress"]`, `done` u stepu, task
`state`, `writes`, `blocked_by`, `blocks`); JSON projde `json.dumps`.

`test_backlog_taskfile.py`: port testů z `prototype/tests/test_taskfile.py`.

`test_backlog_cli.py` (volat `aifactory.cli.main([...])` a `capsys`):
- `backlog check --repo <vzorek>` → 0, `OK: 2 module, 3 step, 6 task`; `--json` → `ok: true`.
- rozbitý vzorek → 1, stdout obsahuje `backlog/...md: duplicate_id:`; `--json` → `ok: false`,
  `errors[*].path` je cesta k souboru.
- neplatný config → 2 (text i JSON s `invalid_config`).
- `backlog list --repo` → 0, strom se stavy; `--status blocked`, `--module M01`, kombinace;
  `--json` s filtry; neznámý modul → 2; chybějící adresář backlogu → 1.
- bez `--repo`: `monkeypatch.chdir(vzorek)` (není git → fallback na cwd) → funguje.
- `main(["backlog"])` → 0.

## Postup

1. Založ `aifactory/src/aifactory/backlog/` a moduly výše (port kódu z prototypu, úpravy podle plánu).
2. Uprav `cli.py` a `tests/test_smoke.py`.
3. Založ fixture a testy.
4. Spusť z kořene repa: `just test`, `just typecheck`, `just lint` (případně `cd aifactory && uv run ruff
   format .` pro formátování). Rozhoduje návratový kód, všechny tři musí projít.
5. Ručně: `just factory backlog check --repo aifactory/tests/backlog/fixtures/sample` (exit 0) a
   `just factory backlog list --repo aifactory/tests/backlog/fixtures/sample --status ready`.

## Hotovo znamená

- `aifactory.backlog` načte strom podle `levels`, tasky dědí `owner`, `source`, `target`, `test`,
  `workflow`, `writes` z `index.md` modulu a stepu.
- Validace hlásí duplicitní id, neznámé odkazy (task i step), cykly, neznámý stav, chybějící povinná pole,
  vše s cestou k souboru; `factory backlog check` vrací 1 při chybách.
- `ready`/`blocked` odvozené z `depends_on`, step hotový = všechny jeho (nezrušené) tasky hotové.
- `factory backlog list` vypíše strom se stavy, umí `--status`, `--module`, `--json`.
- `just test`, `just typecheck`, `just lint` projdou; `vendor/` a `prototype/` beze změny
  (`git status` je neukazuje).
