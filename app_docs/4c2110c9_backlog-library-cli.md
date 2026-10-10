# Knihovna backlogu a `factory backlog check|list`

Session `4c2110c9` · spec `specs/4c2110c9_backlog-library-cli.md`

## Co se změnilo

Do `aifactory` přibyl balíček `aifactory.backlog`: přenesená knihovna, která čte backlog v markdownu. K ní dva příkazy CLI:

- `factory backlog check [--json] [--repo PATH]` validuje backlog. Vrací `0` = OK, `1` = nalezené chyby, `2` = neplatný `.factory/config.yaml`.
- `factory backlog list [--json] [--status S] [--module ID] [--repo PATH]` vypíše strom s odvozenými stavy.

Knihovna soubory **jen čte**. Stavy `ready`/`blocked` i zpětné odkazy „blocks“ se počítají v paměti a nikam se neukládají.

## Model backlogu

- Úrovně stromu se berou z `levels` v `.factory/config.yaml` (výchozí `module → step → task`) a adresář backlogu z `backlog_dir`. Každá úroveň kromě poslední je adresář s `index.md`, poslední úroveň tvoří soubory `*.md` s YAML hlavičkou.
- `index.md` musí mít `id` a `title`. Klíče `owner`, `source`, `target`, `test`, `workflow`, `writes` a `auto_continue` jsou výchozí hodnoty, které tasky dědí. Ostatní klíče jdou do `extra`.
- Task má povinné `id`, `title` a `status` (`todo | done | cancelled`). Volitelné jsou seznamy `depends_on`, `related` a `writes`.
- Dědění (`effective()`): nejdřív se vezmou hodnoty nejvyššího předka, bližší předek je přepíše a vlastní hodnoty tasku mají přednost.
- Odvozený stav (`derived_state()`): `done`/`cancelled` zůstávají, jak jsou uložené. `todo` se změní na `blocked`, pokud má nesplněnou závislost, jinak na `ready`. Neplatný status vrací `invalid`.
- Kontejner (step, modul) je hotový, když jsou `done` všechny jeho potomkovské tasky mimo `cancelled`. Prázdný kontejner hotový není. Závislost na kontejneru proto čeká, dokud nejsou hotové všechny jeho tasky (`reason: incomplete` se seznamem chybějících).

## Validace (`check_backlog`)

Každá chyba je `Issue(code, message, path, id)`. `path` je relativní ke kořeni repa a ukazuje na soubor tasku nebo na `index.md`. Výstup je seřazený podle cesty. Kódy chyb:

| kód | kdy |
|---|---|
| `duplicate_id` | id se opakuje, zpráva uvádí i místo prvního výskytu |
| `unknown_ref` | `depends_on`/`related` odkazuje na neexistující task nebo step |
| `cycle` | cyklus v grafu závislostí (Tarjan). Graf obsahuje i hrany kontejner → jeho tasky, takže cyklem je i task závislý na vlastním stepu |
| `invalid_status` | status mimo `todo/done/cancelled` |
| `missing_field` / `invalid_field` | chybí `id`/`title`/`status` nebo má pole špatný typ (např. `depends_on` není seznam řetězců) |
| `id_prefix` | id nezačíná id předka + `-` |
| `invalid_frontmatter`, `missing_index`, `misplaced_file`, `misplaced_dir`, `missing_backlog_dir` | strukturální chyby |

## Kde to je

`aifactory/src/aifactory/backlog/`:
- `model.py`: dataclassy `Container`, `Task`, `Issue`, `Unmet`, `Backlog` a konstanty (`VALID_STATUSES`, `INHERITED_KEYS`).
- `frontmatter.py`: `parse_frontmatter()`, která rozdělí soubor na YAML hlavičku a tělo.
- `loader.py`: `load_backlog(root)`, `load_settings()` a iterátory `iter_nodes`/`iter_tasks`/`iter_containers`.
- `derived.py`: dědění, `is_done`, `unmet`, `derived_state`, `blocks`, `progress`.
- `validate.py`: `check_backlog()` včetně detekce cyklů.
- `render.py`: `format_tree()` (text), `backlog_to_json()`, `issues_to_json()`, `counts()`, `select_modules()` a `STATUS_FILTERS`.
- `taskfile.py`: textová úprava souboru tasku (`mark_done`, `run_entry`, `has_entry`), která nastaví `status: done` a přidá řádek do `## Běhy`. Ostatní bajty souboru nemění. Příkazy z této změny ji **nevolají**.
- `__init__.py`: veřejné API.

`aifactory/src/aifactory/cli.py` přidává podpříkaz `backlog`. Bez `--repo` se použije kořen aktuálního git repa, a když to nejde, aktuální adresář. Holé `factory backlog` vypíše nápovědu a vrátí `0`, s tím počítá upravený `aifactory/tests/test_smoke.py`.

## Výstup

`backlog list`: odsazení po dvou mezerách na úroveň. U kontejneru se zobrazuje `[hotovo/celkem]`, případně `done`. U tasku stav, u `blocked` navíc `(waits for: …)`, a kde je co zobrazit, i `(blocks: …)`.
- `--status` přijímá `todo|done|cancelled|ready|blocked` a skryje kontejnery, ve kterých žádný task neodpovídá.
- `--module` přijímá id nebo název adresáře. Neznámý modul vrátí kód `2`.
- Chybějící `backlog_dir` vrátí kód `1`. Ostatní problémy vypíšou strom a na stderr hlášku `N problem(s), run 'factory backlog check'`.

`backlog check` bez chyb vypíše `OK: 2 module, 3 step, 6 task` (počty podle názvů úrovní). S chybami vypíše řádky `cesta: kód: zpráva` a nakonec `N error(s)`.

JSON (`--json`): `check` → `{ok, errors[], counts}`. `list` → `{ok, levels, backlog_dir, filters, items[], issues[]}`, kde task nese `status`, `state`, `effective`, `workflow`, `writes`, `own_writes`, `blocked_by`, `blocks` a kontejner nese `progress`, `done`, `defaults`, `children`.

## Ověření

```sh
just test tests/backlog      # 60 testovacích funkcí v aifactory/tests/backlog/
just test && just typecheck && just lint
just factory backlog check --repo aifactory/tests/backlog/fixtures/sample
just factory backlog list  --repo aifactory/tests/backlog/fixtures/sample --status ready
```

Vzorový backlog `aifactory/tests/backlog/fixtures/sample/` má moduly `M01-core` a `M02-ui` a ukazuje dědění z `index.md` i závislost na stepu (`M01-S02-T01` → `M01-S01`). Testy používají pomocníka `aifactory/tests/backlog/backlog_repo.py`. Pokrývají parsování hlavičky, načtení, validaci, render, CLI a `taskfile`.
