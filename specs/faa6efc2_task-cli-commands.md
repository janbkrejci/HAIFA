# Plán: `factory task add|edit|show|list|link` (úkol 2.6)

## Cíl

Přidat do CLI `factory` podpříkaz `task` s akcemi `add`, `edit`, `show`, `list` a `link`. Postaví se nad knihovnou `aifactory.backlog` z úkolu 2.5. Logika zápisu patří do core (`aifactory.backlog`), protože ji později použije i dashboard. `cli.py` zůstane tenká vrstva.

Mimo rozsah: `task run` (2.9) a dashboard. Neměnit `vendor/`, `prototype/` ani chráněné soubory (`adws/adw_modules/`, `adws/adw_*.py`, `adws/adw_sssf_config/`, `docs/product-brief.md`).

## Výchozí stav (přečteno)

- `aifactory/src/aifactory/backlog/`: `model.py` (`Task`, `Container`, `Issue`, `Backlog`, `VALID_STATUSES`, `INDEX_FILE`), `loader.py` (`load_backlog(root, settings=None)`, `iter_tasks`, `iter_containers`), `derived.py` (`derived_state`, `unmet`, `blocks`, `effective*`), `validate.py` (`check_backlog`), `render.py` (`task_to_json`, `task_matches`, `select_modules`, `STATUS_FILTERS`, `_jsonable`), `taskfile.py` (textová úprava `status: done` a `## Běhy`, funkce `_split_header`), `frontmatter.py` (`parse_frontmatter`, `FrontmatterError`).
- `aifactory/src/aifactory/cli.py`: `SUBCOMMANDS` obsahuje `task`, ale ten zatím vrací `not implemented yet` (kód 2). Vzorem je `backlog` (`_add_backlog_commands`, `_backlog`, `_backlog_root(repo)`, `_print_json`), včetně chyby `invalid_config` při `ConfigError`.
- Testy: `aifactory/tests/backlog/backlog_repo.py` (`sample_repo(tmp_path)`, `write`, `rewrite`, `task_md`, `index_md`, konstanty cest `T01`, `T02`, `ENDPOINT`, `DOCS`, `VIEW`, `FILTER`, `M01_S01`…) a fixture `tests/backlog/fixtures/sample/` (M01-S01-T01 done, M01-S01-T02 todo → T01, M01-S02-T01 → step M01-S01 a related M02-S01-T01, M01-S02-T02 cancelled, M02-S01-T01 → M01-S01-T01, M02-S01-T02 → M02-S01-T01 + M01-S02-T01). Testy se importují přes rootdir (`from backlog_repo import ...`), balíčky nemají `__init__.py`, takže jména testovacích modulů musí být v celém stromu unikátní.
- `aifactory/tests/test_smoke.py::test_subcommands_not_implemented` přeskakuje `harness`, `config` a `backlog`. Nově musí přeskakovat i `task` a ověřit `main(["task"]) == 0`.
- Formát tasku podle briefu (`docs/product-brief.md`, sekce „Backlog v markdownu“):

```markdown
---
id: M07-S02-T03
title: Migrace hlavičky faktury
status: todo
workflow: plan-build-test-review
depends_on: [M07-S01, M03-S01-T02]
writes: [src/Invoicing/, src/Common/Tax/]
---

## Zadání
...

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
```

Umístění souboru: `backlog/<modul>/<step>/<id>-<slug>.md`.

## Návrh

### 1. Textová úprava hlavičky: `aifactory/src/aifactory/backlog/taskfile.py` (rozšířit)

Stávající `mark_done`, `run_entry`, `has_entry` a `_split_header` zůstanou beze změny. Přidat:

