> Úprava (2026-10-03): repo HAIFA zůstává soukromé a HAIFA se distribuuje bundlem `haifa-<verze>.zip` (viz `docs/decisions.md`), D31 o instalaci z git tagu tím neplatí. Kódy úkolů v backlogu: L1 = HAIFA-S05-T01, L2 = HAIFA-S05-T03, L3 = HAIFA-S05-T06, L4 = HAIFA-S05-T04, L5 = HAIFA-S05-T05, L6 = HAIFA-S05-T02, L7 = HAIFA-S05-T07, L8 = HAIFA-S05-T08, L9 = HAIFA-S05-T09, L10 = HAIFA-S05-T10, L11 = HAIFA-S05-T11, L12 = HAIFA-S05-T12, L13 = HAIFA-S05-T13, L14 = HAIFA-S05-T14, M1 = HAIFA-S01-T08, M2 = HAIFA-S01-T09, M3 = HAIFA-S01-T13, M4 = HAIFA-S01-T15, M5 = HAIFA-S01-T16, M6 = HAIFA-S01-T10, M7 = HAIFA-S01-T11, M8 = HAIFA-S01-T12, M9 = HAIFA-S01-T14, M10 = HAIFA-S01-T17, M11 = HAIFA-S01-T18, M12 = HAIFA-S01-T19, M13 = HAIFA-S01-T20, M14 = HAIFA-S01-T21, M15 = HAIFA-S01-T22, O1 = HAIFA-S06-T02, O2 = HAIFA-S06-T03, O3 = HAIFA-S06-T01, O4 = HAIFA-S06-T04, O5 = HAIFA-S06-T05, O6 = HAIFA-S06-T06, P1 = HAIFA-S07-T01, P2 = HAIFA-S07-T02, P3 = HAIFA-S07-T03, P4 = HAIFA-S07-T04.

# Knihovna, onboarding a distribuce týmu: výsledný návrh

Cesty backendu jsou relativní k `aifactory/src/aifactory/`, `fe/` je `aifactory/web/src/`. Kódy navazují na `docs/design/multi-repo-dashboard.md`. Úkoly: M1 až M15 (revize), L1 až L14 (knihovna a skilly), O1 až O6 (onboarding), P1 až P4 (balíček a distribuce). RS, SK, EX, PK, OV, DR a R20 až R33 jsou kódy mapy kódu. „Rozhodnutí 1 až 9“ jsou závazná rozhodnutí engineera z 2026-10-02.

## 1. Verdikt

| Kritérium | A | B | Co rozhodlo |
|---|---|---|---|
| Věrnost rozhodnutím 1 až 9 | 5 | 3 | B nechá upravené prompty jen v repu (jeho D32 O1), takže knihovna z onboardingu nic nedostane, a nemá příkaz pro upgrade. A vytěží do knihovny a pokryje instalaci, kontrolu i upgrade. |
| Sdílení a reprodukovatelnost (D4) | 5 | 4 | B nechá balíčkový fallback workflow, který se mění s verzí HAIFA na stroji kolegy (R21). |
| Bezpečnost | 5 | 4 | A zapisuje knihovnu commitem bez checkoutu a pushne dřív, než posune lokální větev. B rebasuje lokální commity knihovny. |
| Postupné dodání | 3 | 4 | A má úkoly na víc běhů (M18, M19). B drží repo bez manifestu beze změny a úkoly jsou menší. |
| Testovatelnost bez modelu | 5 | 5 | Oba testují bez modelu a sondy se skutečnými CLI drží mimo `just test`. |
| Jednoduchost | 2 | 4 | A má dva zdroje položek (semínko a knihovna), stav `newer_seed`, index verzí semínka, `factory.requires` z tabulky funkcí a release s wheelem, constraints, součty a hatch-vcs. B má jednu knihovnu založenou ze semínka, formát jako číslo a instalaci z git tagu. |

Základem je B. Jeho kostra je jednodušší a výhody A jsou pravidla, která jdou na B naroubovat. Složitost A je ve struktuře a roubováním by nezmizela.

Z A se přebírá: upravené položky jdou při vytěžení do knihovny jako nové položky (D30), rozšíření pi jako čtvrtý typ položky (FC2), zápis knihovny commitem bez checkoutu s push před posunem (AR17), aktualizace po souborech třemi verzemi (AR24), repo s manifestem bere workflow jen ze své kopie (D32), samostatné `onboard` a `adopt` vedle `init` (T16 a D20 platí dál), stock tabulky sssf a pravidla slučování promptů, `factory upgrade`, ruamel.yaml (FC6) a limity importu.

Z B se přebírá: jedna knihovna na stroj založená ze semínka, `.factory/manifest.yaml` s celočíselným formátem, vlastnictví agenta (FC1), sloty `--as`, krok `agent:` a překryv rolí, stavy z porovnání R, M a L, `user.md` vždy z knihovny, `test_command` a `test_timeout` z `quality.py` přes `ast`, instalace z git tagu a verze z jednoho místa (D31), rozšíření `factory check` místo nového `doctor`, kontrola remote jen při onboardingu, obrazovky Tento počítač a Knihovna a očekávané výsledky na tomto stroji.

Vlastní úpravy:
1. Semínko je zdroj i bez knihovny. Verze je hash obsahu, takže repo nainstalované ze semínka je po založení knihovny hned `synced`.
2. Vytěžení je jednorázová migrace na stroji engineera (HAIFA, haifa-sandbox, Omnibus, JSST, amber). Je proto CLI-first a dashboard ho ukáže jen obecným náhledem plánu, bez průvodce mapováním (FC3). Kolegové repo převezmou (`adopt`) nebo nainstalují (`init`).
3. Dokumentace je v `aifactory/README.md`, protože úkoly projektu HAIFA smí zapisovat jen `aifactory/` a `justfile` (FC4). Obě varianty chtěly `docs/team-setup.md`.
4. D22 se dodá celé v M11 spolu s formulářem nastavení, aby dashboard pro jedno repo fungoval po každém úkolu.
5. HAIFA-S04-T01 a HAIFA-S04-T02 se přepíšou, ne zruší. Jejich id a vazby v backlogu zůstanou.

