# Plán: načtení a validace backlogu (`backlog check`, `backlog list`)

## Cíl

Implementovat v prototypu načtení backlogu HAIFA podle sekce „Backlog v markdownu“ v `docs/product-brief.md`:
strom adresářů modul → step → task, task = markdown soubor s YAML hlavičkou, dědění výchozích hodnot
z `index.md`, odvozené stavy `ready`/`blocked`, dopočítané „blokuje“, validaci a dva příkazy CLI:
`haifa-proto backlog check` a `haifa-proto backlog list` (oba s `--json`).

Mimo rozsah: spouštění tasků, trace, zápis stavu `done`, web, příkazy `task *`, `backlog sync`.

Pevná omezení:
- Kód soubory backlogu **jen čte**, nikdy nezapisuje.
- V souborech je jen `depends_on` (a `related`). „Blokuje“ (`blocks`) se počítá v paměti, nikdy se neukládá.
- Stavy `running`, `failed`, `in review` se neřeší vůbec (nejsou platné hodnoty `status`, nikde se neobjeví).
- `vendor/`, `adws/`, `docs/product-brief.md`, kořenový `backlog/` a `BACKLOG.md` se neupravují.

## Stávající stav

- `prototype/src/haifa_proto/cli.py`: argparse, subpříkazy `backlog`, `task`, `serve` jsou no-op a vrací 0.
- `prototype/tests/test_cli.py`: test `test_subcommands_are_noops` volá `main(["backlog"])` a čeká 0 — **musí dál projít**
  (holé `backlog` bez podpříkazu vypíše nápovědu k `backlog` a vrátí 0).
- Závislosti v `prototype/pyproject.toml` už obsahují `pyyaml`, `pydantic`, `rich`; dev `types-PyYAML`, `mypy --strict`, `ruff` (line-length 100, pravidla E,F,I,UP,B). Nic nepřidávat.
- Ověření: `just test`, `just typecheck`, `just lint` (z kořene repa; běží v `prototype/`).

## Soubory

| Soubor | Akce |
|---|---|
| `prototype/src/haifa_proto/config.py` | nový — načtení `.factory/config.yaml` |
| `prototype/src/haifa_proto/backlog.py` | nový — model, načtení, dědění, odvozené stavy, validace, serializace |
| `prototype/src/haifa_proto/cli.py` | upravit — podpříkazy `backlog check` a `backlog list` |
| `prototype/tests/fixtures/backlog/...` | nový — vzorový repozitář (viz níže) |
| `prototype/tests/conftest.py` | nový — fixture `sample_repo` (kopie vzorových dat do `tmp_path`) |
| `prototype/tests/test_config.py` | nový |
| `prototype/tests/test_backlog_load.py` | nový — načtení, dědění, stavy, blocks |
| `prototype/tests/test_backlog_check.py` | nový — každá validace s rozbitou kopií |
| `prototype/tests/test_cli_backlog.py` | nový — CLI, návratové kódy, `--json` |
| `prototype/tests/test_cli.py` | nechat beze změny (musí projít) |

## 1. `config.py`

```python
DEFAULT_LEVELS = ("module", "step", "task")
CONFIG_PATH = Path(".factory") / "config.yaml"

class ConfigError(Exception): ...

@dataclass(frozen=True)
class FactoryConfig:
    levels: tuple[str, ...] = DEFAULT_LEVELS
    backlog_dir: str = "backlog"

def load_config(repo_root: Path) -> FactoryConfig
```

- Soubor chybí → výchozí hodnoty. Prázdný soubor (`None`) → výchozí hodnoty.
- Kořen YAML není mapa → `ConfigError`. Ostatní klíče v souboru se ignorují (budoucí nastavení).
- `levels`: seznam neprázdných unikátních řetězců, délka ≥ 2 (aspoň jedna úroveň kontejneru + task), jinak `ConfigError`.
  Poslední úroveň je vždy úroveň tasku (souboru), předchozí jsou adresáře.
