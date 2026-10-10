# HAIFA-S05-T01 — Položky knihovny: model, verze a semínko (plán)

Návrh: `docs/design/library-onboarding-distribution.md` AR14 (formát), AR15 (verze), AR16 (semínko), AR20 (agent: obsah × vazby), S14 (limity). Toto je úkol L1. Mimo rozsah: knihovna v domově, git, CLI, manifest, skilly v běhu, změny `.factory/` HAIFA, `vendor/`, `prototype/`.

Všechny cesty jsou relativní k worktree. Kód píšeš jen pod `aifactory/` (plus tento spec). `.factory/`, `vendor/` a `prototype/` jen čteš.

## Shrnutí změn

| Soubor | Změna |
|---|---|
| `aifactory/src/aifactory/config/loader.py` | jen dvě nové konstanty `SKILLS_DIR`, `EXTENSIONS_DIR` |
| `aifactory/src/aifactory/library/__init__.py` | nový, re-exporty |
| `aifactory/src/aifactory/library/model.py` | typy, jména, `ItemFile`, `AgentDefaults`, `Item`, `LibraryError` |
| `aifactory/src/aifactory/library/version.py` | kanonický obsah a `sha256:` verze |
| `aifactory/src/aifactory/library/load.py` | načtení z rozložení knihovny a z kopie v repu + validace |
| `aifactory/src/aifactory/library/agent.py` | `expand_writes`, `roster_entry` |
| `aifactory/src/aifactory/library/seed.py` | semínko (`seed/agents/` + balíčková workflow) |
| `aifactory/src/aifactory/seed/agents/{planner,builder,reviewer,documenter,scout}/{agent.yaml,system.md,user.md}` | nová data |
| `aifactory/tests/library/test_library_*.py` | nové testy |

`workflow/parse.py`, `workflow/check.py`, `engine/role_registry.py` a `defaults/workflows/` se **nemění**, jen se používají (`parse_workflow`, `load_roles`, `Issue`, `preflight`, `DEFAULT_WORKFLOWS_DIR`). Kdyby mypy/ruff vyžadovaly drobnou úpravu, smí se, ale není to cílem. `roles.yaml` zůstává: role `scout` už jmenuje agenta `scout`, chyběl jen agent; ten teď dodá semínko.

Balíček se buildí hatchlingem s `packages = ["src/aifactory"]`, takže i `seed/**` (ne-.py soubory) se do wheelu dostanou stejně jako dnes `defaults/workflows/*.yaml`. Do `seed/` nedávej `__init__.py`.

## 1. `config/loader.py`

Vedle `WORKFLOWS_DIR` přidej:
```python
SKILLS_DIR = ".factory/skills"
EXTENSIONS_DIR = ".factory/extensions"
```
Nic jiného se v loaderu nemění (`load_config` je zatím nečte; to je L5).

## 2. `library/model.py`

```python
ItemType = Literal["agent", "workflow", "skill", "extension"]
ITEM_TYPES: tuple[ItemType, ...] = ("agent", "workflow", "skill", "extension")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")   # vždy přes fullmatch
MAX_ITEM_BYTES = 2 * 1024 * 1024
MAX_ITEM_FILES = 200
WRITES_VARIABLES = ("$specs_dir/", "$docs_dir/")

def check_name(name: str) -> bool  # NAME_RE.fullmatch

@dataclass(frozen=True)
class ItemFile:
    path: str          # relativní POSIX cesta uvnitř položky
    executable: bool
    data: bytes

class AgentDefaults(BaseModel):     # pydantic, ConfigDict(frozen=True, extra="forbid")
    harness: str | None = None      # validátor: aifactory.harness.canonical(), vrací kanonické jméno
    model: str | None = None
    thinking: str | None = None     # validátor: v aifactory.harness.override.THINKING_LEVELS
    tools: tuple[str, ...] | None = None
    writes: tuple[str, ...] | None = None   # validátor: položka obsahující "$" musí začínat jednou z WRITES_VARIABLES a za ní už "$" nemá
    color: str | None = None
    skills: tuple[str, ...] = ()    # validátor: každé jméno check_name
    extensions: tuple[str, ...] = ()

@dataclass(frozen=True)
class Item:
    type: ItemType
    name: str
    files: tuple[ItemFile, ...]          # seřazené podle path.encode("utf-8")
    purpose: str = ""                    # jen agent
    defaults: AgentDefaults | None = None  # jen agent z rozložení knihovny; z repa None

    @property
    def version(self) -> str: ...        # volá version.item_version(self)

class LibraryError(Exception):
    def __init__(self, issues: list[Issue]) -> None  # Issue z aifactory.engine.role_registry; message = "; ".join(f"{path}: {code}: {message}")
```
U agenta jsou `files` přesně `system.md` a `user.md` (v tomto pořadí po seřazení), u workflow jediný soubor `<jméno>.yaml`, u skillu a rozšíření celý strom.