Zamítnuto: semínko jako druhý zdroj vedle knihovny (A AR16), `factory.requires` z tabulky funkcí (A AR35), release wheel s constraints a hatch-vcs (A AR35, D31 O2), `factory doctor` (A AR38, je to `factory check`), úpravy YAML podle značek `yaml.compose` (B RP9), `library sync` s rebase (B L6), `factory init` jako rozcestník podle stavu (B K8, mění sémantiku T16), upravené položky jen jako změna v repu (B D32 O1, zůstává jako volba `--keep-local`), rozšíření jen jako soubory repa (B FC4), PR do knihovny ve v1 (A AR17).

## 2. Zásady

- Z7. Běh čte jen `.factory/` z commitu base a nainstalovanou HAIFA. Knihovnu ani `$HAIFA_HOME` nečte nikdy (RS11).
- Z8. Verze položky je sha256 jejího obsahu. Pořadí verzí dává historie gitu knihovny. Nikdo nečísluje ručně.
- Z9. Každý zápis do repa nebo knihovny jde přes plán s digestem (Z1). Když akce píše do obou, knihovna se pushne první.
- Z10. Úpravu v repu nic nepřepíše bez `--take`.
- Z11. Onboarding zdroj jen čte. `adws/` a stávající soubory `.factory/` zůstanou bajtově stejné.
- Z12. Vytěžení proběhne pro repo jednou. Kolegové konfiguraci převezmou.
- Z13. Repo bez manifestu (formát 0) běží jako dnes.

## 3. Knihovna

**AR13 Domov** (zakládá ho M2: `$HAIFA_HOME`, jinak `$XDG_CONFIG_HOME/haifa`, jinak `~/.config/haifa`).
```
$HAIFA_HOME/        0700
  dashboard.yaml    registr a port dashboardu (M3, D22)
  env               volitelné KEY=VALUE pro klíče harnessů, 0600 (P1)
  library/          git klon knihovny, jeden na stroj, cestu přebije HAIFA_LIBRARY
  library.lock      flock pro zápisy CLI i dashboardu
  cache/            historie verzí, smí se smazat
  logs/             logy běhů z dashboardu (M2)
```

**AR14 Formát knihovny.**
```
library.yaml                    format: 1, id: <uuid4>, name, min_factory_version, seed: {typ/jméno: verze}
agents/<jméno>/agent.yaml       purpose, defaults
agents/<jméno>/system.md, user.md
workflows/<jméno>.yaml          stejné schéma jako .factory/workflows/
skills/<jméno>/SKILL.md + soubory          front matter: name = složka, description
extensions/<jméno>/<jméno>.ts + soubory    rozšíření pi (FC2)
```
```yaml
# agents/builder/agent.yaml
purpose: Implement the plan exactly; report every changed file.
defaults:          # jen předvyplní nový slot v repu, do verze nepatří
  harness: claude
  model: claude-opus-5-5
  thinking: medium
  writes: null     # $specs_dir/ a $docs_dir/ se při přidání nahradí hodnotou z config.yaml
  skills: []
  extensions: []
```
Jména `[a-z0-9][a-z0-9-]{0,47}`, jedinečná v rámci typu.

**AR15 Verze.** `sha256:<hex>` kanonického obsahu, v UI `v4 · 81c2e0a1` (v4 je pořadí v historii knihovny).
- agent: purpose, `system.md` a `user.md`, každá část s délkou
- workflow: bajty souboru
- skill a rozšíření: seřazený seznam (relativní cesta, spustitelnost, bajty), symlink se odmítne

Stejná funkce hashuje kopii v repu (purpose z `agents.yaml`, prompty z `.factory/prompts/<slot>/`). Stejný obsah dá stejnou verzi pod jakýmkoli jménem, takže stock obsah se nezdvojí (EX11). Starou verzi najde `git log -- <cesta položky>` a hash v každém commitu, výsledek drží `cache/`.

**AR16 Semínko.** Balíček nese `seed/agents/`: planner, builder, reviewer a documenter z `.factory/` HAIFA (bajtově stejné prompty) a scout ze sssf upravený jako planner HAIFA (řeší R32). Workflow semínka jsou balíčková `defaults/workflows/*.yaml`. `factory library init` založí knihovnu ze semínka. Bez knihovny slouží semínko jako zdroj pro `init` a pro stavy. Nové semínko po upgradu HAIFA převezme knihovna příkazem `factory library seed` (L10): položka, kterou tým od posledního semínka nezměnil, se nahradí, upravená zůstane s diffem a `--take`.

**AR17 Zápis a sdílení.** Knihovna je obyčejný git klon s volitelným remote.
1. Zápis drží flock a odmítne `library_dirty`.
2. S remote nejdřív `git fetch`. Lokální větev za remote dá `library_behind` (oprava `factory library pull`), rozejitá `library_diverged`.
3. Commit vznikne bez checkoutu nad HEAD (primitiva z M7) a pushne se bez force. Odmítnutí je `push_failed` a lokálně se nic nezmění.
4. Po úspěchu se lokální větev a pracovní strom posunou fast-forwardem.

`pull` je jen fast-forward, `push` nikdy force. Když dva upraví stejnou položku, druhý dostane `library_behind`, po `pull` vidí v plánu změnu prvního a vybere, jestli ji ponechá, zapíše svoji jako další verzi, nebo uloží novou položku (`--as`). Text se nikdy neslučuje sám. Mazání a přejmenování položek nemá ve v1 příkaz, slouží git v knihovně. Remote se ukládá a vypisuje bez přihlašovacích údajů.

## 4. Repo

**AR18 `.factory/`.**

| Cesta | Vlastník | Změna |
|---|---|---|
| `config.yaml` | repo | klíč `test_timeout` (O3) |
| `agents.yaml` | purpose z položky, zbytek repo | klíče `skills` a `extensions` u agenta (L5) |
| `roles.yaml` | repo | bez `code_steps` je překryv (L6) |
| `prompts/<slot>/` | položka agenta | — |
| `workflows/<jméno>.yaml` | položka workflow | — |
| `skills/<jméno>/` | položka skillu | nové (L5) |
| `extensions/<jméno>/` | položka rozšíření | nové (L5) |
| `manifest.yaml` | factory | nové (L4), původ a značka onboardingu |
| `local.yaml` | stroj, mimo git | jen `trace_db` (D22, M11) |

