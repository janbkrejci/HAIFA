# HAIFA-S05-T07: `factory config add`, `set` a `remove`

Tři nové podpříkazy `factory config` spravují položky v `.factory/` repa podle knihovny. Každý nejdřív sestaví plán s digestem, plán ověří a teprve potom ho zapíše do pracovního stromu nebo jedním commitem do base.

## Příkazy

```bash
factory config add TYP JMÉNO [--as SLOT] [--harness H] [--model M] [--thinking T]
factory config set agent SLOT [--harness] [--model] [--thinking] [--tools] [--writes] [--color]
factory config remove TYP JMÉNO [--prune]
# společné volby: --dry-run | --commit [--pr] [-m TEXT], --expect DIGEST, --json, --repo PATH
```

TYP je `agent`, `workflow`, `skill` nebo `extension`. `set` zná jen `agent`.

- **add** zkopíruje položku z HEAD knihovny a zapíše ji do `.factory/manifest.yaml`. Bez knihovny bere položku ze semínka, které má jen agenty a workflow. Přidá i uzávěr: workflow přinese agenty svých kroků (roli bere z registru repa nebo z `agent:` kroku), agent přinese skilly a extensions ze svých `defaults`. Závislost, která už v repu je, zůstane beze změny (`kept`, důvod `present`). Skill se zapíše do `.claude/skills/<jméno>/` a jeho kopie do `.agents/skills/<jméno>/`. Nový slot agenta dostane `defaults` položky, v nichž se `$specs_dir/` a `$docs_dir/` nahradí hodnotami z `config.yaml`, a volby `--harness`, `--model` a `--thinking` je přepíšou. Když slot drží jiný obsah, příkaz skončí kódem `slot_taken` (oprava: `--as NOVÝ`). Stejný obsah je no-op.
- **set** změní jen vazby slotu v `agents.yaml`. Manifest ani prompty se nemění. `--tools` a `--writes` berou seznam oddělený čárkami: `''` znamená prázdný seznam, `-` klíč odebere. `--color #rrggbb` nastaví barvu, `-` ji odebere. Neznámé `thinking` nebo harness skončí kódem `invalid_value`, neznámý slot kódem `unknown_item`.
- **remove** odebere položku včetně záznamu v manifestu. U agenta zmizí položka v rosteru a jeho prompty, u skillu oba stromy. Příkaz odmítne kódem `in_use` (podrobnosti v `data.used_by`), když položku používá:
  - u agenta workflow repa nebo `roles.yaml`,
  - u workflow task backlogu v base,
  - u skillu nebo extension jiný agent v manifestu.

  `--prune` odebere i závislosti zapsané v manifestu, které už nikdo nepoužívá (`removed`, důvod `pruned`). Lokální položky `--prune` nikdy neodebere.

**Režimy** jsou stejné jako u `init`:

- `--dry-run` vypíše plán (files, added/kept/removed, bindings, blockers, validation, digest) a nic nezapíše.
- Bez volby se plán zapíše do pracovního stromu a nic se necommituje. Necommitované změny pak zapíše `factory config commit`. Běžící task zápis zablokuje kódem `run_in_progress`.
- `--commit` zapíše plán nad stromem base jedním commitem přes `providers.publish`. S `--pr` místo toho otevře PR z větve `factory-config/<n>`.

`--expect DIGEST` odmítne plán, který se od kontroly změnil (`plan_changed`). Plán musí projít `load_config` a preflightem všech workflow repa, jinak skončí kódem `invalid_plan`. Repo bez `.factory/manifest.yaml` skončí kódem `not_onboarded` (oprava: `factory onboard`).

## Soubory

| Soubor | Co nese |
|---|---|
| `aifactory/src/aifactory/library/config_edit.py` (nový) | `plan_add`, `plan_set`, `plan_remove`, `plan_config`, `run_config`: plán, kontrola použití, validace, zápis do pracovního stromu nebo commit |
| `aifactory/src/aifactory/config/yamledit.py` (nový) | `edit_yaml` a `roster_add`/`roster_set`/`roster_remove` přes ruamel.yaml round trip (zachová komentáře, pořadí klíčů, uvozovky a odsazení seznamů); nový `harness` nahradí starý klíč `coding_agent` na stejném místě |
| `aifactory/src/aifactory/cli.py` | parsery `add`/`set`/`remove`, kontrola konfliktních voleb (`--pr`/`-m` vyžadují `--commit`, `--expect` nejde s `--dry-run` → `conflicting_options`), textový i JSON výstup |
| `aifactory/src/aifactory/config/loader.py` | `SKILLS_DIR` je nově `.claude/skills` (dřív `.factory/skills`), přibyl `SKILLS_MIRROR_DIR = ".agents/skills"` |
| `aifactory/src/aifactory/config/status.py`, `config/commit.py` | sdílená konfigurace zahrnuje i `.factory/extensions/`, `.claude/skills/` a `.agents/skills/`, takže `config status/commit` je vidí |
| `aifactory/src/aifactory/config/source.py` | `OverlaySource` lze položit na libovolný `ConfigSource` a hodnota `None` v overlay znamená smazaný soubor |
| `aifactory/src/aifactory/library/install_commit.py` | z `_validate` vznikla znovupoužitelná `validate_source(source, workflows, missing)` |
| `aifactory/src/aifactory/library/install.py` | `_workflow_agents` přijme registr rolí repa; semínko bez knihovny pro skill a extension vrátí `unknown_item` |
| `aifactory/src/aifactory/providers/publish.py` | při materializaci smaže soubor naplánovaný ke smazání, pokud má ještě obsah z base, a uklidí prázdné složky |
| `aifactory/src/aifactory/skill/codes.py`, `skill/skill.md` | nové kódy `slot_taken` a `in_use`, rozšířené popisy kódů `run_in_progress`, `plan_changed`, `unknown_item`, `dirty_paths`, `invalid_plan` a `not_onboarded`; sekce „Items of the repo“ v `factory --skill` |
| `aifactory/pyproject.toml`, `aifactory/uv.lock` | nová závislost `ruamel-yaml>=0.18.10,<0.19` |
| `aifactory/tests/library/test_library_config_edit.py` (nový) | testy (viz níže) |
| `aifactory/tests/test_bundle.py`, `tests/library/test_library_version.py` | bundle počítá s `ruamel-yaml`, cesta skillu je `.claude/skills/lint` |

Upozornění: příkazy upravují jen `agents.yaml`. `config.yaml` a `roles.yaml` pouze čtou, i když `yamledit` je napsaný obecně pro všechny tři soubory.

## Ověření

```bash
cd aifactory && uv run pytest tests/library/test_library_config_edit.py -q
just test && just typecheck && just lint
```

Testy pracují s dočasnou knihovnou a holým remote repem. Pokrývají:

- add workflow s uzávěrem,
- add agenta do jiného slotu přes `--as`,
- `slot_taken` a no-op při stejném obsahu,
- skill v `.claude/skills/` i `.agents/skills/`,
- `set` se zachovanými komentáři a pořadím klíčů a round trip `yamledit`,
- neplatné `thinking`,
- remove s `in_use` a `--prune`, ponechání lokálních položek a kontrolu backlogu v base,
- `--commit` a `plan_changed`,
- `--expect` v pracovním stromu a `run_in_progress`,
- `not_onboarded`,
- konflikty voleb.

Ruční zkouška v onboardovaném repu: `factory config add workflow solo --dry-run --json` vypíše plán s `digest`. Potom `factory config add workflow solo --expect <digest>` zapíše soubory do pracovního stromu a `factory config status` je ukáže.