## 3. `library/version.py` — přesný kanonický formát

Pomocná funkce (netstring):
```python
def _ns(data: bytes) -> bytes:
    return str(len(data)).encode("ascii") + b":" + data + b","
```
- **agent**: `sha256(_ns(purpose.encode("utf-8")) + _ns(system_bytes) + _ns(user_bytes))`. Spustitelnost ani `defaults` se nepočítají.
- **workflow**: `sha256(bajty souboru)` — nic dalšího.
- **skill / extension**: pro soubory seřazené podle `path.encode("utf-8")`: zřetězit `_ns(path.encode("utf-8")) + (b"1" if executable else b"0") + _ns(data)`, pak `sha256`.
- Výstup: `"sha256:" + hexdigest()`.

API:
```python
def agent_version(purpose: str, system: bytes, user: bytes) -> str
def workflow_version(data: bytes) -> str
def tree_version(files: Iterable[ItemFile]) -> str   # řadí sama
def item_version(item: Item) -> str                   # dispatch podle item.type
```
Jméno položky ani typ do hashe nevstupují → stejný obsah = stejná verze pod jakýmkoli jménem a v obou rozloženích.

## 4. `library/load.py` — načtení a validace

Veřejné API:
```python
def load_library_item(root: Path, type: ItemType, name: str) -> Item     # LibraryError se všemi problémy
def load_repo_item(repo: Path, type: ItemType, name: str) -> Item        # repo = kořen pracovního stromu
def check_library_item(root, type, name) -> tuple[Item | None, list[Issue]]
def check_repo_item(repo, type, name) -> tuple[Item | None, list[Issue]]
def validate_item(item: Item) -> list[Issue]    # obsahová pravidla (workflow, skill, extension)
```
`load_*` = `check_*` a při neprázdných issues `raise LibraryError(issues)`. `check_*` sbírá **všechny** problémy (čtení i obsah) a nikdy nekončí na prvním. `Item` vrátí jen když bylo co hashovat (soubory načteny), i když jsou issues.

Rozložení:

| typ | knihovna (`root/…`) | repo (`repo/…`) |
|---|---|---|
| agent | `agents/<n>/agent.yaml`, `agents/<n>/system.md`, `agents/<n>/user.md` | purpose z `.factory/agents.yaml` (položka `name == n`), prompty `.factory/prompts/<n>/{system,user}.md` (konstanty `AGENTS_FILE`, `PROMPTS_DIR` z `config.loader`) |
| workflow | `workflows/<n>.yaml` | `.factory/workflows/<n>.yaml` (`WORKFLOWS_DIR`) |
| skill | `skills/<n>/` | `.factory/skills/<n>/` (`SKILLS_DIR`) |
| extension | `extensions/<n>/` | `.factory/extensions/<n>/` (`EXTENSIONS_DIR`) |

