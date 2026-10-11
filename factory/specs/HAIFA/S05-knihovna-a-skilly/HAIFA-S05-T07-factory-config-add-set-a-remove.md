# HAIFA-S05-T07: `factory config add`, `set` a `remove`

## Cíl

Tři nové podpříkazy skupiny `factory config` spravují položky v `.factory/` (a ve skillech repa) podle knihovny:

- `factory config add TYP JMÉNO`: zkopíruje položku z knihovny (bez knihovny ze semínka) i se závislostmi a zapíše ji do manifestu.
- `factory config set agent SLOT`: změní jen vazby slotu v `agents.yaml`.
- `factory config remove TYP JMÉNO [--prune]`: odebere položku, s `--prune` i závislosti, které nikdo jiný nepoužívá.

Všechny tři počítají **plán s digestem** a mají stejné režimy:

- `--dry-run`: jen plán, nic nezapíše.
- bez volby: zápis do pracovního stromu.
- `--commit`: jeden commit do base cestou z M7 (`providers.publish`).

Mimo rozsah: export do knihovny a návrat verze (L8), aktualizace (M9), operace ve více repech (L9), dashboard.

## Povolené cesty

`aifactory/`, `justfile`, tento spec, `app_docs/HAIFA-S05-T07-factory-config-add-set-a-remove.md` (tu píše dokumentační fáze, builder ji nechá být). `.factory/`, `.claude/`, `docs/`, `vendor/`, `prototype/` a `CLAUDE.md` repa HAIFA se nemění. Testy nevolají model ani síť. Bez `--commit` se nic necommituje.

## Co už existuje (použij, nepiš znovu)

- `library/install.py`:
  - `_Source` načte položky z HEAD knihovny nebo ze semínka.
  - `_workflow_agents(item)` vrátí agenty kroků. Dnes čte jen balíčkový registr `load_roles()`.
  - `_agent_entry(item, settings, Binding)` udělá záznam rosteru z `defaults` a z vazby.
  - Dál `parse_binding`, `_committed`, `_git_out`, `_repo_root`, `_now`.
- `library/install_commit.py`:
  - `_validate(...)`: `load_config` přes `OverlaySource(CommitSource)` a `preflight` každého workflow, s výjimkou `invalid_agent` u chybějícího harness CLI.
  - `_store(root)` (trace DB jen když existuje), `_dirty(root, files)`, `_harness_warnings`.
  - `commit_init`: vzor pro `plan_changed`, blockery a `publish_direct(materialize=True)` / `publish_pr`.
- `providers/publish.py`: `PlannedFile` (akce `create|modify|delete`), `PublishPlan`, `plan_digest`, `plan_contents`, `direct_blockers`, `run_blocker`, `publish_direct`, `publish_pr`.
- `config/source.py`: `WorktreeSource`, `CommitSource`, `OverlaySource`.
- `config/manifest.py`: `Manifest`, `ManifestEntry`, `ManifestItems.of(type)`, `read_manifest`, `parse_manifest`, `dump_manifest`, `MANIFEST_FILE`, `ITEM_KEYS`.
- `library/load.py`:
  - `repo_path(type, name)`, `library_path`, `check_repo_item`, `check_library_item`.
  - `validate_item`: skill má `SKILL.md`, jehož `name` musí být rovno složce.
- `library/state.py`: `repo_item_names`, `repo_version`, `extract_factory`.
- `library/tree.py`: `tree_files`, `read_blobs`, `write_files`, `read_items`.
- `library/agent.py`: `expand_writes` nahradí `$specs_dir/` a `$docs_dir/`.
- `library/model.py`: `AgentDefaults` (harness, model, thinking, tools, writes, color, skills, extensions), `check_name`.
- `harness/override.py`: `THINKING_LEVELS`. `harness.canonical(name)` vyhodí `ValueError` u neznámého harnessu.
- `harness/repo_skills.py`: `SOURCE = ".claude/skills"`, `MIRROR = ".agents/skills"`.
- `backlog/loader.py` `load_backlog(root, settings)`, `backlog/derived.py` `effective_workflow(task)`, `backlog.loader.iter_tasks`.
- `config/commit.py` `CONFIG_BRANCH_PREFIX = "factory-config/"`.
- CLI: `_add_config_commands`, `_config` a `_library_fail` (obálka chyby z `LibraryStoreError`) v `cli.py`.