- `backlog_dir`: neprázdný řetězec, relativní cesta vůči `repo_root`; jinak `ConfigError`.
- Neplatné YAML → `ConfigError` se zprávou obsahující cestu.
- Může použít pydantic nebo ruční validaci; výsledkem musí být výše uvedený typ (mypy strict).

## 2. `backlog.py`

### Datový model (dataclasses, vše typované)

```python
VALID_STATUSES = ("todo", "done", "cancelled")
INHERITED_KEYS = ("owner", "source", "target", "test", "workflow", "auto_continue")

@dataclass
class Issue:
    code: str          # viz tabulka kódů
    message: str       # anglicky, lidsky čitelné
    path: str          # cesta relativní k repo_root, posix, "" když není
    id: str | None = None
    def to_dict(self) -> dict[str, object]

@dataclass
class Container:           # modul, step (obecně libovolná neleaf úroveň)
    id: str | None         # None, když index.md chybí nebo je neplatný
    title: str | None
    level: str             # jméno úrovně z configu
    path: str              # relativní cesta k adresáři
    defaults: dict[str, object]   # jen klíče z INHERITED_KEYS uvedené v index.md
    extra: dict[str, object]      # zbytek hlavičky (description apod.), nevalidovat
    parent: Container | None
    children: list[Container]
    tasks: list[Task]

@dataclass
class Task:
    id: str
    title: str
    status: str            # hodnota ze souboru (po validaci jedna z VALID_STATUSES)
    level: str             # levels[-1]
    path: str
    own: dict[str, object]        # INHERITED_KEYS uvedené přímo v hlavičce tasku
    depends_on: list[str]
    related: list[str]
    writes: list[str]
    parent: Container      # step
    body: str

@dataclass
class Backlog:
    root: Path             # repo_root
    config: FactoryConfig
    containers: list[Container]   # nejvyšší úroveň (moduly), seřazené podle jména adresáře
    issues: list[Issue]           # problémy nalezené už při načítání
    # pomocné indexy vytvořené po načtení:
    by_id: dict[str, Container | Task]   # první výskyt podle seřazené cesty
```

### Parsování hlavičky

`parse_frontmatter(text: str) -> tuple[dict[str, object], str]`:
- Soubor musí začínat řádkem `---`; hlavička končí dalším řádkem, který je přesně `---`. Zbytek = tělo.
- `yaml.safe_load`; výsledek musí být `dict` (prázdná hlavička → `{}`), jinak chyba.
- Chybějící/neukončená hlavička nebo YAML chyba → vyhodit interní výjimku, kterou loader převede na `Issue("invalid_frontmatter", ...)`.
- Soubory číst `encoding="utf-8"`.

### Načtení stromu — `load_backlog(repo_root: Path, config: FactoryConfig | None = None) -> Backlog`

- `config is None` → `load_config(repo_root)`.
- `backlog_root = repo_root / config.backlog_dir`. Neexistuje / není adresář → `Backlog` bez kontejnerů s `Issue("missing_backlog_dir", ...)`.
- Počet úrovní `n = len(levels)`. Adresáře v hloubce `0 .. n-2` pod `backlog_root` jsou kontejnery úrovně `levels[depth]`.
  Tasky jsou soubory `*.md` (kromě `index.md`) přímo v kontejneru hloubky `n-2`.
- Procházení: položky seřadit podle jména; přeskočit vše, co začíná `.`; ne-`.md` soubory ignorovat.
- Kontejner:
  - `index.md` chybí → `Issue("missing_index", path=<adresář>)`, kontejner vznikne s `id=None`, do potomků se dál sestupuje.
  - `index.md` načíst; povinné `id` a `title` (neprázdné řetězce) → jinak `missing_field` / `invalid_field`.
  - Klíče z `INHERITED_KEYS` → `defaults`; ostatní kromě `id`, `title` → `extra`.