**AR19 Manifest.**
```yaml
format: 1
written_by: 0.2.0
library: {id: 2f6c0b1e-…, name: helios, remote: https://github.com/<tým>/haifa-library.git}   # null: ze semínka
onboarding:              # zapíše se jednou a dál se nemění
  source: sssf           # init, sssf nebo pre_library
  source_commit: 78db8bf…
  at: 2026-10-02T18:40:12Z
  by: Jan Krejčí         # git user.name
  factory: 0.2.0
  library_commit: 1a2b3c4…
items:                   # klíč je jméno v repu (slot)
  agents:
    planner: {item: planner, version: "sha256:…"}
    builder: {item: builder-jsst, version: "sha256:…"}
  workflows: {simple-sdlc: {item: simple-sdlc, version: "sha256:…"}}
  skills: {}
  extensions: {subagents: {item: subagents, version: "sha256:…"}}
```
Manifest je sdílená konfigurace (`SHARED_FILES`), takže ho hlídá varování D4 a bere ho `factory config commit`. Běh z něj čte jen `format`.

**AR20 Agent: obsah a vazby (FC1).** Knihovna vlastní purpose a prompty, jen ty tvoří verzi a drift. Repo vlastní slot (jméno agenta v repu) a vazby: harness, model, thinking, tools, writes, color, skills a extensions. `defaults` položky předvyplní nový slot a pak nic neřídí. Tentýž builder tak běží v jednom repu na codexu a v jiném na claude (D24) a krok workflow ho dál přepíše (RS7).

**AR21 Sloty, krok `agent:` a role (L6).**
- `--as builder` dá položku `builder-dotnet` do slotu `builder`, takže ji použijí všechny role, které builder jmenují. Role se nemění.
- Krok role ve workflow přijme `agent:` vedle `harness`, `model` a `thinking`. Krok dostane kopii role s jiným agentem, `check.py` a `interpreter.py` se nemění.
- `.factory/roles.yaml` bez `code_steps` je překryv sloučený přes balíčkový registr podle jména kroku. Soubor s `code_steps` nahradí registr jako dnes a `factory check` hlásí `roles_full_copy`.
- Role nejsou položky knihovny (FC5). Typy výstupů a gates jsou kód enginu.

**AR22 Co čte běh.**
- `load_run_config` čte z base jako dnes `config.yaml`, `agents.yaml`, role, prompty a workflow. Nově `manifest.yaml` a `skills/**` a `extensions/**` jako bajty se spustitelností (`read_bytes` na `ConfigSource`, `ls-tree` a `cat-file`).
- Formát, který nainstalovaná HAIFA nezná, zastaví `load_config` i běh kódem `format_unsupported` s příkazem `factory upgrade`.
- Repo s manifestem bere workflow jen z `.factory/workflows/`, interní `resolve` z balíčku (D32). Chybějící workflow dá `unknown_workflow` s opravou `factory config add workflow <jméno>`.
- `FactoryConfig.digest` zahrne bajty skillů a rozšíření, `SHARED_DIRS` má `.factory/skills/` a `.factory/extensions/`.

**AR23 Stavy položky (L4).** R je hash kopie v repu, M verze v manifestu, L hlava knihovny (bez knihovny semínko), H historie položky v knihovně. Stavy se počítají a neukládají.

| Podmínka, v tomto pořadí | Stav | Nabídne |
|---|---|---|
| bez záznamu v manifestu | `local` | export |
| záznam bez souborů | `missing` | obnovit, odebrat |
| R = L | `synced` | — |
| M není v H | `unknown` | `adopt`, export |
| R = M, L ≠ M | `outdated` | update |
| R ≠ M, L = M | `modified` | export, revert |
| jinak | `diverged` | update po souborech, export, revert |

**AR24 Aktualizace (`factory update`, D20, M9).** Jednotka je soubor: u agenta purpose, `system.md` a `user.md`, u workflow soubor, u skillu a rozšíření každý soubor včetně přidaných a smazaných. Base je obsah verze M z historie knihovny, ours kopie v repu, theirs hlava.
- ours = base: vezme se theirs.
- theirs = base: zůstane ours.
- ours = theirs: beze změny.
- Jinak konflikt: zůstane ours a plán ukáže oba diffy. `--take TYP/JMÉNO[:SOUBOR]` vezme theirs, `--merge TYP/JMÉNO` vezme výsledek `git merge-file`, jen když je čistý a projde validací.

Stav `unknown` nemá base, plán ukáže diff ours proti theirs a výchozí je ponechat. Po aktualizaci ukazuje manifest na hlavu, ponechaný soubor se proto ukáže jako `modified`. Tentýž plán doplní chybějící prompty, soubory a řádky `.gitignore`, obnoví manifest a nabídne migrace.

**AR25 Migrace (D26).** Migrace má id, detektor nad soubory base a transformaci. Plán vypíše zjištěné migrace s diffem a provede je jen s `--migrate ID`. Detektor ji dělá idempotentní, manifest si provedené migrace nepamatuje. `config.yaml`, `agents.yaml` a `roles.yaml` se upravují round tripem ruamel.yaml, který zachová komentáře a pořadí (FC6, R28). První migrace m001 mění `levels: [module, step, task]` na `[project, step, task]` (po HAIFA-S03-T02).

**AR26 Port (D22, M11).** `LocalSettings` nemá `port`. Starý klíč se ignoruje s varováním `local_port_ignored` a kvůli němu nic neselže (R27). Port dashboardu je `--port`, registr, 4700.

## 5. CLI (D12)

Zápis do repa: `--dry-run` (plán a digest), bez volby pracovní strom (T16, blokuje `run_in_progress`), `--commit [--pr] [--expect DIGEST] [-m TEXT]` cestou M7. Zápis do knihovny: `--dry-run`, jinak commit a push. Všechny příkazy mají `--json` a příkazy repa `--repo`.

