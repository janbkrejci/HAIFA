# HAIFA-S01-T14: `factory update` z knihovny s migracemi

## Co se změnilo

Nový příkaz `factory update` přenese do repa nové verze položek z `.factory/manifest.yaml`. Bere je z hlavy knihovny, a když knihovna není, ze semínka. Soubor, který repo upravilo, nepřepíše bez `--take` nebo `--merge` (D20). K tomu nabízí migrace konfigurace (D26). `factory check` nově hlásí, že je co aktualizovat.

### Porovnání po souborech

Jednotkou je soubor:

- u agenta `purpose` (záznam v rosteru), `system.md` a `user.md`;
- u workflow jeho soubor;
- u skillu a rozšíření každý soubor, včetně přidaných a smazaných.

Každý soubor má tři verze: **base** (verze z manifestu, čtená z historie knihovny), **ours** (kopie v repu) a **theirs** (hlava knihovny). Pravidla (`unit_rule` v `update.py`) se zkoušejí v tomto pořadí:

| stav | kdy | výsledek |
|---|---|---|
| `restore` | položka je `missing` | chybějící soubory se doplní |
| `same` | ours = theirs | beze změny |
| `take` | ours = base | zapíše se theirs |
| `keep` | theirs = base | zůstane ours |
| `taken` | `--take TYP/JMÉNO[:SOUBOR]` | zapíše se theirs |
| `merged` | `--merge TYP/JMÉNO` | výsledek `git merge-file`. Při konfliktu nebo nevalidní položce selže `merge_conflict` a nic se nezapíše |
| `conflict` | jinak | zůstane ours, plán ukáže `ours_diff` a `theirs_diff` |
| `unknown` | verze z manifestu není v historii | base chybí. Plán ukáže diff ours proti theirs, výchozí je ponechat, `--take` převezme. `--merge` vrátí `invalid_value` |

Celá položka dostane akci `same`, `update`, `keep`, `conflict`, `unknown`, `restore` nebo `absent` (knihovna položku už nemá, varování `item_not_in_library`). Skill, který se změní, se znovu zkopíruje do `.agents/skills/`.

Stejný plán posune každý záznam manifestu na hlavu knihovny a nastaví `written_by` na nainstalovanou verzi HAIFA. Doplní chybějící prompty agentů deklarovaných v `agents.yaml` (`data.update.restored`, případně varování `prompt_missing`) a chybějící runtime řádky `.gitignore`.

### Migrace

`library/migrations.py` definuje `Migration` (id, titulek, soubor, detektor, úprava) a seznam `MIGRATIONS`. Plán vypíše každou zjištěnou migraci s diffem a varováním `migration_available`. Provede ji jen `--migrate ID`. Neznámé ID vrátí `invalid_value` a ID, které už nic nemění, dá varování `migration_not_needed`. Migrace `m001` přepíše `levels: [module, step, task]` v `.factory/config.yaml` na `[project, step, task]`. Úprava běží round tripem přes `config.yamledit.edit_yaml` a mění sekvenci na místě, takže komentáře i styl zůstanou. Migraci dělá idempotentní detektor: hledá `module` bez `project`.

### Režimy a odmítnutí

Režimy jsou stejné jako u `config add`: `--dry-run` vypíše plán s digestem, bez volby se zapisuje do pracovního stromu (blokuje `run_in_progress`) a `--commit [--pr] [--expect DIGEST] [-m TEXT]` udělá jeden commit do base nebo otevře PR. Předmět commitu je `factory: update N item(s) from …` a k němu případně `+ migrations …`.

Před plánováním příkaz odmítne:

- `not_onboarded`: v base chybí manifest. `data.fix` radí `factory onboard`, když existuje `.factory/` nebo `adws/`, jinak `factory init`.
- `config_not_committed`: manifest je jen v pracovním stromu.
- `format_unsupported`: formát manifestu je novější, než HAIFA zná.

## Soubory

- `aifactory/src/aifactory/library/update.py` (nový): `plan_update`, `run_update`, `unit_rule`, `merge_text` (obal `git merge-file`), `parse_selector` a odmítnutí.
- `aifactory/src/aifactory/library/migrations.py` (nový): migrace a `m001`.
- `aifactory/src/aifactory/library/config_edit.py`: z `plan_config` je vyčleněno `finish_plan` (blokery, validace, digest) a z `run_config` zase `execute_plan` (dry run, `--expect`, zápis). Obojí teď používá i `update`. `Command` zná `"update"` a `_subject` bere předmět z `detail.update.subject`.
- `aifactory/src/aifactory/cli.py`: podpříkaz `update`, jeho parser (`_add_update_command`), textový i JSON výstup (`_update`) a dispatch.
- `aifactory/src/aifactory/check/repo_rules.py`: pravidlo `update` hlásí `update_available` (info, akce `update`) s položkami k aktualizaci a zjištěnými migracemi. Jen čte: base rozbalí do dočasného adresáře a hlavy knihovny čte bez fetch.
- `aifactory/src/aifactory/providers/publish.py`: `_stage_matching` nastaví souboru práva podle `mode` (755 nebo 644), protože `git add` mód stageuje.
- `aifactory/src/aifactory/skill/codes.py`: nový kód `merge_conflict`, skupiny `update_item`, `update_file`, `update` a `migration`, `update_available` mezi nálezy kontroly a rozšířené popisy u stávajících kódů.
- `aifactory/src/aifactory/skill/skill.md`: nová sekce „Update from the library“. Akce `update` u `factory check` teď odkazuje na skutečný příkaz.
- `aifactory/tests/library/test_library_update.py` (nový) a `aifactory/tests/test_smoke.py` (`update` už není mezi neimplementovanými příkazy).
- `specs/HAIFA-S01-T14-factory-update-z-knihovny-s-migracemi.md`: plán tasku.

## Použití

```bash
factory update --dry-run                       # plán a digest
factory update --expect <digest>               # zápis do pracovního stromu
factory update --take agent/builder:system.md  # převezmi jeden soubor z knihovny
factory update --merge workflow/solo           # git merge-file konfliktních souborů
factory update --migrate m001
factory update --commit [--pr] -m "…"
factory check                                  # hlásí update_available
```

## Ověření

```bash
uv run pytest aifactory/tests/library/test_library_update.py aifactory/tests/test_smoke.py
just test && just typecheck && just lint
```

Testy pokrývají:

- tabulku `unit_rule` a `merge_text`;
- nahrazení, ponechání, konflikt s následným `--take`, čisté i konfliktní `--merge`, `unknown`;
- doplnění chybějícího promptu (položky i deklarovaného agenta);
- skill s přidaným a smazaným souborem;
- `m001` se zachovanými komentáři a idempotencí;
- druhý update beze změn, commit s holým remote a odmítnutí;
- selektory, řádky `.gitignore`, `update_available` v `factory check` a textový výstup.

Žádný test nevolá model ani síť.