- Soubor `*.md` jiný než `index.md` na úrovni, kde nemá být task (hloubka < n-2 nebo přímo v `backlog_root`) → `Issue("misplaced_file")`.
  Adresář v kontejneru hloubky `n-2` (hlouběji, než dovolují `levels`) → `Issue("misplaced_dir")`, dovnitř se nesestupuje.
- Task:
  - Povinné: `id`, `title` (neprázdné řetězce), `status`. Chybí → `missing_field` (task se přesto vloží, pokud má `id`; bez `id` se přeskočí).
  - `status` mimo `VALID_STATUSES` (včetně `running`, `failed`, `in review`) → `invalid_status`; task se vloží se zachovanou hodnotou,
    jeho odvozený stav je `"invalid"` a v závislostech se bere jako nehotový.
  - `depends_on`, `related`, `writes`: volitelné, výchozí `[]`; musí být seznam řetězců (samotný řetězec → chyba) → jinak `invalid_field`.
  - `workflow` a ostatní `INHERITED_KEYS` → `own`. Ostatní neznámé klíče tolerovat.
  - Hodnota `id`, která není řetězec (YAML převede `2024` na int) → `invalid_field`.

### Dědění

`effective(task) -> dict[str, object]`: začít od nejvyššího předka, přepisovat hodnotami bližších předků, nakonec `task.own`.
Vrací jen klíče z `INHERITED_KEYS`, které jsou někde nastavené. `effective_workflow(task) = effective(task).get("workflow")`.

### Indexy a odkazy

- `iter_nodes(backlog)` — všechny kontejnery s `id` a všechny tasky v deterministickém pořadí (DFS, seřazené podle cesty).
- `by_id`: první výskyt vyhrává (duplicity řeší validace).
- Odkaz v `depends_on` smí mířit na task nebo na kontejner (step; obecně jakýkoli kontejner — modul funguje stejně, „hotový, když jsou hotové všechny jeho tasky“).
- `blocks(backlog) -> dict[str, list[str]]`: pro každý task `X` a každé `Y` v `X.depends_on`, které existuje v `by_id`, přidat `X` do `blocks[Y]`. Seznamy seřazené. **Jen v paměti.**

### Hotovost a odvozený stav

- Task je hotový ⇔ `status == "done"`.
- Kontejner je hotový ⇔ má aspoň jeden potomkový task se stavem jiným než `cancelled` a všechny takové tasky jsou `done`.
  (`cancelled` tasky se do hotovosti kontejneru nepočítají. Kontejner bez tasků / jen se zrušenými není hotový.)
- `unmet(backlog, task) -> list[Unmet]`, kde `Unmet = {id: str, reason: str, missing: list[str]}`:
  - `reason="unknown"` — id neexistuje;
  - `reason="not_done"` — task není `done` (`missing=[id]`);
  - `reason="cancelled"` — přímá závislost na zrušeném tasku (nesplněná);
  - `reason="incomplete"` — kontejner, `missing` = seřazená id potomkových nehotových, nezrušených tasků (prázdný kontejner → `reason="empty"`).
- `derived_state(task)`:
  - `done` → `"done"`, `cancelled` → `"cancelled"`, neplatný status → `"invalid"`;
  - `todo` a `unmet` prázdné → `"ready"`; jinak `"blocked"` (s výpisem `unmet`).
- Souhrn kontejneru: `done_count`, `total` (bez `cancelled`), pro výpis.

### Validace — `check_backlog(backlog: Backlog) -> list[Issue]`

Vrátí `backlog.issues` (z načítání) + níže uvedené, seřazené stabilně (podle `path`, pak `code`, pak `message`).

