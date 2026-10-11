# HAIFA — návod pro tým

HAIFA (Helios AI Factory) je lokální řídicí panel a CLI `factory`, které pouští agenty
(Claude Code, Codex, pi) na úkoly z backlogu v tvých Git repech. Tento návod popisuje, jak
si HAIFA stáhneš, zprovozníš na svém stroji a přidáš do ní svoje repa.

Agent (Claude Code, Codex, pi) dostane stejné postupy v angličtině z `factory --skill`;
výstup ulož jako jeho `SKILL.md` a po každé aktualizaci HAIFA ho vygeneruj znovu.

## Předpoklady

- **Systém:** macOS, Linux nebo Windows přes WSL. Jiný systém `factory check` hlásí jako
  `unsupported_platform`.
- **git** s nastavenou identitou:
  `git config --global user.name "Jméno Příjmení"` a
  `git config --global user.email jmeno@firma.cz`.
- **[uv](https://docs.astral.sh/uv/)** na PATH (`curl -LsSf https://astral.sh/uv/install.sh | sh`
  nebo `brew install uv`). Instaluje a aktualizuje nástroj `factory`.
- **CLI hostingu** podle `git_provider` repa: `gh` pro provider `github` (přihlášení
  `gh auth login`), `az` s rozšířením `azure-devops` pro provider `azure` (`az login`).
  Pro provider `local` žádné CLI nepotřebuješ.
- **CLI harnessů**, které tvůj roster používá, a přihlášení do nich:
  - `claude` (Claude Code): `claude auth login`,
  - `codex`: `codex login`,
  - `pi`: `pi auth login`; pi navíc potřebuje **node**.
- **just**, pokud repo spouští testy přes `justfile` (výchozí testovací příkaz repa HAIFA
  i řady týmových rep je `just test`). Kontroly, které běh pustí, volí agent tester podle
  repa; program, který na PATH chybí, nespustí.

Co chybí, ti ukáže `factory check` (viz Kontrola).

## Instalace z bundlu

HAIFA dostaneš jako zip `haifa-<verze>.zip`. Přístup k repu HAIFA nepotřebuješ, bundle
obsahuje kolo (wheel) a přesné verze závislostí.

```bash
unzip haifa-<verze>.zip
cd haifa-<verze>
./install.sh
```

Skript ověří součty v `SHA256SUMS` a nainstaluje nástroj `factory` přes
`uv tool install` s verzemi z `constraints.txt`. Když shell `factory` nenajde, spusť
`uv tool update-shell` a otevři nový terminál. `factory --version` vypíše
nainstalovanou verzi.

## Kontrola

```bash
factory check
```

Kontrola jen čte, nic nemění. Spusť ji kdekoli: mimo repo zkontroluje stroj a knihovnu,
v repu navíc repo. Každé zjištění má kód, závažnost (`error`, `warning`, `info`) a radu,
co udělat; přehled je v Řešení problémů. Dokud kontrola hlásí `error`, úkoly
nepouštěj. `factory check --offline` vynechá dotazy na hosting a přihlášení harnessů.

## Knihovna

Knihovna je Git repo v domovském adresáři HAIFA (`$HAIFA_HOME/library`, výchozí
`~/.config/haifa/library`). Obsahuje agenty, workflow, skilly a rozšíření, které repa
dědí. Tým ji sdílí přes Git remote.

- **Týmová knihovna existuje:** naklonuj ji.

  ```bash
  factory library clone <URL-týmové-knihovny>
  ```

- **Jsi první v týmu:** založ ji ze semínka, které je součástí HAIFA. S `--remote URL`
  ji rovnou nahraješ do prázdného remote, odkud si ji ostatní naklonují.

  ```bash
  factory library init --name "Knihovna týmu" --remote <URL-prázdného-repa>
  ```

Stav knihovny ukáže `factory library status --fetch`, změny ostatních stáhne
`factory library pull`, svoje commity odešle `factory library push`. Obsah vypíše
`factory library list`.

Repo bere agenty a workflow nejdřív ze své `.factory/`, potom z knihovny. Vlastní kopie
v repu vyhrává; co repo nemá, zdědí z knihovny při každém běhu.

## Přidání repa

### Repo bez factory

V kořeni repa spusť kontrolu a pak `factory init`. Náhled ukáže soubory, které vzniknou
(`.factory/config.yaml`, adresář backlogu, `.gitignore`), a otisk (digest); commit
potvrdí přesně tento plán:

```bash
cd ~/cesta/k/repu
factory check
factory init --dry-run
factory init --commit --expect <digest>
```

`factory init --commit` udělá jeden commit do base a odešle ho. Když remote přímý push
odmítne, použij `factory init --commit --pr --expect <digest>`: konfigurace pak přijde
pull requestem. Agenty a workflow `factory init` nekopíruje, repo je dědí z knihovny.

### Repo s commitnutou `.factory/` na dalším stroji

Repo, které už HAIFA používá (kolega ho přidal), jen převezmeš:

1. Naklonuj repo: `git clone <URL-repa>`.
2. Měj na stroji stejnou knihovnu jako tým (`factory library clone <URL>`, viz Knihovna).
3. V repu spusť `factory check`. Stav repa je `installed`; vyřeš zjištění stroje
   (harnessy, přihlášení, CLI hostingu). `factory init` znovu nespouštěj.