| Příkaz | Dělá | Úkol |
|---|---|---|
| `factory library init [--name] [--remote URL]` | knihovna ze semínka, push do prázdného remote | L2, L3 |
| `factory library clone URL`, `status [--fetch]`, `pull`, `push` | týmová knihovna | L3 |
| `factory library list [--type]`, `show TYP JMÉNO [--version]` | položky, verze, historie | L2 |
| `factory library import CESTA --type TYP [--name]` | složka nebo soubor pod domovem do knihovny | L2 |
| `factory library where TYP JMÉNO` | registrovaná repa s položkou a stavem | L9 |
| `factory library seed [--take]` | nové semínko do knihovny | L10 |
| `factory config items` | stavy AR23 | L4 |
| `factory config add TYP JMÉNO [--as SLOT] [--agent A] [--harness] [--model] [--thinking] [--repos]` | položka s uzávěrem závislostí, i do více rep | L7, L9 |
| `factory config set agent SLOT [vazby]` | harness, model, thinking, tools, writes, color, skills, extensions | L7 |
| `factory config remove TYP JMÉNO [--prune]` | odmítne použitou položku (`in_use`) | L7 |
| `factory config export TYP JMÉNO [--as NOVÉ]`, `revert`, `diff` | repo do knihovny a zpět | L8 |
| `factory init [--agents] [--bind AGENT=HARNESS[:MODEL[:THINKING]]] [--workflows]` | repo bez factory | HAIFA-S04-T01, M8 |
| `factory onboard [--keep-local TYP/JMÉNO] [--name TYP/JMÉNO=NOVÉ] [--workflows]` | jednorázové vytěžení | O2, O4 |
| `factory adopt` | doplní knihovnu podle onboardovaného repa, repo nemění | O1 |
| `factory update [--take] [--merge] [--migrate ID] [--repos]` | aktualizace z knihovny | M9, L9 |
| `factory check [--offline]` | repo, stroj a knihovna, mimo repo jen stroj a knihovna | M6, O1, P2 |
| `factory upgrade [--to X.Y.Z] [--dry-run]` | nová verze HAIFA | P3 |

Uzávěr závislostí: workflow přidá agenty svých kroků (role z registru nebo `agent:`), agent své výchozí skilly a rozšíření. Obsazený slot s jiným obsahem dá `slot_taken` (oprava `--as`). `factory --skill` popisuje postupy a nové kódy jsou v `skill/codes.py`.

## 6. Skilly

**AR27 Přiřazení.** Skill je položka knihovny. `factory config add skill X --agent builder` ho zkopíruje do `.factory/skills/X/` a agentovi zapíše `skills: [X]`. `skills` se nedědí z `defaults` rosteru. `load_config` ověří, že přiřazený skill existuje, `SKILL.md` má `name` rovné složce a neprázdné `description` a agent se seznamem `tools` má `read`. Nad 2 MB nebo 200 souborů je varování. Rozšíření smí mít jen agent na pi.

**AR28 Doručení v běhu (D29, L5).**
- `prepare_cfg` zapíše přiřazené skilly a rozšíření z base do `<session>/skills/<jméno>/` a `<session>/extensions/<jméno>/` vedle `prompt_templates`, včetně spustitelnosti. Hlídač session ignoruje.
- `write_prompts` připojí k system šabloně agenta se skilly blok `## Skills` se jménem, popisem a absolutní cestou ke `SKILL.md`. Uložený `prompts/system.md` fáze ho ukáže, takže ho testy ověří bez modelu.
- Vstup rozšíření jde jako absolutní cesta do `harness_engineering`, pi ho dostane přes `-e`.
- claude dál běží s `--strict-mcp-config --safe-mode`.
- pi dostane `--no-skills --no-extensions --no-context-files --no-prompt-templates`. Explicitní `-e` se dál načte (pi 0.99.2), `PI_SAFE_MODE=0` izolaci vypne.
- codex se nemění. `factory check` hlásí `codex_not_isolated`, dokud sonda EV3 neověří izolaci.
- HAIFA nikdy nezapisuje do `~/.claude/skills`, `~/.agents/skills` ani `~/.pi/agent`.

**AR29 Nativní načítání později.** Po sondách EV1 až EV3 a podle verze HAIFA, ne nastavením: claude `--setting-sources "" --plugin-dir <session>/<agent>/plugin` místo `--safe-mode` (`--bare` rozbije OAuth, `--restricted` odmítne bypassPermissions), pi `--skill` pod `--no-skills`, codex kořen skillů a `-c skills.config`. Rejstřík zůstane jako fallback.

## 7. Onboarding

**AR30 Stavy repa (O1).** Čte se base bez fetch a bez hooků (`GIT_OPTIONAL_LOCKS=0`), pořadí shora.

| Stav | V base |
|---|---|
| `onboarded` | `.factory/manifest.yaml` |
| `pre_library` | `.factory/config.yaml` nebo `agents.yaml` bez manifestu |
| `sssf` | `adws/adw_sssf_config/*.yaml` bez `.factory/` |
| `working_tree` | konfigurace jen v pracovním stromu |
| `none` | nic z toho |

Příznaky: `sssf_leftover` (`adws/` vedle `.factory/`, HAIFA) a `alternate_rosters` (víc YAML v `adw_sssf_config`). `factory check` a inspect (M3) vrací stav a akci `init`, `onboard`, `adopt` nebo `config_commit`.

**AR31 Plán vytěžení (`factory onboard`, O2).**
1. Stav musí být `sssf` nebo `pre_library`, jinak `already_onboarded` nebo `not_installed`. Zdroj musí být commitnutý (`source_not_committed`).
2. Jediný síťový krok: `git fetch <remote> <base>` a `git ls-remote --heads <remote> factory-config/onboarding`. Blokátory `onboarded_in_remote` (oprava `factory config pull`, pak `factory adopt`), `onboarding_pending` (větev nebo PR existuje) a `remote_unchecked` (remote nedostupný). Bez remote jen varování `no_remote`. Platí i blokátory M7.
3. Knihovna: `library_missing`, `library_dirty`, `library_behind`, `library_diverged`.
4. Převodník vrátí položky, soubory repa a zprávu. Obsah, který knihovna má (verze v historii položky stejného jména nebo hlava jiné položky), se napojí. Jiný obsah dostane novou položku `<jméno>`, nebo `<jméno>-<slug repa>`, když je jméno obsazené (D30). `--keep-local TYP/JMÉNO` napojí položku stejného jména a úpravu nechá v repu.
5. Plánovaná konfigurace base projde `load_config` a preflight každého zapsaného workflow.
6. Digest pokrývá část knihovny (obsahy a sha hlavy) i část repa.

**AR32 Převod sssf (O4).**