| Kód | Kdy | Zpráva musí obsahovat |
|---|---|---|
| `missing_backlog_dir` | `backlog_dir` neexistuje | cestu |
| `missing_index` | kontejnerový adresář bez `index.md` | cestu adresáře |
| `invalid_frontmatter` | hlavička chybí / neukončená / neplatné YAML / není mapa | cestu |
| `missing_field` / `invalid_field` | chybí nebo má špatný typ `id`, `title`, `status`, `depends_on`, `related`, `writes` | jméno pole |
| `invalid_status` | `status` mimo `todo|done|cancelled` | nalezenou hodnotu a povolené |
| `duplicate_id` | stejné `id` u dvou uzlů (task i kontejner, napříč celým stromem) | id a **obě** cesty; jedno Issue na každý další výskyt |
| `unknown_ref` | id v `depends_on` nebo `related` neexistuje | id tasku, jméno pole, neznámé id |
| `id_prefix` | id uzlu nezačíná `<id předka>-` pro **každého** předka s id (task vůči stepu i modulu, step vůči modulu) | id uzlu a očekávaný prefix |
| `cycle` | cyklus v grafu závislostí | cestu cyklu `A -> B -> ... -> A` |
| `misplaced_file` / `misplaced_dir` | viz načtení | cestu |
| `self_dependency` | nepotřeba — self-loop se hlásí jako `cycle` (`A -> A`) | — |

**Graf pro cykly:** uzly = id všech tasků a kontejnerů. Hrany:
- task `X` → každé existující `Y` v `X.depends_on`;
- kontejner `C` → každý jeho potomkový task, který není `cancelled` (kontejner „čeká“ na své tasky).
Díky implicitním hranám se odhalí i skrytý cyklus, např. task závisí na vlastním stepu (`M01-S01-T01 -> M01-S01 -> M01-S01-T01`)
nebo step A čeká na task, který závisí na stepu B, jehož task závisí na stepu A. `related` se do grafu nezapočítává.

Algoritmus: Tarjanovy SCC (iterativně nebo rekurzivně — backlog je malý), sousedy procházet seřazené. Pro každou SCC s více uzly
nebo se self-loopem najít jednu cyklickou cestu DFS uvnitř SCC začínající u nejmenšího id a nahlásit ji jako jedno `Issue("cycle")`
(`id` = počáteční uzel, `path` = cesta souboru počátečního uzlu). Výstup deterministický.

### Serializace

- `issues_to_json(issues) -> dict`: `{"ok": bool, "errors": [issue.to_dict()...], "counts": {"module": 2, "step": 3, "task": 6}}`
  (`counts` podle jmen úrovní z configu).
- `backlog_to_json(backlog) -> dict`:
  ```json
  {
    "levels": ["module", "step", "task"],
    "backlog_dir": "backlog",
    "items": [ <uzel> ],
    "issues": [ <issue> ]
  }
  ```
  Kontejner: `{"kind": "container", "id", "title", "level", "path", "done": n, "total": n, "blocks": [...], "children": [...]}`,
  kde `children` obsahuje nejdřív podkontejnery, pak tasky (obojí seřazené podle cesty).
  Task: `{"kind": "task", "id", "title", "level", "path", "status", "state", "workflow", "effective": {...},
  "depends_on", "related", "writes", "blocked_by": [{"id", "reason", "missing"}], "blocks": [...]}`.
  Vše musí projít `json.dumps` (žádné `Path`, množiny apod.).

## 3. CLI (`cli.py`)

```
haifa-proto backlog check [--repo PATH] [--json]
haifa-proto backlog list  [--repo PATH] [--json]
```

- `backlog` s vnořenými subparsery (`dest="backlog_command"`). Holé `haifa-proto backlog` → vypíše nápovědu `backlog`, vrátí 0 (kvůli `test_subcommands_are_noops`).
- `--repo` výchozí `Path.cwd()`. Konfigurace z `<repo>/.factory/config.yaml`.
- `ConfigError` → zpráva na stderr (při `--json` na stdout `{"ok": false, "errors": [{"code": "invalid_config", ...}]}`), návratový kód 1.
- `task` a `serve` zůstávají no-op jako dnes.
- `check`:
  - bez chyb → vypíše `OK: 2 module, 3 step, 6 task` (formát libovolný, ale obsahuje `OK`), kód **0**;
  - s chybami → každý řádek `<path>: <code>: <message>`, poslední řádek `N error(s)`, kód **1**;
  - `--json` → `issues_to_json` na stdout (`json.dumps(..., ensure_ascii=False, indent=2)`), kódy stejně.