## Návrh

### 1. Závislost ruamel.yaml

- `cd aifactory && uv add "ruamel.yaml>=0.18.10,<0.19"`. Pokud je nejnovější vydání vyšší, vezmi `>=X.Y.Z,<X.(Y+1)`, tedy vždy s horní mezí. Commituje se i aktualizovaný `aifactory/uv.lock`.
- `tests/test_bundle.py::test_constraints_pin_runtime_dependencies_from_lock`: přidej `"ruamel.yaml"` do seznamu běhových závislostí, které se kontrolují.
- Když mypy strict ruamel neuzná jako typovaný, přidej do `pyproject.toml` `[[tool.mypy.overrides]] module = ["ruamel.*"]` s `ignore_missing_imports = true`. Jinak override nepřidávej.

### 2. `config/yamledit.py` (nový): round trip pro `agents.yaml`, `config.yaml` a `roles.yaml`

```python
def load_rt(text: str) -> tuple[YAML, Any]        # YAML(typ="rt"), preserve_quotes=True, width=4096
def dump_rt(yaml: YAML, data: Any) -> str
def edit_yaml(text: str, change: Callable[[Any], None]) -> str
```

- `edit_yaml` načte dokument, zavolá `change` na `CommentedMap` a vrátí text.
- Ověří, že `yaml.safe_load(výsledek) == očekávaná data`. Očekávaná data vzniknou stejnou změnou na `copy.deepcopy(yaml.safe_load(text))` přes čisté dict/list. Pro jednoduchost stačí kontrola, že výsledek jde načíst, a test pokryje obsah. Neplatný výsledek vyhodí `ValueError`.
- Odsazení se zjistí z textu: první řádek sekvence `- ` pod klíčem nejvyšší úrovně. Bez odsazení (styl PyYAML) je to `indent(mapping=2, sequence=2, offset=0)`, s `  - ` je to `sequence=4, offset=2`.
- Prázdný text nebo dokument `None` se stane prázdnou `CommentedMap`.
- Pomocné funkce pro `agents.yaml`:
  - `roster_add(doc, entry: dict)` připojí `CommentedMap` na konec `agents`.
  - `roster_set(doc, slot, changes: dict[str, Any | None])`: hodnota `None` klíč odstraní. Při změně harnessu se `coding_agent` nahradí klíčem `harness` na stejné pozici (`doc.insert(pos, "harness", value)`) a `coding_agent` se odstraní.
  - `roster_remove(doc, slot)`.
- Nový záznam rosteru má pořadí klíčů jako `install._agent_entry`: name, purpose, harness, model, thinking a pak zbytek.
- `config.yaml` a `roles.yaml` tento task jen čte. Jakákoli úprava v kódu ale musí jít přes `edit_yaml`, nikdy přes `yaml.safe_dump`. Napiš to do docstringu modulu.

### 3. `config/loader.py`, `config/source.py`, `config/status.py`

- **loader.py**: `SKILLS_DIR = ".claude/skills"` podle rozhodnutí Skilly v repu (zdroj skillu je `.claude/skills/<jméno>/`). Přidej `SKILLS_MIRROR_DIR = ".agents/skills"`, ať se shoduje s `repo_skills.SOURCE` a `MIRROR`. Oprav test, který čeká `.factory/skills/lint` (`tests/library/test_library_version.py:102`), a docstring `library/load.py` (popis kopie v repu).
- **source.py**: `OverlaySource.__init__(self, base: ConfigSource | None, overlay: Mapping[str, bytes | None])`.
  - Hodnota `None` znamená smazaný soubor: `read_text` vrátí `None` a `list_files` cestu vynechá.
  - `name` u jiného zdroje než commitu použije `base.name`.
  - Stávající volání (`install_commit._validate`) se nemění.
