# HAIFA-S05-T01: Položky knihovny – model, verze a semínko

## Co se změnilo a proč

Balíček `aifactory` nově umí pracovat s **položkami knihovny HAIFA**: typy `agent`, `workflow`, `skill` a `extension` (rozšíření pi). Každá položka má **verzi `sha256:<hex>`** spočtenou z kanonického obsahu, takže stejný obsah dá stejnou verzi v knihovně, v kopii `.factory/` repa i pod jiným jménem. Na tom stojí hybridní konfigurace. Balíček zároveň nese **semínko knihovny**: pět agentů (planner, builder, reviewer, documenter, scout) s prompty a výchozími vazbami. Balíčkové workflow `scout` tak konečně má svého agenta.

## Kde to je

| Soubor | Obsah |
|---|---|
| `aifactory/src/aifactory/library/model.py` | `ItemType`, `ITEM_TYPES`, `NAME_RE` (`[a-z0-9][a-z0-9-]{0,47}`), limity `MAX_ITEM_BYTES` (2 MB) a `MAX_ITEM_FILES` (200), `ItemFile`, `Item` (vlastnost `version`), `AgentDefaults` (pydantic, `extra="forbid"`), `LibraryError(issues)` |
| `aifactory/src/aifactory/library/version.py` | `agent_version`, `workflow_version`, `tree_version`, `item_version` |
| `aifactory/src/aifactory/library/load.py` | čtení z rozložení knihovny i z repa, validace obsahu (`check_*`, `load_*`, `validate_item`) |
| `aifactory/src/aifactory/library/agent.py` | `expand_writes`, `roster_entry` |
| `aifactory/src/aifactory/library/seed.py` | `SEED_DIR`, `SEED_AGENTS`, `seed_agent_names`, `seed_workflow_names`, `seed_items` |
| `aifactory/src/aifactory/library/__init__.py` | veřejné API balíčku |
| `aifactory/src/aifactory/config/loader.py` | nové konstanty `SKILLS_DIR = ".factory/skills"` a `EXTENSIONS_DIR = ".factory/extensions"` |
| `aifactory/src/aifactory/seed/agents/<jméno>/{agent.yaml,system.md,user.md}` | semínko pěti agentů |
| `aifactory/tests/library/` | testy (`library_tree.py` jsou pomocné funkce pro stavbu stromů) |

### Rozložení

- **Knihovna:** `agents/<jméno>/{agent.yaml,system.md,user.md}`, `workflows/<jméno>.yaml`, `skills/<jméno>/`, `extensions/<jméno>/`.
- **Repo:** purpose agenta z `.factory/agents.yaml`, prompty z `.factory/prompts/<jméno>/`, `.factory/workflows/<jméno>.yaml`, `.factory/skills/<jméno>/`, `.factory/extensions/<jméno>/`.

### Verze (`version.py`)

Do hashe nevstupuje jméno ani typ položky. Jednotlivé části se kódují jako netstring `<délka>:<data>,`, takže se nemohou slít.
- **agent** = purpose + `system.md` + `user.md`. `defaults` ani spustitelnost promptů verzi nemění.
- **workflow** = bajty souboru.
- **skill / extension** = soubory seřazené podle UTF-8 cesty, za každý relativní cesta, příznak `0`/`1` pro spustitelnost (`S_IXUSR`) a bajty.

### Validace (`load.py`)

`check_library_item(root, type, name)` a `check_repo_item(repo, type, name)` vrátí `(Item | None, list[Issue])` a sesbírají všechny problémy najednou. `load_*` při jakémkoli problému vyhodí `LibraryError` se všemi problémy. Kontroluje se:
- typ a jméno (`invalid_type`, `invalid_name`),
- symlinky se odmítají a nikdy se nenásledují (`symlink`), stejně jako speciální soubory (`not_a_file`),
- limity na položku (`too_many_files`, `too_large`); u knihovního agenta se počítá i `agent.yaml`,
- `agent.yaml`: mapování jen s klíči `purpose` (neprázdný řetězec) a `defaults`. V `defaults` se harness kanonizuje přes `harness.canonical`, `thinking` musí patřit do `THINKING_LEVELS`, `writes` smí začínat jen `$specs_dir/` nebo `$docs_dir/` a jména ve `skills`/`extensions` musí odpovídat `NAME_RE`,
- agent v repu musí být v rosteru (`unknown_agent`),
- workflow: UTF-8 YAML mapování, které projde `parse_workflow(raw, load_roles())`. Chyby workflow se přenesou s cestou `<rel>:<path>`,
- skill: `SKILL.md` s YAML front matter (`parse_frontmatter`), `name` se rovná jménu složky a `description` není prázdný,
- extension: musí obsahovat vstupní soubor `<jméno>.ts`.

### Agent v projektu (`agent.py`)

- `expand_writes(writes, settings)` nahradí prefix `$specs_dir/` / `$docs_dir/` hodnotou `ProjectSettings.specs_dir` / `docs_dir` (koncové `/` normalizuje). Na jakoukoli jinou proměnnou vyhodí `ValueError`.
- `roster_entry(item, settings)` sestaví záznam do `.factory/agents.yaml` z knihovního agenta (`name`, `purpose`, a jen nastavené `harness`, `model`, `thinking`, `tools`, `writes`, `color`). Klíče `skills` a `extensions` do rosteru nepíše.

### Semínko

- Všech pět agentů má `harness: claude`, `model: claude-opus-5-5`, `thinking: medium`. `writes`: planner `$specs_dir/`, documenter `$docs_dir/`, reviewer a scout `[]`, builder bez `writes`.
- Prompty planneru, builderu, revieweru a documenteru jsou podle testů bajtově shodné s `.factory/prompts/` repa HAIFA, purpose a vazby odpovídají `.factory/agents.yaml`.
- Prompty scouta jsou z `vendor/sssf/templates/prompt_engineering/scout/` doplněné o odstavec, že `<context_handoff_dir>` leží mimo repo, a v `system.md` o zákaz git příkazů. Neobsahují `adw_id`.
- Workflow semínka se nekopírují. `seed_items()` je načítá přímo z `DEFAULT_WORKFLOWS_DIR` (`aifactory/defaults/workflows/`).

## Použití

```python
from pathlib import Path
from aifactory.library import SEED_DIR, load_library_item, load_repo_item, roster_entry
from aifactory.config.settings import ProjectSettings

item = load_library_item(Path("~/lib").expanduser(), "skill", "lint")
item.version                          # "sha256:…"
load_repo_item(Path("."), "agent", "planner").version
roster_entry(load_library_item(SEED_DIR, "agent", "planner"), ProjectSettings())
```

## Ověření

```
just test tests/library   # just test spouští pytest v aifactory/
just typecheck
just lint
```

Testy pokrývají:
- zlaté verze pro každý typ a shodnou verzi z knihovny i z repa (u workflow i pod jiným jménem),
- změnu verze po změně bajtu, spustitelnosti nebo názvu souboru,
- nezávislost verze na `defaults` a na pořadí souborů,
- každou chybu validace,
- `expand_writes` a `roster_entry`,
- shodu semínka s HAIFA,
- odvození scouta z vendoru,
- dočasné repo s rosterem ze semínka (všech 5 agentů): projde `load_config` a `preflight` každého balíčkového workflow včetně `scout`.

Testy nevolají model ani síť.