- `list`:
  - lidský výstup: strom s odsazením 2 mezery na úroveň, např.
    ```
    M01 Core [1/3 done]
      M01-S01 Model [1/2 done]
        M01-S01-T01 Schema  done
        M01-S01-T02 Loader  ready
      M01-S02 API [0/1 done]
        M01-S02-T01 Endpoint  blocked (waits for: M01-S01 [M01-S01-T02])
        M01-S02-T02 Docs  cancelled
    ```
    u blokovaného tasku vypsat, na co čeká; u uzlů s neprázdným `blocks` může být `blocks: ...` (volitelné).
    Kontejner bez id zobrazit jako `? <path>`.
  - `--json` → `backlog_to_json`.
  - Kód 0; kód 1 jen když chybí `backlog_dir` nebo je chybný config. Jsou-li jiné problémy, v lidském režimu napsat na stderr
    `N problem(s), run 'haifa-proto backlog check'`.
- Výstup psát přes `print` (ne rich), aby šel testovat přes `capsys`.

## 4. Vzorová data — `prototype/tests/fixtures/backlog/`

Adresář je kořen vzorového repa (předává se jako `--repo`):

```
tests/fixtures/backlog/
  .factory/config.yaml            # levels: [module, step, task]\nbacklog_dir: backlog
  backlog/
    M01-core/index.md             # id: M01, title: Core, owner: alice, workflow: plan-build,
                                  # test: "uv run pytest", source: src/, target: src/
      S01-model/index.md          # id: M01-S01, title: Model
        M01-S01-T01-schema.md     # status: done
        M01-S01-T02-loader.md     # status: todo, depends_on: [M01-S01-T01],
                                  # workflow: plan-build-test-review (přepis zděděné hodnoty)
      S02-api/index.md            # id: M01-S02, title: API, workflow: plan-build-test
        M01-S02-T01-endpoint.md   # status: todo, depends_on: [M01-S01]  ← závislost na STEP
                                  # related: [M02-S01-T01], writes: [src/api/]
        M01-S02-T02-docs.md       # status: cancelled
    M02-ui/index.md               # id: M02, title: UI, owner: bob, workflow: plan-build
      S01-list/index.md           # id: M02-S01, title: List
        M02-S01-T01-view.md       # status: todo, depends_on: [M01-S01-T01]  ← mezi moduly (splněná)
        M02-S01-T02-filter.md     # status: todo, depends_on: [M02-S01-T01, M01-S02-T01] ← mezi moduly
```

Očekávané stavy: `M01-S01-T01 done`, `M01-S01-T02 ready` (workflow `plan-build-test-review`),
`M01-S02-T01 blocked` (čeká na `M01-S01`, chybí `M01-S01-T02`; workflow `plan-build-test` ze stepu; owner `alice` z modulu),
`M01-S02-T02 cancelled`, `M02-S01-T01 ready` (owner `bob`), `M02-S01-T02 blocked` (chybí `M02-S01-T01` i `M01-S02-T01`).
`blocks`: `M01-S01-T01 → [M01-S01-T02, M02-S01-T01]`, `M01-S01 → [M01-S02-T01]`, `M01-S02-T01 → [M02-S01-T02]`, `M02-S01-T01 → [M02-S01-T02]`.
Vzorový backlog je čistý: `check` → 0 chyb. Každý task má tělo se sekcí `## Zadání` a prázdnou `## Běhy`.
Každý `index.md` má krátký popis v těle.

Pozor: kořenový `backlog/` v HAIFA repu je jiný formát (fáze) — nic s ním nedělat a netestovat proti němu.

## 5. Testy