- **status.py**: `config commit` musí umět commitnout skilly, které `config add` zapsal do pracovního stromu.
  - Přidej `SHARED_DIRS += (".claude/skills/", ".agents/skills/")`.
  - `config_changes` předá `git diff-index` pathspecy `[FACTORY_DIR, ".claude/skills", ".agents/skills"]`.
  - Aktualizuj docstring a nápovědu `config commit` v CLI (výčet cest).
  - Ověř, že stávající testy `config status` a `config commit` projdou. Kde test vyjmenovává sdílené cesty, doplň je.

### 4. `providers/publish.py`: smazání při `materialize`

V `_stage_matching` s `materialize=True` platí: je-li `f.content is None`, disk je soubor a `disk.read_bytes() == f.old_content`, soubor se smaže (`unlink`). Prázdné nadřazené adresáře se uklidí až po kořen checkoutu, který se nemaže. Pak jde cesta do `remove`. Bez `materialize` se chování nemění. Test je v sadě níže (`--commit` u remove).

### 5. `library/install.py`: drobné úpravy pro sdílení

- `_workflow_agents(item, roles: RoleRegistry | None = None)` použije `roles or load_roles()`. Kroky s `agent:` už nese `step.role.agent`.
- `_Source.load` pro `skill` a `extension` ze semínka: semínko je nemá, takže vyhodí `unknown_item` s textem `no skill 'x' in the seed`. Dnes by se omylem hledalo mezi workflow.
- `_agent_entry` zůstane, `config add` ho volá.

### 6. `install_commit._validate` se zobecní

Vytáhni jádro do `validate_source(source: ConfigSource, workflows: Mapping[str, bytes], missing: frozenset[str]) -> list[Issue]`. Funkce udělá `load_config(source)`, `write_prompts` a pro každé workflow `parse_workflow` s `cfg.roles` a `preflight`. `_validate` pro init se zúží na zavolání `validate_source(OverlaySource(CommitSource(...), overlay), {name: contents[...]}, missing)`. Chování initu se nemění.

### 7. `library/config_edit.py` (nový): plán a zápis

Docstring modulu popíše režimy, blockery a kódy, stejně jako `install_commit`.

#### Stav repa

```python
@dataclass
class RepoState:
    root: Path
    mode: Literal["worktree", "base"]
    base: str; base_sha: str
    files: dict[str, bytes]      # .factory/** bez local.yaml, data/, worktrees/, trace.db*;
                                 # .claude/skills/**, .agents/skills/**
    executable: set[str]         # cesty s exec bitem (skilly)
```

- Režim `worktree` čte disk.
- Režimy `--commit` a `--commit --dry-run` čtou strom base přes `tree_files`/`read_blobs`, mód `100755` znamená exec bit.
- Base se bere z `worktree_base(root)` a sha z `git.rev_parse(root, f"refs/heads/{base}")`. Když chybí, je to `unknown_base`.
- `state.manifest()` je `parse_manifest(files[MANIFEST_FILE])`. Když soubor chybí, vyhoď `LibraryStoreError("not_onboarded", "...run factory onboard", data={"fix": "factory onboard"})`. Pokud v base chybí, ale je na disku, zpráva navíc doporučí `factory config commit` (kód zůstává `not_onboarded`).
- `state.settings()` je `parse_project_settings` z `config.yaml` stavu a slouží k náhradě `$specs_dir/` a `$docs_dir/`.
- `state.config()` je `load_config(OverlaySource(source, {}))` a dává `cfg.roles` (registr repa) a roster.
- Pro `check_repo_item` a `repo_version` se stav dočasně rozbalí do tempdir (`with state.materialized() as tmp`). Neřeš to ručním čtením.

#### Operace

Každá operace je čistá funkce `RepoState -> Change`:

