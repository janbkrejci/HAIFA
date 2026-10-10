# HAIFA-S01-T12: `factory init` s náhledem, commitem do base a vazbami po agentech

## Co se změnilo a proč

`factory init` z HAIFA-S04-T01 uměl jen zapsat soubory factory do pracovního stromu. Dashboard
potřebuje u repa bez factory dvě věci: ukázat, co se nainstaluje, a nainstalovat to jedním
commitem do base. `init` má proto tři režimy:

| Režim | Volby | Co dělá |
|---|---|---|
| původní | bez `--dry-run` a `--commit` | zapíše soubory do pracovního stromu, existující přeskočí (kromě `--force`), nic necommituje. Chování z HAIFA-S04-T01 se nemění. |
| náhled | `--dry-run [--pr]` | vrátí plán a nic nezapíše |
| commit | `--commit [--pr] [--expect DIGEST] [-m TEXT]` | stejný plán provede jako jeden commit cestou z M7 (`providers/publish.py`) |

Nové volby platí ve všech režimech: `--provider local|github|azure`, `--azure-org`,
`--azure-project`, `--azure-repo`, `--backlog-dir`, `--specs-dir` a `--docs-dir`. Platí v nich
i dřívější `--agents`, `--workflows` a `--bind AGENT=HARNESS[:MODEL[:THINKING]]` (vazby po
agentech podle D24). `$specs_dir/` a `$docs_dir/` ve `writes` se nahradí zvolenými adresáři.

Nepovolené kombinace skončí kódem `conflicting_options` (exit 2). Jde o `--force` s
`--dry-run`/`--commit`, `--pr` bez jednoho z nich, `--expect` bez `--commit` nebo spolu s
`--dry-run`, `-m` bez `--commit` a `--azure-*` s jiným providerem než `azure`.

### Plán (`--dry-run --json`)

V `data` je:

- `files`: cesta, akce, diff a obsah každého souboru včetně `.factory/manifest.yaml`.
- `blockers`: `code`, `message` a u některých `fix`, tedy příkaz, který blokátor odstraní.
- `warnings`: seznam `{code, message}`.
- `digest`, `exclude` a `validation`.
- `detected`: remote (`origin`, jinak první podle abecedy), URL remote bez přihlašovacích
  údajů, base (`refs/remotes/<remote>/HEAD`, jinak aktuální větev) a provider z URL. Pro
  github.com dá provider `github`, a to v https, ssh i scp tvaru. Pro dev.azure.com,
  ssh.dev.azure.com, `*.visualstudio.com` a vs-ssh dá `azure` s organizací, projektem a repem.
  Jinak dá `local`. Dále pole `harnesses` (`installed`, `path`) pro každé harness CLI, které
  se hledá jen na PATH a nespouští se.
- `available`: agenti a workflow z knihovny, bez knihovny ze semínka. Agent nese výchozí
  `harness`, `model` a `thinking`, workflow své agenty a obojí příznak `default`.

Náhled a commit berou base, provider a azure ze zjištěných hodnot, původní režim dál
z aktuální větve a `local`. Explicitní volby mají vždy přednost.

Plán se ověří: konfigurace z base doplněná o plánované soubory (`OverlaySource`) musí projít
`load_config`. Každé plánované workflow musí projít `parse_workflow` a `preflight`. Když
ověření selže, vznikne blokátor `invalid_plan`.

Digest je `publish.plan_digest` nad plánovanými soubory. Manifest se do něj počítá s prázdným
`onboarding.at`, jinak by se digest měnil každou sekundu. Když se runtime řádky zapisují do
`info/exclude`, přidá se k digestu pseudosoubor `:info/exclude`.

### Blokátory (commit odmítne prvním z nich, exit 2)

1. `already_installed`: manifest je v base (`fix: factory update`).
2. `existing_config`: konfigurace sssf nebo `.factory/` bez manifestu (`fix: factory onboard`).
3. `config_not_committed`: manifest je jen v pracovním stromu (`fix: factory config commit`).
4. `dirty_paths`: na plánované cestě je soubor s jiným obsahem. Soubor se stejným obsahem
   nevadí.
5. `invalid_plan`: issues jsou v `data.validation.issues`, při commitu v `error.issues`.
6. Blokátory M7, jen u přímého commitu: `not_on_base`, `run_in_progress`, `base_behind` a
   `base_diverged`.

### Varování (nikdy neblokují)

- `harness_missing`: vázaný harness nemá CLI na PATH.
- `gitignore_dirty`: `.gitignore` má necommitnuté změny, proto chybějící runtime řádky jdou
  do `<git common dir>/info/exclude` (`data.exclude`). Plán pak `.gitignore` nemění. U čistého
  `.gitignore` plán doplní řádky přímo do něj.