`conftest.py`:
```python
FIXTURE = Path(__file__).parent / "fixtures" / "backlog"
@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    dst = tmp_path / "repo"; shutil.copytree(FIXTURE, dst); return dst
```
Rozbíjení vždy jen na kopii v `tmp_path`, nikdy ve `fixtures/`. Pomocná funkce `rewrite(path, old, new)` pro úpravu hlavičky.

`test_config.py`:
- chybějící `.factory/config.yaml` → `levels == ("module","step","task")`, `backlog_dir == "backlog"`;
- vlastní `levels: [module, task]` a `backlog_dir: items` se načtou;
- neplatné YAML / `levels` s jednou položkou / duplicitní úrovně → `ConfigError`.

`test_backlog_load.py` (nad `sample_repo`):
- počty: 2 moduly, 3 stepy, 6 tasků;
- odvozené stavy všech 6 tasků dle tabulky výše;
- `blocked_by` u `M01-S02-T01` = `[{"id": "M01-S01", "reason": "incomplete", "missing": ["M01-S01-T02"]}]`;
- po přepnutí `M01-S01-T02` na `done` je `M01-S02-T01` `ready` (step hotový);
- dědění: owner/workflow/test/source/target dle popisu; vlastní hodnota tasku má přednost;
- `blocks` odpovídá výpisu výše a v žádném souboru se neobjeví klíč `blocks` (načtení nic nezapíše: porovnat mtime/obsah všech souborů před a po `load_backlog` + `check_backlog` + `backlog_to_json`);
- dvouúrovňová konfigurace `levels: [module, task]` na malém stromu v `tmp_path` funguje (tasky přímo v adresáři modulu);
- `backlog_to_json` projde `json.dumps`.

`test_backlog_check.py` — čistá kopie → `[]`; pak pro každou validaci jedna rozbitá kopie a assert na `code` (+ klíčové části zprávy):
- `duplicate_id`: `M02-S01-T02` přepsat na `id: M02-S01-T01` (zpráva obsahuje obě cesty);
- `unknown_ref` v `depends_on` (`M09-S01-T01`) a zvlášť v `related`;
- `cycle`: `M01-S01-T01` dostane `depends_on: [M01-S01-T02]` → zpráva obsahuje `M01-S01-T01 -> M01-S01-T02 -> M01-S01-T01`;
- `cycle` přes step: task `M01-S01-T01` s `depends_on: [M01-S01]` → cesta obsahuje `M01-S01`;
- `invalid_status`: `status: running` (a zvlášť `status: in review`);
- `missing_index`: smazat `backlog/M02-ui/S01-list/index.md`, a zvlášť `backlog/M02-ui/index.md`;
- `id_prefix`: task v `S01-list` s id `M02-S02-T09` (nesedí step), a task s id `M03-S01-T01` (nesedí step ani modul); step s id `M09-S01`;
- `invalid_frontmatter`: task bez `---` hlavičky;
- `missing_field`: task bez `title`;
- `missing_backlog_dir`: smazat `backlog/`.

`test_cli_backlog.py` (volat `main([...])` přímo, `capsys`):
- `backlog check --repo <sample>` → 0, výstup obsahuje `OK`;
- `backlog check --repo <broken>` → 1, výstup obsahuje kód chyby;
- `backlog check --json` → validní JSON, `ok` true/false, `errors[*].code`;
- `backlog list --repo <sample>` → 0, obsahuje všechna id a slova `ready`, `blocked`, `done`, `cancelled`;
- `backlog list --json` → `items` má 2 moduly, stav `M01-S02-T01` je `blocked`;
- neplatný config → 1;
- `test_cli.py` beze změny prochází (`main(["backlog"]) == 0`).

## 6. Ověření

Z kořene repa, všechny musí skončit s návratovým kódem 0:
```bash
just test
just typecheck
just lint        # případně nejdřív: cd prototype && uv run ruff format .
just proto backlog check --repo prototype/tests/fixtures/backlog     # exit 0
just proto backlog list --repo prototype/tests/fixtures/backlog
just proto backlog list --json --repo prototype/tests/fixtures/backlog
```