```python
@dataclass
class Change:
    files: dict[str, bytes | None]   # nový obsah, None = smazat; jen změněné cesty
    added: list[dict]                # {type, name, item, version, reason: "requested"|"dependency"}
    kept: list[dict]                 # {type, name, reason}  (existující závislost, no-op)
    removed: list[dict]              # {type, name, reason: "requested"|"pruned"}
    bindings: dict[str, dict]        # slot -> {harness, model, thinking, tools, writes, color}
    warnings: list[str]
```

**add**

1. Typ musí být v `ITEM_TYPES` a jméno platné (`invalid_value`).
2. `--as` je jen pro `agent` a `workflow`. U skillu a rozšíření dá `conflicting_options`, protože jméno skillu musí být rovno složce. `--harness`, `--model` a `--thinking` jsou jen pro `agent`, jinak také `conflicting_options`.
3. `thinking` mimo `THINKING_LEVELS` dá `invalid_value` a neznámý harness také `invalid_value`. Použij `parse_binding`-style validaci, klidně přes `Binding`.
4. Položku načti přes `_Source(environ).load(type, [name])`.
5. **Uzávěr** zpracovává frontu `(type, item_name, slot, reason)`:
   - `workflow`: jeho agenti podle `_workflow_agents(item, state.config().roles)`.
   - `agent`: jeho `defaults.skills` a `defaults.extensions`.
   - Závislost se jménem, které už v repu je (v rosteru nebo v manifestu daného typu), se nekopíruje a jde do `kept` s důvodem `present`, a to bez ohledu na obsah.
6. **Požadovaná položka** (slot = `--as` nebo jméno):
   - Slot neexistuje: vytvoř.
   - Slot existuje a `repo_version(slot)` se rovná `item.version` (u agenta i stejné `item` v manifestu nebo bez manifestu): no-op, `kept` s důvodem `same_content`, žádné soubory, `changed: false`.
   - Slot existuje s jiným obsahem: `LibraryStoreError("slot_taken", "... slot X is taken by other content; pick another with --as NEW", data={"fix": "--as <slot>", "slot": X})`.
7. **Soubory podle typu**:
   - agent:
     - `.factory/prompts/<slot>/system.md` a `user.md` (chybějící prompt je `b""` jako v `render_files`).
     - Záznam v `agents.yaml` přes `yamledit.roster_add`. Obsah je `_agent_entry(item, settings, Binding(slot, harness, model, thinking))` s `name` = slot. Když není dán `--harness`, ale je `--model` nebo `--thinking`, ponech harness z defaults: `Binding.harness = defaults.harness`.
   - workflow: `.factory/workflows/<slot>.yaml` = `item.files[0].data`.
   - skill: každý soubor itemu do `.claude/skills/<name>/<path>` a stejné bajty do `.agents/skills/<name>/<path>`, exec bit podle `ItemFile.executable`.
   - extension: `.factory/extensions/<name>/<path>`.
   - Manifest: `items.<typ>[slot] = ManifestEntry(item=item.name, version=item.version)`, zapsaný přes `dump_manifest(manifest.model_copy(update=...))`. `onboarding` ani `library` se nemění. Když `manifest.library` existuje a jeho `id` se liší od aktuální knihovny, přidej varování `library_mismatch`.

**set agent SLOT**

- Slot musí být v rosteru stavu, jinak `unknown_item`. Musí být zadaná aspoň jedna volba, jinak `invalid_value`.
- Volby:
  - `--harness H`: `canonical`, při chybě `invalid_value`.
  - `--model M`.
  - `--thinking T`: mimo `THINKING_LEVELS` dá `invalid_value` se seznamem úrovní.
  - `--tools LIST` a `--writes LIST`: seznamy oddělené čárkou. Prázdný řetězec dá `[]`, `-` klíč odstraní. `writes` projde `expand_writes` s nastavením repa a neznámá proměnná dá `invalid_value`.
  - `--color #rrggbb`: regex `^#[0-9a-fA-F]{6}$`, jinak `invalid_value`.
- Mění se jen `agents.yaml` přes `yamledit.roster_set`. Manifest ani prompty se nemění. Vazby nejsou součástí verze (AR20), takže stav položky v `config items` zůstane.