- `FIELD_ORDER: tuple[str, ...] = ("id", "title", "status", "workflow", "depends_on", "related", "writes")`.
- `format_scalar(value: str) -> str`: hodnota se zapíše bez uvozovek (plain), pokud je neprázdná, nezačíná ani nekončí mezerou, neobsahuje žádný ze znaků `:#,[]{}&*!|>'"%@\`` a newline, nezačíná `-` ani `?` a zároveň `yaml.safe_load(text) == value`. Tím se vyloučí `true`, `null`, `123`, data apod. Jinak se zapíše `json.dumps(value, ensure_ascii=False)`, protože JSON řetězec je platný YAML double-quoted scalar. Diakritika zůstane plain (`Migrace hlavičky faktury`).
- `format_list(values: list[str]) -> str` vrátí `[a, b]` s položkami přes `format_scalar`. Prázdný seznam dává `[]`.
- `set_field(text: str, key: str, value: str | list[str]) -> str`: najde v hlavičce řádek `^{key}:` ve sloupci 0. Rozsah pole zahrnuje i následující pokračovací řádky, tedy ty, které začínají mezerou, tabulátorem nebo `-` (blokový seznam `depends_on:\n  - a`). Rozsah se nahradí jedním řádkem `key: <hodnota>\n`. Když klíč chybí, nový řádek se vloží za poslední existující klíč, který je ve `FIELD_ORDER` před `key`. Pokud takový klíč není, vloží se na konec hlavičky. Tělo a ostatní řádky zůstanou byte-identické.
- `remove_field(text: str, key: str) -> str` odstraní řádek klíče včetně pokračovacích řádků. Chybějící klíč vrátí text beze změny.
- Po `set_field` a `remove_field` se výsledek ověří přes `parse_frontmatter`: nová hodnota klíče musí být rovna `value`, resp. klíč musí chybět. Při neshodě se vyhodí `ValueError`. Je to pojistka proti exotickým hlavičkám.
- `new_task_text(fields: dict[str, object], body: str) -> str` sestaví nový soubor. Pole jdou v pořadí `FIELD_ORDER`, řádek se vynechá, když hodnota je `None`. Výstup je `---\n...---\n\n## Zadání\n{body.strip()}\n\n## Běhy\n<!-- doplňuje HAIFA při schválení PR -->\n`. Při prázdném body se řádek s textem vynechá, zůstane `## Zadání\n\n## Běhy…`.

### 2. Operace nad backlogem: nový `aifactory/src/aifactory/backlog/edit.py`

```python
class TaskEditError(Exception):
    def __init__(self, code: str, message: str, *, exit_code: int = 2,
                 path: str | None = None, id: str | None = None,
                 issues: list[Issue] | None = None) -> None: ...
    def errors(self) -> list[dict[str, object]]
        # issues -> [i.to_dict()...], jinak [{"code","message","path","id"}]

@dataclass
class WriteResult:
    action: str            # "add" | "edit" | "link"
    changed: bool
    path: str              # relativní k rootu
    task: Task             # task z nově načteného backlogu
    backlog: Backlog       # backlog po zápisu
    issues: list[Issue]    # check_backlog po zápisu (zbylé, předem existující problémy)
```

Veřejné funkce (všechny berou `root: Path`, načtou backlog samy přes `load_backlog(root)` a propouštějí `ConfigError`):

- `add_task(root, step: str, title: str, *, task_id: str | None = None, slug: str | None = None, workflow: str | None = None, writes: list[str] | None = None, depends_on: list[str] | None = None, related: list[str] | None = None, body: str = "") -> WriteResult`
- `edit_task(root, task_id, *, title=None, status=None, workflow=None, clear_workflow=False, writes=None, clear_writes=False) -> WriteResult`
- `link_task(root, task_id, *, depends_on: list[str] = [], related: list[str] = [], remove: bool = False) -> WriteResult` (v kódu `None` default, ne mutable)
- `find_task(backlog, task_id) -> Task` vyhodí `TaskEditError("unknown_task")`. Použije se i pro show.

Společný průběh zápisu (privátní `_commit(backlog, changes: dict[str, str], action, target_rel)`):

1. `baseline = check_backlog(backlog)`.
2. **Staging:** do `tempfile.TemporaryDirectory()` zkopírovat `root/<backlog_dir>` přes `shutil.copytree`, aplikovat `changes` (rel. cesta → nový text) a spustit `load_backlog(tmp_root, backlog.settings)` a `check_backlog`. Soubor `.factory/config.yaml` se nekopíruje, settings se předají přímo.
3. `new = [i for i in candidate if (i.code, i.path, i.message) not in baseline_keys]`. Pokud `new` není prázdné, vyhodí se `TaskEditError(code="backlog_invalid", message=f"change rejected: {len(new)} new problem(s)", exit_code=1, issues=new)`. `errors()` pak vrací přímo nové issues s kódy z 2.5 (`cycle`, `unknown_ref`, `duplicate_id`, `id_prefix`, …). **Reálný strom se v tomto případě vůbec nedotkne.** Předem existující problémy jinde v backlogu zápis neblokují, jen se nesmí přidat nové.
4. **Pojistka cest:** každá cílová cesta musí po `resolve()` ležet uvnitř `(root / backlog_dir).resolve()` a končit `.md`. Jinak se vyhodí `TaskEditError("outside_backlog")`.
5. Atomický zápis: `tempfile.NamedTemporaryFile(dir=cíl.parent, prefix=".", suffix=".tmp", delete=False)`, zápis UTF-8 a `os.replace`. Loader skryté soubory ignoruje. Při `OSError` se dočasný soubor smaže a vyhodí se `TaskEditError("write_failed")`.
6. Po zápisu: `after = load_backlog(root, settings)`, `issues = check_backlog(after)` (validace z 2.5 po zápisu), `task = after.by_id[id]`. Výsledkem je `WriteResult`.
7. Když `changes` nic nemění (nový text == starý), staging i zápis se přeskočí a vrátí se `changed=False`. Validace po „zápisu“ se přesto spustí a vrátí issues.