Harnessy agentů přepneš přes `factory config roster set claude` nebo
`factory config roster set codex` (s `--dry-run` jen náhled). Změna je v pracovním stromu
`.factory/agents.yaml`; běhy ji uvidí až po `factory config commit`.

### Dashboard

```bash
factory obs --repo ~/cesta/k/repu
```

Otevře dashboard na `http://127.0.0.1:4700` a repo v něm zaregistruje. Další repa přidáš
stejně, nebo přímo v dashboardu. Terminál nech otevřený.

## Aktualizace HAIFA

```bash
factory upgrade haifa-<verze>.zip
factory library seed --dry-run
factory library seed
```

`factory upgrade` přijme cestu i `https` URL, ověří součty a nainstaluje novou verzi
(`--dry-run` jen ukáže, co by udělal). Běžící dashboard (`factory obs`) pak restartuj.

Nová verze může přinést nové verze agentů a workflow v semínku. `factory library seed`
je převezme do knihovny: položky, které tým neupravil, nahradí; upravené ponechá (`kept`)
a ukáže rozdíl. Semínkovou verzi upravené položky vezmeš přes
`factory library seed --take agent/<jméno>`. Pak `factory library push`, ať ji mají i
ostatní. Repa nové verze položek zdědí při dalším běhu, vlastní kopie v repu zůstávají.

## Vydání (pro engineera)

1. Zvyš verzi v `aifactory/src/aifactory/__init__.py` (`__version__`).
2. `just check` musí projít (a `just e2e` při změně dashboardu).
3. `just bundle` vytvoří `aifactory/dist/haifa-<verze>.zip`.
4. Rozešli zip týmu; každý ho nainstaluje přes `factory upgrade`.
5. Když nová verze knihovny vyžaduje novější HAIFA, nastav v knihovně
   `min_factory_version` v `library.yaml`, commitni a odešli (`factory library push`).
   Kolegové se starší verzí pak uvidí v `factory check` chybu `factory_outdated`.

## Řešení problémů

| Kód kontroly | Oprava |
| --- | --- |
| `unsupported_platform` | HAIFA běží na macOS, Linuxu a WSL; na Windows použij WSL. |
| `git_missing` | Nainstaluj git. |
| `git_identity_missing` | `git config --global user.name "…"` a `git config --global user.email …`. |
| `uv_missing` | Nainstaluj uv (`curl -LsSf https://astral.sh/uv/install.sh \| sh`). |
| `node_missing` | Roster používá pi, nainstaluj node. |
| `harness_missing` | Nainstaluj CLI harnessu (`claude`, `codex`, `pi`), nebo přepni roster (`factory config roster set …`). |
| `harness_login` | Přihlas se: `claude auth login`, `codex login` nebo `pi auth login`. |
| `pi_model_unknown` | Model není v `pi --list-models` nebo je nejednoznačný; zaregistruj ho v pi nebo oprav `model` v `.factory/agents.yaml`. |
| `codex_not_isolated` | Codex načítá globální soubory (`~/.codex/AGENTS.md`, `~/.codex/skills`, `~/.agents/skills`); přesuň je jinam, nebo nastav `CODEX_SAFE_MODE=1`. |
| `pi_not_isolated` | pi načítá globální soubory v `~/.pi/agent`; přesuň je jinam, nebo nastav `PI_SAFE_MODE=1`. |
| `gh_missing` | Nainstaluj GitHub CLI `gh`. |
| `gh_login` | `gh auth login`. |
| `az_missing` | Nainstaluj Azure CLI `az`. |
| `az_devops_missing` | `az extension add --name azure-devops`. |
| `az_login` | `az login`, nebo nastav `AZURE_DEVOPS_EXT_PAT`. |
| `hosting_skipped` | Kontrola běžela s `--offline`; pro kontrolu hostingu ji spusť bez něj. |
| `local_config_invalid` | Oprav `.factory/local.yaml` (`trace_db`) podle zprávy kontroly. |
| `local_port_ignored` | Smaž řádek `port` z `.factory/local.yaml`; port dashboardu nastavíš přes `factory obs --port N`. |
| `env_file_mode` | `chmod 600 $HAIFA_HOME/env`. |
| `env_override` | Proměnná (`CLAUDE_SAFE_MODE`, `CODEX_SANDBOX`, …) mění chování harnessu; zruš ji, pokud ji nechceš. |
| `factory_outdated` | Knihovna vyžaduje novější HAIFA: `factory upgrade haifa-<verze>.zip`. |
| `library_missing` | `factory library clone <URL>` nebo `factory library init`. |
| `library_dirty` | Knihovna má necommitnuté změny; commitni je nebo zahoď přímo v knihovně. |
| `library_behind` | `factory library pull`. |
| `library_unpushed` | `factory library push`. |
| `seed_update_available` | `factory library seed --dry-run`, pak `factory library seed`. |

Zjištění repa (`factory_missing`, `config_not_committed`, `workflow_unknown` a další) mají
radu přímo ve výstupu `factory check`. Necommitnutou konfiguraci repa commitne
`factory config commit`.