**remove TYP JMÉNO [--prune]**

- Položka musí v repu existovat: v rosteru, v adresáři položky nebo v manifestu. Jinak `unknown_item`.
- `in_use(state_after, type, name) -> list[str]` (důvody) počítá **nad stavem po odebrání**:
  - agent:
    - Některé workflow ve stavu (`.factory/workflows/*.yaml`, parsované s `cfg.roles` stavu) má krok s tímto agentem. Důvod: `workflow <w> step <path>`.
    - `.factory/roles.yaml` ve stavu jmenuje tohoto agenta. Důvod: `roles.yaml role <r>`.
  - workflow: úkol backlogu **v base** (vždy base, i v režimu worktree) má `effective_workflow == name`.
    - Backlog base se čte tak, že se kořeny backlogu z nastavení base (`backlog_roots`) a `.factory/config.yaml` rozbalí přes `tree_files`/`write_files` do tempdir. Pak `load_backlog(tmp, settings)` a `iter_tasks`.
    - Důvod: `backlog task <id>`.
  - skill a rozšíření (vazba jiného agenta):
    - Jiný agent v manifestu, jehož knihovní položka (`_Source.load("agent", [entry.item])`, s ignorovanou chybou `unknown_item`) má jméno v `defaults.skills` nebo `defaults.extensions`.
    - U rozšíření také agent rosteru, jehož `harness_engineering` obsahuje cestu pod `.factory/extensions/<name>/`.
    - Důvod: `agent <slot>`.
- Neprázdné důvody dají `LibraryStoreError("in_use", "... is used by: ...", data={"used_by": [...]})`.
- Soubory k odebrání:
  - agent: záznam rosteru (`roster_remove`), všechny soubory pod `.factory/prompts/<slot>/` a manifest.
  - workflow: soubor a manifest.
  - skill: oba stromy (`.claude/skills/<n>/`, `.agents/skills/<n>/`) a manifest.
  - extension: strom a manifest.
- `--prune`:
  - Závislosti odebrané položky jsou u workflow jeho agenti, u agenta jeho `defaults.skills` a `extensions` (z knihovní položky podle manifestu, jinak žádné).
  - Prořezávají se jen ty, které jsou **v manifestu**. Lokální položky se nikdy neprořezávají.
  - Závislost se odebere, když `in_use` nad průběžným stavem vrátí prázdno. Postupuje se rekurzivně a výsledek je v `removed` s důvodem `pruned`.
  - Použité závislosti jsou v `kept` s důvodem `in_use`.

#### Plán, validace a blockery

```python
@dataclass
class ConfigPlan:
    command: Literal["add", "set", "remove"]; type: str; name: str; slot: str | None
    target: Literal["worktree", "direct", "pr"]
    state: RepoState; change: Change
    publish: PublishPlan        # i pro worktree (base/base_sha + PlannedFile)
    issues: list[Issue]; warnings: list[str]
    def to_json(self) -> dict[str, Any]
```

- **PlannedFile** pro každou cestu v `change.files`:
  - `old_content` a `old_blob` pochází ze stavu. V režimu worktree je `old_blob` hash obsahu na disku: `git.hash_blob(root, data, write=False)`, při absenci `None`.
  - `mode` je `100755` pro spustitelný soubor skillu, jinak `100644`. Při mazání je `None`.
  - `action` je `create`, `modify` nebo `delete`.
  - Cesty, které se nemění, se vynechají.
- **digest** = `plan_digest(base, base_sha, files)`. Manifest neobsahuje čas, takže je stabilní. Digest režimu worktree se tak změní s každou změnou disku i base.
- **validace** se dělá jen, když se mění `.factory/`:
  - `validate_source(OverlaySource(source_of(state), {p: c for p, c in change.files.items() if p.startswith(".factory/")}), workflows=všechna workflow nového stavu, missing=harnessy bez CLI)`.
  - `source_of` je `WorktreeSource(root)` pro worktree, jinak `CommitSource(root, base, base_sha)`. Chybějící harnessy zjistíš přes `library.detect.detect(root).harnesses`, nebo levněji přes `harness.check`, a použij stejnou logiku jako init.
  - Skilly se validují `validate_item` už při načtení z knihovny.
  - Problémy dají blocker `invalid_plan`.