| sssf | HAIFA | Zpráva |
|---|---|---|
| `coding_agent` | vazba `harness` (`claude_code` → `claude`) | `converted` |
| `model` | vazba `model` | id pi ověří `factory check` proti katalogu stroje |
| `thinking: auto` | `medium` | `changed_meaning`: claude běžel na medium, pi dostával `auto` |
| `tools`, `color`, `writes` | vazby | `writes: **/*.md` dokumentátora odemyká chráněné markdowny |
| `purpose` | obsah položky | `converted` |
| stock `system.md` | prompt položky z knihovny | `linked` |
| upravený `system.md` | `git merge-file -p`: base stock sssf, ours repo, theirs knihovna. Konflikt jen ze vložení vyřeší `--union`, jiný konflikt nechá text knihovny | `carried_over`, jinak `manual` s citací změny |
| `user.md` | vždy text knihovny | sssf jmenuje výstupy podle `adw_id` a HAIFA je vrací (R25), úprava je `manual` |
| agent bez stock předlohy | prompty beze změny | `manual` |
| `harness_engineering` | položky rozšíření s relativními importy, vazba `extensions` | `subagents.ts` táhne `themeMap.ts` |
| `defaults.protected_files` | `config.yaml` plus `.factory/` | `converted` |
| `data_dir`, `observability` | vynechá se | `not_converted` |
| stock chainy `adw_plan`, `adw_plan_build`, `adw_plan_build_test`, `adw_simple_sdlc`, `adw_document`, `adw_scout` | workflow stejného jména z knihovny, scout táhne agenta scout | podle blob id, `adw_simple_sdlc.py` má dvě stock verze (a6a5c4c… a 3f5d483…) |
| jiné a upravené chainy, recepty | — | `not_converted` nebo `manual` |
| `quality.py` | `test_command` a `test_timeout` z literálů `QualityCheckSpec` přes `ast` | lint, typecheck a build `not_converted` |
| ostatní změny `adw_modules/` | — | `manual`, je to kód enginu (EX7) |
| `.claude/skills/sssf`, justfile, `.env`, skripty | zůstanou | `left_in_place` |

Do repa jde `simple-sdlc`, další přes `--workflows` nebo později `config add`. Stock texty 10 promptů z `vendor/sssf/templates/prompt_engineering/` a blob id chainů jsou v balíčku, protože vytěžit může i stroj bez `vendor/`.

**AR33 Případ `pre_library` (O2).** Agenti, prompty a workflow se zahashují a napojí. Workflow, která jmenuje backlog v base a v repu chybí, se přidají z knihovny. Existující soubory zůstanou bajtově stejné, plán jen přidává.

**AR34 Doručení a značka.**
1. Plán se přepočítá, jiný digest je `plan_changed`.
2. Knihovna dostane commit a push (AR17). Odmítnutí zastaví vše dřív, než se sáhne na repo.
3. Repo dostane commit bez checkoutu (M7) s manifestem a blokem `onboarding`, přímo do base nebo jako PR z pevné větve `factory-config/onboarding`. Zpráva jde do commitu i do popisu PR.
4. Selhání po push knihovny nechá nepoužité verze. Neškodí a opakovaný onboarding je napojí.
5. `adws/`, justfile, `.claude/` a `.env` zůstanou (Z11). Smazání `adws/` je samostatný commit engineera.

Jednorázovost drží blok `onboarding` v base, kontrola remote base a pevná větev PR (R20).

**AR35 Převzetí na stroji kolegy (`factory adopt`, O1).** Repo se nemění.
- Stav `onboarded` vylučuje vytěžení. Check i dashboard ukážou, kdo, kdy, z čeho a s jakou knihovnou repo onboardoval.
- Bez knihovny: `library_missing` s příkazem `factory library clone <remote z manifestu>`.
- Knihovna s jiným `id`: varování `library_mismatch`.
- Položku, kterou knihovna vůbec nemá, naimportuje z kopie v base (stejné verze se nezdvojí). Verze chybějící v existující položce zůstane `unknown` s opravou `config export --as`.
- Starý klon bez manifestu ukáže `sssf` nebo `pre_library`, ale plán `onboard` skončí na `onboarded_in_remote` (R20).

**AR36 Očekávané výsledky na tomto stroji.**

| Repo | Stav | Knihovna | Repo |
|---|---|---|---|
| HAIFA | `pre_library`, `sssf_leftover` | nic, 4 agenti se rovnají semínku | manifest, `simple-sdlc` a `plan-build-test` (jmenuje je backlog) |
| haifa-sandbox | `pre_library` | nic s `--keep-local` pro 4 agenty a `simple-sdlc` (validační pravidla) | manifest, úpravy zůstanou jako `modified` |
| Omnibus (GitHub) | `sssf` | nic, 5 stock agentů | `test_command [just, test]`, `test_timeout 1800`, zpráva `auto` → `medium` a lint `not_converted` |
| JSST (bez remote) | `sssf` | `builder-jsst` (union), `reviewer-jsst` (čistý merge), rozšíření `subagents` | pi vazby a rozšíření, jen commit |
| amber-swiss-clock (GitHub) | `sssf` | `builder-amber-swiss-clock` (čistý merge), `subagents` se napojí | pi vazby a rozšíření |

Slučování promptů JSST a amber je ověřené na tomto stroji přes `git merge-file -p` (jen výstup na stdout).

## 8. Distribuce týmu

**AR37 Instalace.** Předpoklady: macOS, Linux nebo WSL (POSIX signály), git s `user.name` a `user.email`, uv, gh přihlášený s přístupem k `janbkrejci/HAIFA` (pro Azure repa az), CLI harnessů z rosterů a jejich přihlášení, node pro pi a just tam, kde ho používá testovací příkaz.
```
gh auth login && gh auth setup-git
uv tool install "git+https://github.com/janbkrejci/HAIFA@v0.2.0#subdirectory=aifactory"
factory check
factory library clone https://github.com/<tým>/haifa-library.git
factory obs
```
SSH varianta: `git+ssh://git@github.com/janbkrejci/HAIFA.git@v0.2.0#subdirectory=aifactory`. uv doplní Python 3.11+. Build frontendu je ve `web/static`, bun není potřeba. Odinstalace `uv tool uninstall aifactory`, `$HAIFA_HOME` i repa zůstanou. Engineer dál vyvíjí přes `just factory` (editovatelná instalace).