- `foreign_content`: adresář backlogu, specs nebo docs už obsahuje jiné soubory.
- `remote_note` a `invalid_item` (neplatná položka knihovny se v `available` vynechá).

Adresář backlogu dostane `.gitkeep`, jen když neexistuje ani v base, ani na disku.

### Commit (`--commit`)

- `--expect` s jiným digestem skončí `plan_changed`.
- Přímý commit jde přes `publish_direct(..., materialize=True)`. Push proběhne dřív, než se
  pohne base. Soubory se do checkoutu base zapíší až v `_advance` po úspěšném push, těsně
  před `update-ref`. Odmítnutý push (`push_failed`) nezmění refy, index ani pracovní strom.
- `--pr` vytvoří commit ve větvi `factory-init/<n>` a otevře pull request. Base ani checkout
  se nemění.
- Do `info/exclude` se zapisuje až po úspěšném publikování (`gitops.ensure_excluded`).
- Výchozí zpráva commitu je `factory: install from the library <name>`, bez knihovny
  `factory: install from the seed`.
- Repo bez trace DB nemá store: neotevře se, aby v pracovním stromu nevzniklo
  `.factory/trace.db`. `publish` pak běží bez zámku a bez kontroly živých běhů.

## Kde to je

- `aifactory/src/aifactory/cli.py`: nové volby `init`, `_init_conflict` a `_init_plan`
  (JSON a lidský výstup s řádkem `next: factory init --commit --expect <digest>`).
- `aifactory/src/aifactory/library/detect.py` (nový): `parse_remote_url`, `RemoteInfo`,
  `detect`, `main_remote`.
- `aifactory/src/aifactory/library/install.py`: z `init_repo` jsou vytažené `Selection`,
  `project_settings`, `build_manifest` a `render_files`, které sdílí oba režimy. `init_repo`
  navíc přijímá `azure`, `backlog_dir`, `specs_dir` a `docs_dir`.
- `aifactory/src/aifactory/library/install_commit.py` (nový): `plan_init`, `commit_init`,
  `InitPlan`, `InitCommitResult` a `InitWarning`. V docstringu modulu je seznam kódů.
- `aifactory/src/aifactory/providers/publish.py`: `Blocker.fix`, `plan_contents` (plán
  z bytů v paměti), sdílené `direct_blockers`, volitelný `store` a příznak `materialize`.
- `aifactory/src/aifactory/config/commit.py`: místo vlastní logiky volá `direct_blockers`.
  Chování `config commit` se nemění.
- `aifactory/src/aifactory/config/source.py`: `OverlaySource`.
- `aifactory/src/aifactory/harness/check.py`: `binary_name` a `installed_path` (jen
  `shutil.which`).
- `aifactory/src/aifactory/skill/codes.py`: nové kódy `config_not_committed`, `dirty_paths`
  a `invalid_plan`, upravené popisy `existing_config` a `plan_changed`.
- `aifactory/src/aifactory/skill/skill.md`: nový postup `### Install`. Obsahuje
  `factory check`, náhled, ukázání plánu a digestu uživateli, commit s `--expect` a po
  `push_failed` zopakování s `--pr`, ale jen se souhlasem uživatele.

## Jak to ověřit

```bash
just test && just typecheck && just lint
uv run pytest aifactory/tests/library/test_library_detect.py \
  aifactory/tests/library/test_library_install_commit.py -q
```

- `test_library_detect.py` obsahuje tabulkový test `parse_remote_url` (github, azure ve všech
  tvarech, jiné hosty a `local`) a testy `detect` (base z remote HEAD, jiný remote,
  URL bez přihlašovacích údajů, repo bez remote).
- `test_library_install_commit.py` pracuje s holým remote. Pokrývá: náhled nic nezapíše,
  commit a push, odmítnutý push nic nezmění, PR přes falešný `gh`, `plan_changed`,
  `dirty_paths`, špinavý i čistý `.gitignore`, `existing_config` u sssf,
  `config_not_committed`, `invalid_plan`, `not_on_base` jen u přímého commitu, builder na
  codexu a ostatní agenti na claude, chybějící `pi` dá jen varování, vlastní adresáře,
  existující backlog, azure z URL, neúplné azure volby a commit bez remote. Po instalaci
  `factory check` nehlásí žádnou chybu a všechny položky v `factory config items` jsou
  `synced`.
- `aifactory/tests/validation/test_validation_template.py`: `test_workflow_names_three_harnesses`
  nahrazuje katalog `pi --list-models` modely ze sandboxu, takže výsledek nezávisí na stroji.

Ručně v dočasném repu:

```bash
factory init --dry-run --json                    # plán, digest, detected, available
factory init --commit --expect <digest> --json   # jeden commit do base
```