- **blockery**:
  - worktree: `run_blocker(store)` přes `install_commit._store(root)`, tedy `run_in_progress`. Dál `invalid_plan`.
  - direct (`--commit`): `_dirty(root, files)` dá `dirty_paths`, dál `invalid_plan` a `direct_blockers(...)`, který přidá `not_on_base`, `run_in_progress`, `base_behind` a `base_diverged`.
  - pr (`--commit --pr`): `dirty_paths` a `invalid_plan`.
  - Varování z `direct_blockers` a `_harness_warnings` jdou do `warnings`.

#### Provedení

`run_config(command, root, *, dry_run, commit, pr, expect, message, environ, **op) -> ConfigResult`:

1. Sestav plán. S `dry_run` ho vrať (`dry_run: true`).
2. `expect` se liší od digestu: `plan_changed` s `data=plan.to_json()`, jako init.
3. Blockery: vyhoď první (u `invalid_plan` i s issues).
4. Prázdná změna (no-op): `changed: false`, nic se nezapisuje ani necommituje, exit 0.
5. Zápis podle cíle:
   - **worktree**: zapiš soubory atomicky (tmp a `os.replace`, `chmod` u exec bitu) a smaž cesty s `None`. Prázdné adresáře se uklidí až po `.factory/`, `.claude/skills/` a `.agents/skills/`. Žádný `git add` ani commit. Výsledek obsahuje `written: true` a doporučení `factory config commit`.
   - **direct**: `publish.publish_direct(root, settings=..., plan=plan.publish, message=subject, store=store, materialize=True, command="config add|set|remove")`.
   - **pr**: `publish.publish_pr(..., prefix=CONFIG_BRANCH_PREFIX)` s tělem jako `install_commit._body`.
   - `ProviderError` a `RuntimeError` se mapují na `LibraryStoreError` jako v `commit_init`.
6. Výchozí zpráva commitu:
   - `factory: add <type> <slot> from <the library NAME|the seed>`
   - `factory: set agent <slot> (<keys>)`
   - `factory: remove <type> <name>`

JSON výsledku (`data`):

```
{repo, command, type, name, slot, target, base, base_sha, digest, files[], paths[], blockers[],
 added[], kept[], removed[], bindings{}, changed, validation{ok, issues[]}, warnings[],
 source, library, dry_run, written, committed, commit, pushed, advanced, branch, pr}
```

### 8. CLI (`cli.py`)

V `_add_config_commands` přidej `add`, `set` a `remove`, každý s podrobným `description`, protože `factory --skill` ho převezme. Popis vyjmenuje režimy, uzávěr, `slot_taken`, `in_use`, `not_onboarded`, blockery a kódy.

- `add`:
  - Poziční `type` (`choices=ITEM_TYPES`) a `name`.
  - Volby `--as SLOT` (`dest="slot"`), `--harness`, `--model`, `--thinking`.
- `set`:
  - Poziční `type` (`choices=("agent",)`) a `slot`.
  - Volby `--harness`, `--model`, `--thinking`, `--tools LIST`, `--writes LIST`, `--color HEX`.
- `remove`: poziční `type` a `name`, volba `--prune`.
- Společné volby: `--dry-run`, `--commit`, `--pr`, `--expect DIGEST`, `-m/--message`, `--repo`, `--json`.
- Konflikty (`conflicting_options`):
  - `--pr` bez `--commit`.
  - `-m` bez `--commit`.
  - `--expect` s `--dry-run`.
  - Pravidla typů z kapitoly 7.
  - `--expect` je povolené i bez `--commit` (režim worktree).