Pravidla jednotlivých operací:

- **add**
  - `step` je id kontejneru na úrovni `levels[-2]`. Hledá se v `iter_containers(backlog.containers)` podle `c.id == step and c.level == levels[-2]`. Když neexistuje, vyhodí se `unknown_step` (exit 2).
  - `title.strip()` nesmí být prázdný, jinak `invalid_value`.
  - Id: pokud je zadané, musí odpovídat `^[A-Za-z0-9][A-Za-z0-9._-]*$`, jinak `invalid_id`. Když zadané není, vygeneruje se `f"{step}-T{n:02d}"`, kde `n = 1 + max` číselné přípony z tasků přímo v tom stepu odpovídajících `^{re.escape(step)}-T(\d+)$` (0, když žádný není). Šířka je `max(2, len(nejdelší nalezené číslice))`.
  - Prefix id a duplicitu neověřuje add sám, zachytí je staging validace (`id_prefix`, `duplicate_id`, exit 1).
  - Slug: `--slug` nebo `slugify(title)`. `slugify` dělá `unicodedata.normalize("NFKD")`, zahodí combining znaky, převede na lowercase, sekvence mimo `[a-z0-9]` nahradí `-`, ořízne `-` a délku na 40 znaků (znovu ořízne `-`). Zadaný `--slug` musí po průchodu `slugify` zůstat stejný, jinak `invalid_value`.
  - Jméno souboru je `f"{id}-{slug}.md"`, a když je slug prázdný, `f"{id}.md"`. Když soubor existuje, vyhodí se `file_exists` (exit 2).
  - Hlavička: `id`, `title`, `status: todo`, `workflow` (jen když je zadaný), `depends_on` (vždy, i `[]`), `related` a `writes` (jen když jsou zadané). Seznamy se deduplikují se zachováním pořadí.
  - Odkazy v `depends_on` a `related` se neověřují zvlášť. Neexistující odkaz nebo cyklus zachytí staging (`unknown_ref`, `cycle`, exit 1). Výjimka: odkaz na sebe sama u `related` vyhodí `self_ref` (exit 2), protože validace ho nezachytí.
- **edit**
  - Bez jediné volby vyhodí `no_changes` (exit 2).
  - `--workflow` a `--clear-workflow` zároveň, stejně jako `--writes` a `--clear-writes` zároveň, vyhodí `conflicting_options` (exit 2).
  - `title` je po strip neprázdný, jinak `invalid_value`.
  - `status` musí být v `("todo", "cancelled")`, jinak `invalid_status` (exit 2) se zprávou, že `done` nastavuje jen schválení PR. Pokud je aktuální status tasku `done` a volá se změna statusu, vyhodí se také `invalid_status` („task is done; its status changes only through PR approval“).
  - `workflow` s neprázdným řetězcem zavolá `set_field("workflow", ...)`, `clear_workflow` zavolá `remove_field` a task pak dědí z `index.md`.
  - `writes` jako seznam (i prázdný, `[]` znamená „nic“ a přebíjí dědění) zavolá `set_field`, `clear_writes` zavolá `remove_field`.
  - Na `title` a `status` se použije `set_field`.