Chybové kódy (`Issue(code, message, path)`; `path` = cesta relativní k `root`/`repo`, např. `skills/foo/SKILL.md`):

| kód | kdy |
|---|---|
| `invalid_type` | typ mimo `ITEM_TYPES` |
| `invalid_name` | jméno neprojde `NAME_RE.fullmatch` (pak se dál nečte) |
| `missing_item` | složka / soubor položky neexistuje (nebo je to jiný druh, např. adresář místo `<n>.yaml`) |
| `missing_file` | chybí `agent.yaml`, `system.md` nebo `user.md` (každý zvlášť) |
| `symlink` | cokoli v položce (kořen, podadresář, soubor, i `agent.yaml`/prompt/workflow soubor) je symlink — kontroluj přes `lstat`/`is_symlink()`, symlinky nenásleduj |
| `not_a_file` | ve stromu je speciální soubor (ne regulární, ne adresář) |
| `too_many_files` | víc než `MAX_ITEM_FILES` souborů |
| `too_large` | součet velikostí (z `lstat`) víc než `MAX_ITEM_BYTES` |
| `not_utf8` | `agent.yaml`, `agents.yaml`, workflow nebo `SKILL.md` není UTF-8 |
| `invalid_yaml` | YAML se nedá načíst |
| `not_a_mapping` | `agent.yaml` nebo workflow není mapování |
| `unknown_key` | klíč v `agent.yaml` mimo `{purpose, defaults}` |
| `missing_purpose` | `agent.yaml` bez neprázdného řetězce `purpose` |
| `invalid_defaults` | `defaults` není mapování nebo neprojde `AgentDefaults` (jedna issue na každou pydantic chybu, path `agents/<n>/agent.yaml`, message s `loc`), včetně neznámého klíče, harness, thinking a `$` ve `writes` |
| `unknown_agent` | repo: `.factory/agents.yaml` chybí, není validní nebo nemá agenta `n` |
| `invalid_purpose` | repo: `purpose` v rosteru není řetězec (chybějící purpose = `""`, povoleno) |
| kódy z `parse_workflow` | workflow neprojde `parse_workflow(data, load_roles())` — každá `WorkflowError.issues` položka se převezme s původním `code`, path `"<cesta souboru>:<issue.path>"` |
| `missing_skill_md` | skill bez `SKILL.md` v kořeni položky |
| `invalid_front_matter` | `SKILL.md` neprojde `aifactory.backlog.frontmatter.parse_frontmatter` (message z `FrontmatterError`) |
| `name_mismatch` | front matter `name` ≠ jméno složky (i když `name` chybí) |
| `missing_description` | `description` chybí, není řetězec nebo je po `strip()` prázdný |
| `missing_entry` | rozšíření bez souboru `<n>.ts` v kořeni položky |

Čtení stromu (skill/extension): kořen je-li symlink → `symlink` a konec. `os.walk(dir, followlinks=False)`; adresáře-symlinky (v `dirnames`) → `symlink`; soubory přes `os.lstat`: symlink → `symlink`, ne-regulární → `not_a_file`, jinak počítej počet a velikost a `executable = bool(st.st_mode & stat.S_IXUSR)`. Limity vyhodnoť **před** čtením obsahu; při překročení obsah nečti (Item = None), ale ostatní issues stejně vrať. Prázdné adresáře se ignorují (git je nenese). Skryté soubory se berou.

Pro agenta a workflow platí limity taky (počítej z načtených souborů), prakticky se neuplatní.

Obsahová validace (`validate_item`) se pustí nad načtenou položkou z obou rozložení stejně: workflow (utf-8 → YAML → mapování → `parse_workflow` proti `load_roles()`), skill (SKILL.md pravidla), extension (`<n>.ts`). Agent: validace `agent.yaml` patří ke čtení knihovny (repo agent žádné `defaults` nemá).

## 5. `library/agent.py`