- `_config` posílá `add`, `set` a `remove` do `_config_edit(args)`. Chyby jdou přes `_library_fail` (exit 2).
- Text bez `--json`, styl jako `_init_plan`:
  - řádky `action path`;
  - `added`, `kept` a `removed`;
  - `blocked: code: message`;
  - `digest`;
  - u dry-run `next: factory config <cmd> ... --expect <digest>` (s `--commit`, pokud byl dry-run s `--commit`);
  - po zápisu do worktree `next: factory config commit`.

### 9. Skill (`skill/skill.md`, `skill/codes.py`)

- `codes.py`:
  - Nové kódy (exit 2):
    - `slot_taken`: config add, slot je obsazený jiným obsahem; `data.fix` je `--as NEW`.
    - `in_use`: config remove, položku používá workflow, role, agent nebo úkol backlogu v base; viz `data.used_by`.
  - Uprav popis `not_onboarded` (i `factory config add|set|remove`, oprava `factory onboard`).
  - Uprav popisy `plan_changed`, `invalid_plan`, `dirty_paths` a `run_in_progress` tak, aby nebyly jen pro init a commit.
  - Ověř `unknown_item` a `conflicting_options`.
  - `tests/test_skill.py` skenuje literály kódů ve zdrojích. Každý nový literál musí být v `codes.py`.
- `skill.md`: krátká sekce „Items of the repo: config add / set / remove“ u `config items`. Obsahuje příklady s `--json`, režimy (`--dry-run`, worktree s `--expect`, `--commit [--pr] --expect`), uzávěr, umístění skillů (`.claude/skills/` a kopie v `.agents/skills/`), `slot_taken` s `--as`, `in_use` s `--prune` a postup dry-run, kontrola, `--expect`.

### 10. Testy: `aifactory/tests/library/test_library_config_edit.py`

Fixture převezmi z `test_library_install_commit.py`: autouse `home` (`HAIFA_HOME` v `tmp_path`, git identita, falešné `claude` na PATH, codex a pi chybí), `make_repo` s holým remote `origin.git`, `run_json`, `snapshot`, `_claim` z `tests/config/test_config_publish.py`. Kód zkopíruj, nebo `_claim` importuj tak, jak to dělají ostatní testy přes `sys.path`.

- **Onboardované repo**: `factory init --commit --json` do repa s remote. Bez knihovny vznikne ze semínka simple-sdlc se čtyřmi agenty.
- **Dočasná knihovna**: `store.init_library("team")`. Do knihovny pak přidej položky přímo gitem v `store.library_root()` (zapiš soubory a commitni): skill `skills/lint/SKILL.md` (frontmatter `name: lint`, `description`), workflow `workflows/solo.yaml` s krokem `agent: scout` a vlastní agent, pokud je potřeba. Postup podle `library_tree.py` (`skill_files`, `library_agent`). Workflow z knihovny musí projít `preflight` s rosterem, kde je `claude` (model `claude-*` z `defaults` agentů v semínku).

Testy (každý ověří i to, že bez `--commit` je `git rev-parse main` beze změny):

1. `test_add_workflow_with_closure`: `config add workflow solo --json` přidá do pracovního stromu workflow a chybějícího agenta (`added` obsahuje agenta s důvodem `dependency`). Existující agenti jsou v `kept`. Manifest má obě položky s verzí. `load_config(WorktreeSource)` projde.
2. `test_add_agent_as_other_slot`: `config add agent builder --as builder2 --model ... --thinking high`. Roster má `builder2` s vazbami podle voleb, `writes` má rozbalené `$specs_dir/`, prompty jsou v `.factory/prompts/builder2/` a manifest `agents.builder2.item == "builder"`.
3. `test_slot_taken_and_same_content_noop`:
   - Stejný obsah: `config add agent builder` dá `changed: false` a soubory se nemění.
   - Jiný obsah: úprava `.factory/prompts/builder/system.md` a znovu `add` dá `slot_taken` s exit 2 a `data.fix` obsahující `--as`.