**AR38 Verze a vydání (D31, P1).** Verze je jen v `__init__.py` (hatch `dynamic`). Závislosti mají horní meze, protože `uv tool install` ignoruje `uv.lock`. Vydání: verze, `just check`, commit, tag `vX.Y.Z`, push tagu. Patch nemění formát, minor smí přidat formát manifestu spolu s migrací. Tým ohlásí povinný upgrade polem `min_factory_version` v `library.yaml`.

**AR39 Upgrade (`factory upgrade`, P3).** Z `direct_url.json` instalace (PEP 610) vezme git URL a podadresář, z `git ls-remote --tags` nejvyšší `vX.Y.Z`, ukáže současnou a cílovou verzi a `min_factory_version` knihovny a spustí `uv tool install --force` s novým tagem. Editovatelnou nebo jinou instalaci odmítne s ručním postupem. Běžící dashboard potřebuje restart, běhy spuštěné potom už jedou na nové verzi (D15).

**AR40 Kontrola stroje (`factory check`, P2).** Mimo repo jen stroj a knihovna. Nález má tvar M6, `--offline` vynechá síť a přihlášení.

| Skupina | Kódy |
|---|---|
| instalace | `factory_outdated` (proti `min_factory_version`), `format_unsupported` |
| platforma a nástroje | `unsupported_platform`, `git_missing`, `git_identity_missing`, `uv_missing`, `node_missing`, `test_command_missing` |
| harnessy | `harness_missing`, `harness_login` (`claude auth status`, `codex login status`, `pi auth check --model M --json --no-refresh`), `pi_model_unknown` |
| hosting | `gh_login`, `az_login` |
| knihovna | `library_missing`, `library_dirty`, `library_behind`, `library_unpushed`, `seed_update_available` |
| prostředí | `env_file_mode`, `env_override` (`CLAUDE_SAFE_MODE`, `CLAUDE_MCP_CONFIG`, `CLAUDE_PERMISSION_MODE`, `CODEX_SAFE_MODE`, `CODEX_SANDBOX`, `PI_SAFE_MODE`), `codex_not_isolated` |
| repo navíc | stavy položek, `workflow_not_in_repo`, `roles_full_copy`, `unknown_thinking`, `sssf_leftover`, `local_port_ignored` (M11) |

`factory harness check --config` přestane padat (PK5) a načte roster loaderem HAIFA.

**AR41 Prostředí (P1).** `engine/utils.py` už nenačítá `.env` při importu. CLI načte `$HAIFA_HOME/env` a nepřepíše, co prostředí už má. `just factory` dál načítá `.env` HAIFA přes `set dotenv-load`. Přednost mají přihlášení harnessů.

**AR42 První spuštění.** `factory` bez příkazu vypíše nápovědu a „První spuštění: factory check“. Dashboard s prázdným registrem otevře Tento počítač, když kontrola hlásí chybu nebo chybí knihovna, jinak prázdný přehled (L13). Nic neinstaluje a nikam nepřihlašuje.

**AR43 Dokumentace (P4, FC4).** `aifactory/README.md` česky: předpoklady, instalace, kontrola, knihovna, přidání repa (`init`, `adopt`), onboarding (jednou), upgrade, vydání a řešení problémů podle kódů kontroly. `factory --skill` nese stejné postupy pro agenty.

## 9. Dashboard

- UI1 Tento počítač (`#/setup`, L13): skupiny AR40 s opravou a tlačítkem Kopírovat, Znovu zkontrolovat a knihovna (Naklonovat týmovou knihovnu…, Založit ze semínka, Pull, Push).
- UI2 Knihovna (`#/library`, L13): záložky Agenti, Workflow, Skilly a Rozšíření pi. Řádek: jméno, popis, `v4 · hash`, datum, autor a čipy rep podle stavu. Detail: soubory, historie a použití s Diff a zaškrtnutím pro Přidat do repozitářů… a Aktualizovat vybraná repa… (plán po repech, provádí se po jednom, R31). Import… ze složky pod domovem s náhledem.
- UI3 Záložka Factory (M14, L14): Agenti (slot, položka se stavem, harness, model a thinking v řádku, skilly, writes, označené sloupce knihovny), Workflow, Skilly a Rozšíření pi. Akce Přidat z knihovny…, Diff, Aktualizovat, Exportovat, Vrátit, Odebrat a Kopírovat do… (export a add přes dvě repa).
- UI4 Onboarding a převzetí (O5): štítky Bez factory, sssf, HAIFA před knihovnou, Onboardováno (kdo, kdy, z čeho), Onboardováno na remote a Čeká v PR. Vytěžení ukáže obecný náhled plánu se sekcemi Knihovna, Repozitář a Zpráva a modál „Commitnout N položek do knihovny <jméno> a pushnout, pak M souborů do <base> a pushnout? adws/ zůstane beze změny.“ Volby po položkách jsou jen v CLI (FC3). Převzetí: Naklonovat knihovnu z remote manifestu a Doplnit knihovnu.
- UI5 Bannery: `format_unsupported` zakáže spuštění s důvodem, `factory_outdated` a knihovna pozadu.
- F4 (editory) staví na stejných akcích: editor má cíl kopii v repu (commit podle D4) nebo položku knihovny (commit knihovny) a záhlaví se stavem a akcemi Export, Aktualizovat, Vrátit a Kde se používá (OV1, OV2). Tento plán F4 nedodává.

| # | Endpoint | Úkol |
|---|---|---|
| E15 | `GET /api/machine/check?offline=&fresh=` | L11 |
| E16 | `GET /api/library` (stav, položky, počty použití) | L11 |
| E17 | `GET /api/library/items/{type}/{name}?version=` | L11 |
| E18 | `POST /api/library/plan`, `/apply` (`init`, `clone`, `import`, `seed`), `/pull`, `/push` | L11 |
| E19 | `GET /api/repos/{id}/factory/items` | L12 |
| E20 | E12 a E13 s akcemi `add`, `set`, `remove`, `export`, `revert`, `onboard`, `adopt` a volbami `update` | L12 |
| E21 | `POST /api/library/repos-plan {action, type, name, repos}` pro přidání a aktualizaci ve více repech | L12 |
| E5 | inspect se stavy AR30 | M3 |