```python
def expand_writes(writes: Sequence[str] | None, settings: ProjectSettings) -> list[str] | None
```
`None` → `None`. Položka začínající `$specs_dir/` → `f"{settings.specs_dir.rstrip('/')}/" + zbytek`, totéž `$docs_dir/` s `settings.docs_dir`. Ostatní beze změny. Jiná `$` proměnná → `ValueError` (validace v `AgentDefaults` to už nepustí).

```python
def roster_entry(item: Item, settings: ProjectSettings) -> dict[str, Any]
```
Pro agenta z knihovny (`item.type == "agent"` a `defaults is not None`, jinak `ValueError`): `{"name": item.name, "purpose": item.purpose}` + `harness`, `model`, `thinking`, `tools` (list), `writes` (přes `expand_writes`, list), `color` — každý jen když není `None`. `skills`/`extensions` se do rosteru **nezapisují** (L5). Výsledek je mapování pro `.factory/agents.yaml` `agents:`.

## 6. Semínko — data

`aifactory/src/aifactory/seed/agents/<n>/`:

- **planner, builder, reviewer, documenter**: `system.md` a `user.md` zkopíruj **bajtově** (`cp`) z `.factory/prompts/<n>/`. `agent.yaml`:
  ```yaml
  purpose: Turn the task into a short plan the builder can follow.
  defaults:
    harness: claude
    model: claude-opus-5-5
    thinking: medium
    writes:
      - $specs_dir/
  ```
  - builder: `purpose: Implement the plan exactly; report every changed file.`, bez `writes` (= neomezeno, jako v `.factory/agents.yaml`).
  - reviewer: `purpose: Confirm that what was built is what was asked for; change nothing.`, `writes: []`.
  - documenter: `purpose: Write up the change from the diff; document only.`, `writes: [$docs_dir/]`.
  Purpose texty musí být znak po znaku stejné jako v `.factory/agents.yaml` (test to ověřuje).
- **scout**: `agent.yaml`:
  ```yaml
  purpose: Find and report where things live; change nothing.
  defaults:
    harness: claude
    model: claude-opus-5-5
    thinking: medium
    writes: []
  ```
  Prompty: vezmi `vendor/sssf/templates/prompt_engineering/scout/{system,user}.md` a uprav je stejným způsobem, jakým se HAIFA planner liší od sssf planneru (`diff vendor/sssf/templates/prompt_engineering/planner/system.md .factory/prompts/planner/system.md`):
  - `system.md`, sekce Instructions: hned za odrážku `- Write your findings to \`<context_handoff_dir>/scout_findings.md\` for agents that follow.` vlož odrážku přesně
    `` - `<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo or the worktree.``
    a na konec seznamu Instructions (za „If you find nothing…“) odrážku
    `` - Git is the workflow's job, not yours. Run no git command that changes anything: never `git commit`, `git add`, `git stash`, `git reset`, `git rebase`, `git merge` or `git push`, and never create, switch or delete branches (`git switch`, `git checkout`, `git branch`). Leave the working tree exactly as you found it.``
  - `user.md`: za řádek `{{context_handoff_dir}}` (a prázdný řádek) vlož stejně jako u planneru odstavec
    `` `<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at exactly that path; never create a directory of the same name inside the repo or the worktree.`` následovaný prázdným řádkem.
  - Jinak text beze změny (sekce Subagents zůstává, jako u HAIFA planneru). Žádné jméno souboru podle `adw_id`, slovo `adw_id` se v promptech scouta nesmí objevit.
- Workflow semínka jsou `aifactory/src/aifactory/defaults/workflows/*.yaml` (všech 7 včetně `resolve`); do `seed/` se **nekopírují**.

## 7. `library/seed.py`

