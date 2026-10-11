# HAIFA-S04-T01: `factory init` do stávajícího repa

## Co se změnilo

Nový příkaz `factory init` nainstaluje factory do git repa, které ji ještě nemá. Do té doby `.factory/` nezakládal žádný příkaz. Položky (agenti a workflow) bere z HEAD knihovny v `$HAIFA_HOME`. Když knihovna neexistuje, bere je ze semínka v balíčku. Oba zdroje se nemíchají.

Zapíše:

- `.factory/config.yaml` s klíči `base`, `git_provider`, `backlog_dir`, `specs_dir` a `docs_dir`,
- `.factory/agents.yaml` se slotem pro každého agenta. Slot sestaví `roster_entry` z položky (`purpose`, vazby z `defaults`, adresáře z `config.yaml`) a `--bind` ho přepíše,
- `.factory/prompts/<agent>/{system,user}.md` zkopírované z položky,
- `.factory/workflows/<jméno>.yaml`,
- `.factory/manifest.yaml` s `written_by`, knihovnou (`id`, `name`, `remote` bez přihlašovacích údajů, bez knihovny `null`), blokem `onboarding` (`source: init`, commit repa a knihovny, čas, autor) a verzí každé položky,
- `<backlog_dir>/.gitkeep`,
- chybějící řádky `.gitignore`: `.factory/data/`, `.factory/worktrees/`, `.factory/local.yaml`, `.factory/trace.db*`. Řádek, který už v souboru je, se nepřidá.

Výchozí hodnoty: base je aktuální větev (při odpojeném HEAD je `--base` povinné), provider `local`, agenti planner, builder, reviewer a documenter, workflow `simple-sdlc`. Agenty z kroků vybraných workflow, kteří v `--agents` chybí, init doplní a vrátí je v `added_agents`.

Odmítnutí. V obou případech init nic nezapíše:

- `already_installed`, když je `.factory/manifest.yaml` commitnutý v HEAD nebo v base. Chyba radí `factory update`. Manifest, který jen leží v pracovním stromu, odmítnutí nespustí.
- `existing_config`, když chybí manifest a existuje `.factory/config.yaml`, `.factory/agents.yaml` nebo `adws/adw_sssf_config/`. Chyba radí `factory onboard`.

Existující soubory init přeskočí a vypíše je jako `skipped`. `--force` je přepíše a vypíše jako `overwritten`. Init nic necommituje a nezapisuje do knihovny ani do `$HAIFA_HOME`.

## Soubory

| Soubor | Změna |
|---|---|
| `aifactory/src/aifactory/library/install.py` | nový modul: `init_repo`, `parse_binding`, `Binding`, `InitResult`, kontroly odmítnutí, výběr zdroje (`_Source`), agenti z workflow, zápis souborů a `.gitignore` |
| `aifactory/src/aifactory/cli.py` | podpříkaz `init` s volbami `--repo`, `--base`, `--provider`, `--agents`, `--bind` (lze opakovat), `--workflows`, `--force`, `--json` |
| `aifactory/src/aifactory/library/remote.py` | veřejná funkce `remote_url()`: URL `origin` knihovny bez uživatele a hesla |
| `aifactory/src/aifactory/skill/codes.py` | chybové kódy `already_installed` a `existing_config` (exit 2) |
| `aifactory/src/aifactory/skill/skill.md` | akce `init` teď odkazuje na příkaz `factory init` |
| `aifactory/tests/library/test_library_install.py` | nové testy |
| `aifactory/tests/test_smoke.py` | `init` zařazený mezi implementované podpříkazy |
| `specs/HAIFA-S04-T01-factory-init-do-stavajiciho-repa.md` | spec tasku |

`--bind AGENT=HARNESS[:MODEL[:THINKING]]` ověří jméno agenta, harness (`harness.canonical`) i úroveň thinking (`THINKING_LEVELS`). Chybný zápis nebo agent mimo výběr skončí chybou `invalid_value`. Když `--bind` změní harness a model nebo thinking vynechá, původní hodnota ze slotu se smaže, aby nezůstal model jiného harnessu.

## Použití

```bash
factory init                                         # výchozí sada ze semínka nebo knihovny
factory init --bind builder=codex:gpt-5.5:high --json
factory init --workflows scout                       # doplní agenta scout
factory init --force                                 # přepíše existující soubory
```

Textový výstup vypíše každý soubor s akcí, přidané řádky `.gitignore`, zdroj (`seed` nebo `library <jméno>`) a další krok: zkontrolovat změny a commitnout `.factory/`, backlog a `.gitignore` do base.

## Ověření

```bash
uv run pytest aifactory/tests/library/test_library_install.py
just test && just typecheck && just lint
```

Testy běží nad dočasným git repem a dočasným `HAIFA_HOME` a nevolají model. Pokrývají:

1. init ze semínka a kontrolu, že prompty neobsahují `haifa-validate`,
2. init z knihovny s upraveným builderem, kdy manifest nese jeho verzi a knihovnu,
3. `--bind` a odmítnutí chybných vazeb,
4. doplnění agentů z workflow,
5. přeskočení všeho při druhém spuštění, přepsání s `--force` a `.gitignore` bez duplicit,
6. odmítnutí `already_installed` (i s `--force`) a `existing_config`,
7. odmítnutí odpojeného HEAD bez `--base`,
8. platnost výsledku po commitu: projdou `config show` a `backlog check` a `config items` ukáže všechny položky `synced`,
9. běh tasku s falešným harnessem v nainstalovaném repu, který doběhne `succeeded`.