4. `test_add_skill_to_both_trees`: `config add skill lint` vytvoří `.claude/skills/lint/SKILL.md` a stejné bajty v `.agents/skills/lint/`. Manifest `skills.lint` existuje. Následný `factory skills sync --json` nic nezmění (`added`, `updated` i `removed` jsou prázdné).
5. `test_set_keeps_comments_and_order`:
   - Do `agents.yaml` přidej komentář na začátek, komentář u agenta a vlastní pořadí klíčů, commitni.
   - `config set agent builder --thinking high --tools read,bash --color '#112233' --json`.
   - Komentáře i pořadí zůstanou (porovnání textu řádek po řádku mimo změněné hodnoty). Změní se jen tyto klíče, ostatní agenti mají identický text.
   - Manifest beze změny.
6. `test_set_invalid_thinking`: `--thinking ultra` dá `invalid_value` (exit 2), soubor beze změny. K tomu `set agent nobody --model x` dá `unknown_item`.
7. `test_remove_in_use_and_prune`:
   - `remove agent builder` dá `in_use` (simple-sdlc ho používá) s `data.used_by`.
   - Workflow, na které ukazuje úkol backlogu v base (`backlog/` s `index.md` a úkolem `workflow: solo`, commit a push), dá `in_use`.
   - Bez úkolu: `remove workflow solo --prune` odebere workflow i agenta, kterého jiný nepoužívá (`removed` s důvodem `pruned`), a agenty používané simple-sdlc ponechá v `kept`.
   - Lokální agent (bez manifestu) se neprořeže.
   - Prompty i záznam rosteru zmizí.
8. `test_commit_and_plan_changed`:
   - `config add workflow solo --commit --dry-run` vrátí digest, nic nezapíše (`snapshot` beze změny).
   - Unrelated commit a push do main. `--commit --expect <starý>` dá `plan_changed` a snapshot je beze změny.
   - Nový dry-run a `--commit --expect <nový> -m "add solo"`: jeden commit na main, pushnutý (`git rev-parse origin/main` v holém repu = main), zpráva `add solo`. Soubory jsou v checkoutu (materialize) a pracovní strom je čistý (`git status --porcelain` prázdné).
   - `remove workflow solo --commit`: commit, soubor smazán i z checkoutu (test kapitoly 4).
9. `test_worktree_expect_and_run_in_progress`:
   - `--dry-run` a pak zápis s `--expect <digest>` projde. Se špatným digestem dá `plan_changed` a nic nezapíše.
   - `_claim(repo, os.getpid())`: zápis do worktree dá `run_in_progress` a nic nezapíše. `--commit` dá také `run_in_progress`.
10. `test_not_onboarded`: holé repo bez manifestu: `config add agent builder` dá `not_onboarded` s `data.fix == "factory onboard"`.
11. `test_yamledit_roundtrip` (jednotkový, `yamledit`): nezměněný dokument vyjde po round tripu bajtově stejný, a to pro styl PyYAML i pro odsazené sekvence. `roster_set` s harnessem nahradí `coding_agent` na stejné pozici.

Nepřidávej `slow` marker. Testy musí běžet paralelně (`-n auto`), nesmí sahat mimo `tmp_path` a nesmí volat síť (remote je lokální bare repo).

### 11. Dokumentace v kódu

Docstringy nových modulů. `cli.py` popisy příkazů jsou zdroj `factory --skill`.

## Ověření

```bash
just test tests/library/test_library_config_edit.py
just test tests/test_skill.py tests/test_bundle.py tests/library tests/config
just test
just typecheck
just lint
```

Ruční kontrola (v `tmp`, ne v repu HAIFA): `factory init --commit` a pak `factory config add workflow simple-sdlc --dry-run --json` vrátí `changed: false`. `factory config set agent builder --thinking ultra --json` vrátí `invalid_value`.

## Rizika a poznámky

- `uv add` potřebuje síť jen při zamykání závislostí. Testy síť nepotřebují.
- Změna `SKILLS_DIR` a `SHARED_DIRS` ovlivní `config items` a `config status/commit`. Projdi testy v `tests/library` a `tests/config` a uprav očekávání, kde vyjmenovávají cesty.
- `.factory/` repa HAIFA neměň. Všechny testy pracují v `tmp_path`.