```python
SEED_DIR = Path(str(resources.files("aifactory") / "seed"))
SEED_WORKFLOWS_ROOT = DEFAULT_WORKFLOWS_DIR.parent        # rozložení knihovny: <root>/workflows/<n>.yaml
SEED_AGENTS: tuple[str, ...] = ("planner", "builder", "reviewer", "documenter", "scout")

def seed_agent_names() -> list[str]      # seřazené jména složek v SEED_DIR/agents
def seed_workflow_names() -> list[str]   # seřazené stemy *.yaml v DEFAULT_WORKFLOWS_DIR
def seed_items() -> list[Item]           # agenti přes load_library_item(SEED_DIR, "agent", n), workflow přes load_library_item(SEED_WORKFLOWS_ROOT, "workflow", n); seřazeno (type dle ITEM_TYPES, name)
```
`DEFAULT_WORKFLOWS_DIR` importuj z `aifactory.workflow.parse` (ne z `aifactory.workflow`, ať se zbytečně netahá interpreter).

## 8. `library/__init__.py`

Re-exportuj: `ITEM_TYPES`, `ItemType`, `NAME_RE`, `MAX_ITEM_BYTES`, `MAX_ITEM_FILES`, `Item`, `ItemFile`, `AgentDefaults`, `LibraryError`, `agent_version`, `workflow_version`, `tree_version`, `item_version`, `load_library_item`, `load_repo_item`, `check_library_item`, `check_repo_item`, `validate_item`, `expand_writes`, `roster_entry`, `SEED_DIR`, `SEED_AGENTS`, `seed_items`, `seed_agent_names`, `seed_workflow_names`. Krátký docstring s odkazem na AR14–AR16.

## 9. Testy — `aifactory/tests/library/`

Bez `__init__.py` (jako ostatní složky testů); jména souborů unikátní (`test_library_*.py`). Žádný model ani síť. Kořen HAIFA: `HAIFA_ROOT = Path(__file__).resolve().parents[3]`. Pomocník pro zápis stromů do `tmp_path` si napiš v testu (nebo `tests/library/library_tree.py`).

**`test_library_version.py`**
- Zlaté verze pro každý typ: pevný obsah (např. agent purpose `"Plan it."`, system `b"sys\n"`, user `b"usr {{prompt}}\n"`; workflow `b"name: plan\nsteps: [plan]\n"`; skill `SKILL.md` + `bin/run.sh` spustitelný; extension `x.ts` + `lib/util.ts`). Každý test assertuje **(a)** rovnost literálu `"sha256:<hex>"` (hex vygeneruj jednou implementací a vlož jako konstantu) **a (b)** rovnost s nezávisle sestaveným `hashlib.sha256(...)` podle formátu z kapitoly 3 přímo v testu.
- Stejná verze z knihovny i z repa pro všechny 4 typy (dvě rozložení v `tmp_path` se stejným obsahem; repo agent s `.factory/agents.yaml` rosterem a jiným slotem, než je jméno v knihovně → stejná verze; workflow pod jiným jménem → stejná verze).
- Změna jednoho bajtu (v purpose, system, user, workflow, souboru skillu) změní verzi; změna spustitelnosti (`chmod`) u skillu/rozšíření verzi změní; u agentových promptů ne.
- Přejmenování souboru ve skillu změní verzi.
- `defaults` (jiný model, writes, harness) verzi agenta nemění.

**`test_library_validate.py`** — každá chyba z tabulky kap. 4 aspoň jednou (`invalid_name` včetně 49 znaků a velkých písmen, `missing_item`, `missing_file`, `symlink` u souboru i adresáře, `too_many_files` (201 malých souborů), `too_large` (soubor 2 MB + 1 B), `invalid_yaml`, `not_a_mapping`, `unknown_key`, `missing_purpose`, `invalid_defaults` (neznámý harness, špatné thinking, `$foo/` ve writes, neznámý klíč v defaults), `unknown_agent`, workflow s neznámou rolí → kód z `parse_workflow` (`unknown_step` nebo co parser vrací — ověř), `missing_skill_md`, `invalid_front_matter`, `name_mismatch`, `missing_description`, `missing_entry`). Plus jeden test, že položka s několika problémy najednou (např. skill bez description, se symlinkem a se jménem neodpovídajícím složce) dostane **všechny** v jednom `LibraryError.issues`. Validní skill/rozšíření/workflow/agent projdou bez issue.