## 10. Bezpečnost

- S9. Repo i knihovna se mění jen potvrzeným plánem s digestem. GET nic nezapisuje. Výpočet plánu smí udělat fetch, nikdy neposune větev ani nezapíše soubor.
- S10. Úprava v repu přežije každý update, pokud ji uživatel výslovně nepřevezme. Odebrání upravené položky ukáže ztracený obsah v plánu.
- S11. Onboarding commituje jen přidané soubory pod `.factory/` a řádky `.gitignore`. Testy ověří bajty zdroje.
- S12. Knihovna nikdy nedostane force push ani přepis historie a pushuje se před commitem repa.
- S13. Import a pull ukážou změněné soubory a zvýrazní spustitelné soubory a shebangy. Skripty skillů běží pod bypassPermissions (`agent_cc.py`, `codex.py`), proto se do běhu dostanou jen commitem repa, který uživatel potvrdil (R30).
- S14. Jména položek se validují, symlinky odmítnou, limit je 2 MB a 200 souborů. Import jen z cest pod domovem, materializace jen do session.
- S15. HAIFA nezapisuje do domovských složek harnessů a neukládá tokeny. Remote knihovny se ukládá bez přihlašovacích údajů.
- S16. Běh odmítne formát, který nainstalovaná HAIFA nezná.
- S17. Zápis do pracovního stromu (`init`, `update`, `config` bez `--commit`) blokuje běžící běh v repu (`run_in_progress`), protože hlídač po každém volání agenta vrací hlavní checkout.

## 11. Testy bez modelu

- V8. Položky: zlaté verze, stejná verze z knihovny i z kopie v repu, validace, semínko projde `load_config` a preflight všech balíčkových workflow včetně scout (L1).
- V9. Knihovna pod dočasným `HAIFA_HOME` s holým remote: init, clone, pull, push, `library_behind`, `push_failed` přes `pre-receive` hook beze změny refů, flock (L2, L3).
- V10. Stavy AR23 nad dočasnou historií, brána formátu, workflow jen z repa (L4).
- V11. Skilly s falešným harnessem: materializované binární a spustitelné soubory, rejstřík v uloženém `system.md`, argv pi a claude přes FakePopen (`tests/harness/harness_fakes.py`), varování D4 (L5).
- V12. add, set, remove, export, revert a update s holými remote: uzávěr, `slot_taken`, zachované komentáře YAML, `--take`, `--merge`, m001, operace ve více repech se zablokovaným repem (L7 až L9, M9).
- V13. Onboarding nad fixturami z `vendor/sssf/templates/` se záplatami JSST, amber a Omnibus a nad kopií `.factory/` HAIFA: zlaté zprávy, union, rozšíření s `themeMap.ts`, bajty zdroje, `already_onboarded`, `onboarded_in_remote` z druhého klonu, `onboarding_pending` a `adopt` z druhého `HAIFA_HOME` (O1, O2, O4).
- V14. Kontrola s falešnými binárkami na PATH a `--offline` bez sítě (P2), upgrade s falešnými `git` a `uv` (P3), wheel postavený přes `hatchling` bez sítě (P1).
- V15. Vitest a Playwright pro nové obrazovky a akceptační test O6.

Sondy se skutečnými CLI pouští engineer mimo `just test` (R24):
- EV1 claude: `--setting-sources ""` s `--plugin-dir`, OAuth funguje, osobní skilly, CLAUDE.md, hooky a auto memory se nenačtou.
- EV2 pi: `--skill` pod `--no-skills`.
- EV3 codex: `--disable` pro memories, hooks, plugins a apps, `--enable skip_host_skill_discovery` nebo `-c skills.config`.
- EV4 rejstřík s kanárkovým skillem na všech třech harnessech.
- EV5 `uv tool install` z tagu na druhém stroji (D2 zatím neověřené).

## 12. Dodání

| Úkol | Obsah | Závisí na |
|---|---|---|
| L1 | položky, verze, validace, semínko se scoutem | — |
| L2 | knihovna v domově: init ze semínka, list, show, import, historie | L1, M2, M7 |
| L3 | sdílení knihovny přes remote | L2 |
| L4 | manifest, brána formátu, workflow jen z repa, `config items` | L2 |
| L5 | skilly a rozšíření v konfiguraci a v běhu, izolace pi | L1 |
| L6 | krok `agent:`, překryv rolí | — |
| HAIFA-S04-T01 | `factory init` z knihovny s manifestem (přepsaný) | HAIFA-S03-T01, HAIFA-S03-T02, L1, L2, L4 |
| M8 | náhled a commit initu, vazby po agentech | M7, HAIFA-S04-T01 |
| L7 | `config add`, `set`, `remove`, ruamel.yaml | L4, L5, L6, M8 |
| L8 | `config export`, `revert`, `diff` | L7, L3 |
| M9 | `factory update` z knihovny, migrace | L7, M8 |
| L9 | kde se používá, přidání a aktualizace ve více repech | M9, M3 |
| L10 | semínko do knihovny | L3 |
| O1 | stavy repa, `factory adopt` | L3, L4, M6 |
| O2 | `factory onboard`, případ `pre_library` | O1, L8, M8 |
| O3 | `test_timeout` | — |
| O4 | převod sssf | O2, O3, L5 |
| P1 | verze, meze závislostí, wheel, `$HAIFA_HOME/env` | M2 |
| P2 | kontrola stroje, knihovny a položek | M6, L3, L4, L5, P1, O1 |
| P3 | `factory upgrade` | P1, L3 |
| P4 | `aifactory/README.md` a postupy ve skillu | P2, P3, O1, O4, L9, L10, HAIFA-S04-T02 |
| L11 | API knihovny a stroje | M3, P2, L3, L9, L10 |
| L12 | API položek, onboardingu a více rep | M10, L8, L9, O1, O2, O4 |
| L13 | UI Tento počítač a Knihovna | L11, L12, M15 |
| L14 | UI záložka Factory: položky a přenos | L13 |
| O5 | UI onboarding a převzetí | L14 |
| O6 | akceptační test | O5 |

Revize M: M3 bere stav repa z O1, M6 závisí jen na HAIFA-S03-T01, M8 a M9 viz tabulka, M10 nové volby plánu, M11 celé D22, M13 stavy AR30, M14 formulář po agentech a skupiny AR24. M1, M2, M4, M5, M7, M12 a M15 zůstávají.