- **link**
  - Musí být zadán aspoň jeden ref, jinak `no_changes`. Ref rovný `task_id` vyhodí `self_ref`.
  - Přidávání: ke stávajícímu seznamu se připojí chybějící refs a pořadí se zachová. Duplicitní ref se nepřidá, takže když se nic nezmění, výsledek je `changed=False`.
  - Odebírání (`remove=True`): refs se ze seznamu odstraní. Ref, který v seznamu není, se tiše ignoruje. `depends_on` zůstane i prázdný jako `depends_on: []`, klíč `related` se při prázdném seznamu odstraní (`remove_field`).
  - Seznamy se vždy přepisují do flow stylu přes `set_field`.
- **Cílový task** (edit, link, show): `backlog.by_id.get(id)` musí být `Task`, jinak `unknown_task` (exit 2). Pokud má baseline `duplicate_id` issue s tímto id, vyhodí se `duplicate_id` (exit 2), protože cíl není jednoznačný.
- Chybějící `backlog_dir` u všech příkazů vyhodí `missing_backlog_dir` (exit 2).

Exporty doplnit do `aifactory/backlog/__init__.py`: `TaskEditError`, `WriteResult`, `add_task`, `edit_task`, `link_task`, `find_task`, `slugify`, `set_field`, `remove_field`. Z `render.py` exportovat i `task_to_json` a `task_matches`. Upravit docstring balíčku: čtení je v `loader`, zápis tasků jen v `edit`/`taskfile`.

### 3. CLI: `aifactory/src/aifactory/cli.py`

- V `build_parser` přidat větev `elif name == "task": _add_task_commands(child)`. V `main` přidat `if command == "task": return _task(args)`. Aktualizovat modulový docstring (seznam implementovaných příkazů).
- Každý podpříkaz dostane `--json` a `--repo PATH`, stejně jako `backlog`. Root se určí přes stávající `_backlog_root`.
- Syntaxe:
  - `factory task add STEP TITLE [--id ID] [--slug SLUG] [--workflow W] [--writes P ...] [--depends-on ID ...] [--related ID ...] [--body TEXT]`
  - `factory task edit ID [--title T] [--status S] [--workflow W | --clear-workflow] [--writes [P ...] | --clear-writes]`. U `--writes` je `nargs="*"`, prázdné znamená `[]`. `--status` je volný řetězec validovaný v core, ne argparse `choices`, aby `--status done` vrátilo JSON chybu `invalid_status`.
  - `factory task link ID [--depends-on REF ...] [--related REF ...] [--remove]`
  - `factory task show ID`
  - `factory task list [--status S] [--module ID] [--step ID]`. `--status` se validuje v kódu proti `STATUS_FILTERS`, jinak `invalid_status` (exit 2). `--module` jde přes `select_modules`, a když modul neexistuje, `unknown_module` (exit 2). `--step` omezí výpis na tasky kontejneru s tímto id na úrovni `levels[-2]`, jinak `unknown_step` (exit 2).
- Holé `factory task` vypíše nápovědu a vrátí 0 (`task_parser.print_help()`, stejný vzor jako `backlog`).
- **Chyby.** Všechny domény se chytají v jednom místě `_task(args)`:
  - `ConfigError` dá JSON `{"ok": false, "errors": [{"code": "invalid_config", ...}]}` a exit 2 (stejně jako `_backlog`).
  - `TaskEditError` dá JSON `{"ok": false, "errors": exc.errors()}` a `exc.exit_code`. Text se píše na stderr: `factory task <cmd>: <message>` a pro každé issue řádek `  <path>: <code>: <message>`.
  - Argparse usage chyby zůstávají jako dosud (exit 2, bez JSON).
- **Úspěch zápisu (add/edit/link):**
  - JSON: `{"ok": true, "action": "add|edit|link", "changed": bool, "path": rel, "task": task_to_json(after, task, blocks(after)), "issues": [i.to_dict() for i in result.issues]}`. Exit 0.
  - Text: `added <id> <path>`, `updated <id> <path>` nebo `unchanged <id>`. Když `issues` není prázdné, na stderr jde `N problem(s), run 'factory backlog check'`.
- **show:**
  - JSON: `{"ok": true, "task": task_to_json(...), "body": task.body, "issues": [...issues týkající se task.path...]}`.
  - Text: řádky `id`, `title`, `path`, `status`, `state` (derived) a `workflow` (efektivní, `-` když chybí). Dále `depends`, kde každá položka je `ID (stav)`: u tasku jeho derived/status, u kontejneru `done` nebo `n/m`. Potom `waits for` (stejný formát jako `_waits_for` v render, a ten proto zveřejnit jako `waits_for`), `related`, `writes` (efektivní) a `blocks`. Prázdné hodnoty se píšou jako `-`. Za prázdným řádkem následuje tělo souboru.