**`test_library_agent.py`** — `expand_writes` (`$specs_dir/` → `specs/`, `$docs_dir/sub/` s `docs_dir="docs"` → `docs/sub/`, `None`, `[]`, obyčejná cesta beze změny), `roster_entry` vynechá `None` klíče a skills/extensions.

**`test_library_seed.py`**
- `seed_agent_names() == sorted(SEED_AGENTS)`; `seed_workflow_names()` = stemy `DEFAULT_WORKFLOWS_DIR`; všechny `seed_items()` se načtou bez chyby.
- Pro planner, builder, reviewer, documenter: `seed/agents/<n>/{system,user}.md` bajtově rovné `HAIFA_ROOT/.factory/prompts/<n>/...`.
- Purpose a vazby semínka odpovídají `HAIFA_ROOT/.factory/agents.yaml`: načti `load_config(WorktreeSource(HAIFA_ROOT))` (jen čtení) a pro každého z 4 agentů porovnej `roster_entry(seed, config.settings)` s `config.agents` (purpose, `coding_agent` == `claude`, model `claude-opus-5-5`, thinking `medium`, writes: planner `["specs/"]`, documenter `["app_docs/"]`, reviewer `[]`, builder `None`).
- Verze semínka = verze `load_repo_item(HAIFA_ROOT, "agent", n)` pro 4 agenty HAIFA.
- Scout: `defaults.writes == ()`, prompty obsahují větu o `<context_handoff_dir>` mimo repo a git odrážku, neobsahují `adw_id`; system i user se liší od vendor originálu jen vloženými řádky (porovnej odstraněním vložených řádků).
- Dočasné repo z rosteru semínka: v `tmp_path` (git init přes `config_repo.git`/`commit_all` z `tests/config/config_repo.py`, pokud to `WorktreeSource`/`repo_root` potřebuje) zapiš `.factory/config.yaml` (`base: main\n`), `.factory/agents.yaml` = `yaml.safe_dump({"agents": [roster_entry(...) for všech 5]})` a prompty všech 5 agentů do `.factory/prompts/<n>/`. `load_config(WorktreeSource(repo))` projde, roster má přesně 5 jmen. Pak pro **každé** `DEFAULT_WORKFLOWS_DIR/*.yaml` (parametrizovat, včetně `scout` a `resolve`): `wf = load_workflow(path, config.roles)`, `cfg = write_prompts(config, tmp_path / "prompts")`, `preflight(wf, cfg)` nevyhodí. (`preflight` z `aifactory.workflow`; claude `resolve_model` je offline.) Zároveň `load_repo_item(repo, "agent", n).version == seed item version` pro všech 5.

## 10. Ověření

Z kořene worktree:
```
just test        # celé, včetně tests/library
just typecheck   # mypy strict nad src i tests
just lint        # ruff check + ruff format --check
```
Rychlá iterace: `cd aifactory && uv run pytest tests/library -n0`. Ověř `git status`, že se `.factory/`, `vendor/`, `prototype/` nezměnily.

## Pasti

- `yaml.safe_dump` napíše `$specs_dir/` bez uvozovek — v `agent.yaml` je to platný plain scalar; ruční zápis jak výše je OK.
- `AgentDefaults.tools`/`writes` jako `tuple` — při `roster_entry` převeď na `list`.
- Pydantic validátor pro `harness` vrací kanonické jméno; `claude` zůstane `claude`.
- Při čtení promptů a workflow používej `read_bytes()` — verze se počítá z bajtů, ne z dekódovaného textu (CRLF, BOM).
- mypy strict: typuj vše, `Literal` pro `ItemType`, žádné `Any` bez potřeby.