Backendové úkoly se prokládají s řetězcem plánu 14 bodů. Frontendové úkoly (M11 až M14, L13, L14, O5) běží po jednom a až po HAIFA-S03-T05 (D28). Nejkratší cesta k prvnímu kolegovi z CLI: L1, M6, M7, P1, L2, L4, HAIFA-S04-T01, L3, M8, O1, L7, L8, O2, P2, P3, P4. Nové úkoly patří do kroků backlogu S05 Dashboard pro více repozitářů (M), S06 Knihovna a skilly (L), S07 Onboarding (O) a S08 Distribuce (P).

## 13. Úpravy multi-repo-dashboard.md

| Kód | Změna |
|---|---|
| DR1 | doplnit plné texty D14 až D28 ze scratchpadu (`multirepo.json`) |
| DR2 | Z2 a AR1: domov drží registr, knihovnu, env, cache a logy (AR13), port jen v registru |
| DR3 | AR11 nahradí AR26 |
| DR4 | W1 doplní AR42 |
| DR5 | E5 a W2 dostanou stavy AR30, kontrola remote jen v plánu onboardingu |
| DR6 | W3, K3 a M8: agenti z knihovny s vazbami po agentech, manifest s původem |
| DR7 | AR9 nahradí AR19 a AR24, věta „Balíčková workflow a roles.yaml se nekopírují“ padá, HAIFA je případ `pre_library` |
| DR8 | AR7 dostane akce `onboard`, `adopt`, `add`, `set`, `remove`, `export`, `revert` a blokátory AR31, digest přes knihovnu i repo |
| DR9 | AR10 a M6 rozšíří AR40 a stavy položek |
| DR10 | API E15 až E21 a CLI z kap. 5 |
| DR11 | dodání z kap. 12 |
| DR12 | brief „Soubory v repu“ (řádek 80): `skills/`, `extensions/`, `manifest.yaml` |

## 14. Rizika

R20 řeší AR31 krok 2 a AR34. R21 řeší AR22 (workflow jen z repa), `min_factory_version` a brána formátu, rozdíly enginu mezi verzemi zůstávají. R22 pořadí AR34 a `adopt` z kopií v repu. R23 AR28 a `env_override`. R24 rejstřík ve v1 a sondy EV1 až EV4. R25 `user.md` z knihovny a `manual`. R26 O3. R27 AR26. R28 ruamel.yaml, zdroj zůstává v gitu. R29 P1 až P3 a AR37. R30 S13. R31 operace po repech, idempotentní. R32 semínko se scoutem a AR33. R33 přepis HAIFA-S04-T01 a HAIFA-S04-T02, než je někdo spustí.

Nová rizika:
- R34. Rejstřík spoléhá na to, že model `SKILL.md` opravdu přečte. Změří to EV4.
- R35. Izolace pi vypne agentům JSST, amber a validačního rosteru pi osobní rozšíření (například max-thinking.ts) a `AGENTS.md` a `CLAUDE.md` repa. Zpráva onboardingu a poznámky k verzi to řeknou.
- R36. `--union` může zdvojit pravidla. Použije se jen na čistá vložení a náhled ho ukáže.
- R37. Kde se používá vidí jen repa registrovaná na tomto stroji.
- R38. Brána formátu zastaví kolegu se starou HAIFA po aktualizaci repa. Zpráva nese příkaz `factory upgrade`.
- R39. Codex agenti načítají osobní skilly, dokud neprojde EV3.
- R40. Task s workflow, které repo s manifestem nemá, selže před startem. `factory check` hlásí `workflow_not_in_repo` a onboarding přidá workflow backlogu.
- R41. Instalace z git tagu je neověřená (EV5) a bez zámku závislostí. Horní meze riziko zmenší.

## 15. Rozhodnutí

Otevřená rozhodnutí s doporučením: D26 migrace, D29 skilly ve v1 a izolace, D30 upravené položky při vytěžení, D31 distribuce, D32 workflow v repu s manifestem.

Pevné volby návrhu:
- FC1. Knihovna vlastní purpose a prompty agenta, repo slot a vazby. Jinak by každá volba modelu v repu (D24) byla drift a blokovala aktualizace promptů.
- FC2. Rozšíření pi je čtvrtý typ položky se stejnou mechanikou jako skill. JSST a amber potřebují `subagents.ts` s `themeMap.ts` a izolace pi vypne osobní rozšíření.
- FC3. Vytěžení je CLI-first, dashboard ho ukáže obecným náhledem plánu. Proběhne jednou na pět rep tohoto stroje.
- FC4. Dokumentace je v `aifactory/README.md`, kam úkoly HAIFA smí zapisovat.
- FC5. Role nejsou položky knihovny. Typy výstupů a gates jsou kód enginu.
- FC6. YAML se upravuje přes ruamel.yaml (nová běhová závislost), aby zůstaly komentáře rosterů.

## 16. Kroky engineera

- A5. Přepsat HAIFA-S04-T01 a upravit HAIFA-S04-T02 podle seznamu změn, než je někdo spustí (R33).
- A6. Rozhodnout D26 a D29 až D32 a zapsat je s plnými texty D14 až D28 do `docs/decisions.md`. V briefu upravit port (řádek 196), soubory v repu (řádek 80), `just obs` na `factory obs` (řádky 29 a 183) a F6 bez převodu ADW (řádek 261, převod dělá O4).
- A7. Po L3 založit soukromý repozitář týmové knihovny a spustit `factory library init --remote <url>`. Dát kolegům čtení `janbkrejci/HAIFA` a knihovny.
- A8. Po O2 onboardovat HAIFA (`factory onboard --repo . --dry-run`, pak `--commit`), když neběží žádný chain, potom haifa-sandbox s `--keep-local`. Po O4 Omnibus, amber a JSST.
- A9. Po P1 přesunout klíče pro nástrojovou instalaci do `$HAIFA_HOME/env`.
- A10. Po P4 vydat v0.2.0 a projít AR37 na druhém stroji (EV5).
- A11. Pustit sondy EV1 až EV4 před nativním načítáním skillů.
- A12. Po M11 změnit `just dash` na `factory obs --repo .`.