- **list:**
  - JSON: `{"ok": not issues, "filters": {...}, "tasks": [task_to_json...], "issues": [...]}`.
  - Text: jeden řádek na task `f"{id:<W} {state:<9} {title}"`. U `blocked` se přidá `  (waits for: ...)`. Když existují issues, na stderr jde stejná hláška jako u `backlog list`. Exit 0.

**Tabulka stabilních kódů** (vložit do docstringu `edit.py` a nápovědy `factory task --help` epilogu):

| kód | exit | kdy |
|---|---|---|
| `invalid_config` | 2 | neplatný `.factory/config.yaml` |
| `missing_backlog_dir` | 2 | `backlog_dir` neexistuje |
| `unknown_task` | 2 | id neexistuje nebo není task |
| `unknown_step` | 2 | step (kontejner úrovně `levels[-2]`) neexistuje |
| `unknown_module` | 2 | `task list --module` |
| `duplicate_id` | 2 / 1 | cílové id je nejednoznačné (2); add by vytvořil duplicitu (1, ze stagingu) |
| `invalid_id`, `invalid_value`, `invalid_status` | 2 | neplatný vstup |
| `no_changes`, `conflicting_options`, `self_ref` | 2 | špatná kombinace voleb |
| `file_exists` | 2 | soubor tasku už existuje |
| `outside_backlog`, `write_failed` | 2 | pojistka cest / chyba I/O |
| `cycle`, `unknown_ref`, `id_prefix`, … (kódy z 2.5) | 1 | zápis by backlog rozbil, nic se nezapsalo |

### 4. Testy

Nové soubory:

**`aifactory/tests/backlog/test_task_taskfile_fields.py`** (čisté funkce):
- `format_scalar`: plain vs. quoted (`"true"`, `"123"`, `"a: b"`, `"x, y"`, diakritika zůstane plain). Round-trip přes `yaml.safe_load`.
- `set_field` nahradí existující řádek. Přepíše blokový seznam (`depends_on:\n  - a\n  - b\n`) na `[a, c]`. Vloží chybějící klíč na správné místo podle `FIELD_ORDER`. Tělo zůstane byte-identické (porovnat část za druhým `---`).
- `remove_field` odstraní klíč i s pokračovacími řádky. Chybějící klíč vrátí text beze změny.
- `new_task_text` se naparsuje přes `parse_frontmatter` s očekávanými poli a obsahuje `## Zadání` a `## Běhy`.
- `slugify("Migrace hlavičky faktury") == "migrace-hlavicky-faktury"`, prázdný/symbolový vstup dává `""` a ořez na 40 znaků.

**`aifactory/tests/backlog/test_task_edit.py`** (core nad `sample_repo(tmp_path)`):
- `add_task(root, "M01-S01", "Nový task")` vytvoří `backlog/M01-core/S01-model/M01-S01-T03-novy-task.md` se `status: todo` a `depends_on: []`. Task je v novém backlogu, `derived_state == "ready"` a `check_backlog` je prázdný.
- add s `--depends-on M01-S01-T02 --writes src/x/ --workflow wf` zapíše pole a vrátí stav `blocked`.
- add s neznámým depends vyhodí `TaskEditError`, `exit_code == 1`, `errors()[0]["code"] == "unknown_ref"` a **strom je byte-identický** (helper `snapshot(root) -> dict[str, bytes]` přes `rglob`, porovnat před a po).
- add s `task_id="X-1"` vyhodí `id_prefix` (exit 1). Existující id `M01-S01-T01` vyhodí `duplicate_id` (exit 1). Neznámý step vyhodí `unknown_step`. Step id modulu (`M01`) vyhodí `unknown_step`. Prázdný title vyhodí `invalid_value`. Id s `/` vyhodí `invalid_id`.
- edit title se znakem `:` projde a zbytek souboru se nezmění, kromě řádku title. Status `cancelled` → `todo` projde. `status="done"` vyhodí `invalid_status`. Změna statusu u done tasku `T01` vyhodí `invalid_status`. `clear_workflow` u `T02` odstraní klíč a efektivní workflow se vrátí k dědění (`plan-build`). `writes=[]` zapíše `writes: []`. Beze změn vyhodí `no_changes`. Stejná hodnota vrátí `changed=False` a mtime/obsah se nezmění.
- link: přidání `related` do `T02` projde. Přidání `depends_on` `M01-S01-T01 → M01-S01-T02` (T02 už závisí na T01) vyhodí `cycle` (exit 1) a strom je byte-identický. Přidání závislosti tasku na vlastní step (`M01-S01-T01 → M01-S01`) vyhodí `cycle`. Neznámý ref vyhodí `unknown_ref`. Self ref vyhodí `self_ref`. `remove=True` odebere a u `related` odstraní klíč, `depends_on` zůstane `[]`. Duplicitní přidání vrátí `changed=False`.
- Předem existující problém jinde (např. `rewrite` jiného tasku na neznámý ref) neblokuje nesouvisející edit a vrácené `issues` ho obsahují.
- Soubory mimo `backlog/` (např. `.factory/config.yaml`) se nikdy nemění. Ověřuje to snapshot mimo `backlog_dir` před a po úspěšném add.

**`aifactory/tests/backlog/test_task_cli.py`** (přes `main([...])` a `capsys`, se vzorem z `test_backlog_cli.py`):
- `main(["task"]) == 0` a nápověda obsahuje `add`.
- add, edit a link v textovém i `--json` režimu vracejí exit 0 a JSON `ok`, `action`, `changed`, `task.id`, `task.state`, `path`.
- Chyba v `--json` (cyklus) vrací exit 1 a `errors[0].code == "cycle"`. Neznámý task vrací exit 2 a `unknown_task`. `edit --status done --json` vrací exit 2 a `invalid_status`. Text chyby jde na stderr s prefixem `factory task link: `.
- `show M01-S01-T02` v textu obsahuje `state     ready` (nebo aspoň `ready` na řádku `state`) a `depends   M01-S01-T01 (done)`. `--json` dává `task.state` a `body`.
- `list` vypíše všech 6 tasků. `--status ready` dá přesně ready tasky ze sample (M01-S01-T02, M02-S01-T01). `--step M02-S01` vypíše 2 tasky. `--module M02` také. `--status bogus --json` vrátí `invalid_status`, `--module nope --json` vrátí `unknown_module`, obojí exit 2.
- Neplatný config (`write(root, ".factory/config.yaml", "levels: [x]\n")`) vrátí u `task list --json` exit 2 a `invalid_config`.

Upravit **`aifactory/tests/test_smoke.py`**: do skip tuple přidat `"task"` a přidat `assert main(["task"]) == 0`. (Po změně bude jediný neimplementovaný `workflow`.)

Všechny testy musí být typově čisté pro `mypy --strict` (anotace `-> None`, `Capsys = pytest.CaptureFixture[str]`, `Any` pro JSON).

### 5. Dokumentace (volitelné, krátce)

Pokud zbude prostor, přidat `app_docs/faa6efc2_task-cli-commands.md` s přehledem příkazů a tabulkou kódů. Není to podmínka hotovo.

## Soubory

- upravit: `aifactory/src/aifactory/backlog/taskfile.py`, `aifactory/src/aifactory/backlog/__init__.py`, `aifactory/src/aifactory/backlog/render.py` (zveřejnit `waits_for`, stávající `_waits_for` přejmenovat nebo aliasovat a vnitřní volání upravit), `aifactory/src/aifactory/cli.py`, `aifactory/tests/test_smoke.py`
- nové: `aifactory/src/aifactory/backlog/edit.py`, `aifactory/tests/backlog/test_task_taskfile_fields.py`, `aifactory/tests/backlog/test_task_edit.py`, `aifactory/tests/backlog/test_task_cli.py`
- neměnit: `vendor/`, `prototype/`, `aifactory/tests/backlog/fixtures/sample/` (testy pracují na kopii přes `sample_repo`), chráněné soubory ADW

## Ověření

```sh
just test tests/backlog
just test
just typecheck
just lint          # ruff check + ruff format --check; případně nejdřív `cd aifactory && uv run ruff format .`
# ruční kontrola na kopii sample:
cp -r aifactory/tests/backlog/fixtures/sample /tmp/s && just factory task add M01-S01 "Nový task" --repo /tmp/s
just factory task link M01-S01-T01 --depends-on M01-S01-T02 --repo /tmp/s --json   # exit 1, code cycle
just factory task list --repo /tmp/s --status ready
just factory task show M01-S01-T03 --repo /tmp/s
```

Úspěch se posuzuje podle exit kódu příkazů, ne podle textu výstupu.
