# Instalace

Instalace GIRO z `giro-<verze>.zip`. Také `INSTALL.md` v bundlu a kapitola **Instalace** v dashboardu.

Bundle obsahuje wheel `aifactory`, `constraints.txt`, instalační a odinstalační skripty pro POSIX i Windows, licence a `SHA256SUMS`.

## Co budeš potřebovat

- **Systém:** macOS, Linux, Windows přes WSL, nebo Windows 10/11 x64 nativně (bez WSL).
- **Git** s nastaveným jménem a e-mailem pro commity.
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** a Python 3.11 nebo novější. uv instaluje a aktualizuje nástroj `giro`.
- **Bash, `curl` a `unzip`** pro instalaci na macOS a Linuxu. Na Windows stačí `winget`, ostatní doinstaluje `install.bat`.
- **CLI hostingu** podle toho, kde máš repa: [GitHub CLI](https://github.com/cli/cli#installation) (`gh`) pro GitHub, Azure CLI `az` s rozšířením `azure-devops` pro Azure DevOps. Pro čistě lokální repa (provider `local`) žádné CLI nepotřebuješ.
- **Alespoň jeden harness**, tedy CLI agenta, nainstalovaný a přihlášený: [Claude Code](https://code.claude.com/docs/en/setup) (`claude`), [Codex CLI](https://github.com/openai/codex) (`codex`) nebo [pi](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent) (`pi`, potřebuje Node.js).
- **just**, pokud tvoje repa spouštějí testy přes `justfile`.

Chybějící nástroje ukáže `giro check` nebo **Kontrola počítače** na stránce **Knihovna**.

## macOS

Nástroje přes [Homebrew](https://brew.sh/):

```bash
brew install git gh uv
uv python install 3.12
```

## Linux a WSL

Například Ubuntu 24.04 (ve WSL stejně):

```bash
sudo apt update
sudo apt install git bash curl unzip gh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
```

## Identita a přihlášení

Identita pro commity a přihlášení GitHub CLI:

```bash
git config --global user.name "Tvoje jméno"
git config --global user.email "tvuj@email.cz"
gh auth login
gh auth setup-git
```

Pro Azure DevOps místo toho:

```bash
az extension add --name azure-devops
az login
```

Harness, například Claude Code:

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude
```

Při prvním spuštění `claude` dokonči přihlášení. Ostatní harnessy: `codex login`, `pi auth login`.

## Instalace balíčku

`giro-<verze>.zip` získáš od správce. Cílové repo `janbkrejci/GIRO` bude instalačním zdrojem až po ověřeném cutoveru T06. Dosud aktivní [vydání HAIFA](https://github.com/janbkrejci/HAIFA/releases/latest) obsahují `haifa-H.zip` (H: poslední HAIFA 0.1). Rozbal ho a spusť instalační skript:

```bash
unzip giro-<verze>.zip
cd giro-<verze>
./install.sh
uv tool update-shell
```

Skript ověří součty v `SHA256SUMS`, nainstaluje nástroj `giro` přes `uv tool install` s verzemi závislostí z `constraints.txt` do samostatného prostředí uv a připraví a obnoví knihovnu (viz [Výchozí knihovna](#/guide/instalace/vychozi-knihovna)). `uv tool update-shell` přidá adresář nástrojů uv na PATH; pak otevři nový terminál.

## Windows bez WSL

Na Windows 10/11 x64 zařídí vše `install.bat`. Potřebuje jen `winget` (ověř `winget --version`, jinak nainstaluj **App Installer** z Microsoft Store).

1. Rozbal `giro-<verze>.zip` (v Průzkumníku pravým tlačítkem **Extrahovat vše**).
2. Ve složce `giro-<verze>` spusť dvojklikem `install.bat` (nebo ho spusť z `cmd` či PowerShellu).

Instalátor:

1. ověří součty v `SHA256SUMS`,
2. doinstaluje chybějící `git`, `uv`, `gh` a Node.js přes `winget` a harnessy `claude` a `codex` přes `npm`,
3. když git nemá jméno nebo e-mail pro commity, zeptá se na ně,
4. nainstaluje nástroj `giro` přes `uv tool install` s verzemi závislostí z `constraints.txt` a přidá adresář nástrojů uv na PATH,
5. na počítači bez knihovny naklonuje výchozí týmovou knihovnu (`giro library clone --seed-fallback`, viz [Výchozí knihovna](#/guide/instalace/vychozi-knihovna)) a pak knihovnu obnoví na semínko instalované verze (`giro library seed`).

Instalace přes `winget` si může vyžádat potvrzení správce. Opakované spuštění je bezpečné: přítomné nástroje znovu neinstaluje. Nakonec se přihlas tam, kde ještě nejsi (`gh auth login`, `gh auth setup-git`, `claude`, `codex login`), a otevři nový terminál, aby se načetl nový PATH.

## Výchozí knihovna

Instalátor (`install.sh` i `install.bat`) na počítači, který ještě knihovnu nemá, naklonuje výchozí týmovou knihovnu [HAIFA-LIBRARY](https://github.com/janbkrejci/HAIFA-LIBRARY) (veřejné repo, větev `main`). Firemní instalace nastaví jinou knihovnu proměnnou `GIRO_LIBRARY_URL` (celá git URL) v prostředí nebo v `$GIRO_HOME/env`, podobně jako `GIRO_UPDATE_REPO` pro vydání.

Při chybě klonování vznikne lokální knihovna s varováním. Před pozdějším `giro library clone` uchovej místní knihovnu včetně neodeslaných změn. Nedestruktivní `giro library seed` ponechá týmové úpravy jako `kept`; dirty knihovnu zachová s diagnostikou. Plán zobrazí `giro library seed --dry-run`, vybranou položku nahradí výslovné `--take`. Skill `factory` generuje `giro --skill`; `.factory/` overrides zůstávají.

Změny knihovny se do HAIFA-LIBRARY dostávají jen pull requestem (kapitola [Knihovna a tým](#/guide/knihovna-a-tym)).

## Ověření instalace

```bash
giro --version
giro check
```

`giro --version` vypíše nainstalovanou verzi. `giro check` jen čte a nic nemění: mimo repo zkontroluje počítač a knihovnu, v repu navíc repo. Každé zjištění má kód, závažnost (`error`, `warning`, `info`) a radu, co udělat. Dokud kontrola hlásí `error`, tasky nespouštěj. Co dělat, když kontrola hlásí chybu, najdeš v kapitole [Řešení problémů](#/guide/aktualizace-a-reseni-problemu/reseni-problemu). Dotazy na hosting a přihlášení harnessů vynecháš přes `giro check --offline`.

Když shell `giro` nenajde, spusť `uv tool update-shell` a otevři nový terminál.

Dashboard spustíš příkazem `giro obs` (kapitola [První běh](#/guide/prvni-beh)), novější verzi nainstaluješ přes `giro upgrade giro-<verze>.zip` (kapitola [Aktualizace a řešení problémů](#/guide/aktualizace-a-reseni-problemu)).

## Odinstalace

Ve složce rozbaleného balíčku spusť `uninstall.bat` (Windows) nebo `./uninstall.sh` (macOS, Linux, WSL). Skript odinstaluje nástroj `giro` a zeptá se, jestli smazat i domovský adresář GIRO (`~/.config/giro`, jinde podle proměnné `GIRO_HOME`) s nastavením počítače, knihovnou a registrem repozitářů. Bez ptaní ho smaže přepínač `-Purge` (`--purge`), ponechá `-KeepData` (`--keep-data`). Neodeslané změny knihovny se smazáním ztratí, proto nejdřív spusť `giro library push`.

Bez balíčku stačí `uv tool uninstall aifactory`. Závislosti (git, uv, gh, Node.js, harnessy), konfigurace repozitářů (`.factory/`) a backlog zůstávají.

Ze starší HAIFA přejdi nejprve na poslední HAIFA s alertem „HAIFA se přejmenovává na GIRO“. Přechodová akce uchová zálohu a obnoví dashboard na stejné adrese. GIRO alert nezobrazuje; aktualizace hledá v novém repo. Offline přechod po zastavení procesů: `giro migrate --confirm --haifa-bundle /cesta/haifa-H.zip`. Návrat vyžaduje zastavení zápisů a obnovu všech cest i softwaru z ověřené zálohy podle `docs/rebranding/release.md`; marker neobcházej.

`factory` a `HAIFA_*` jsou kompatibilní aliasy `giro` a `GIRO_*`. Zachované technické názvy: `.factory/`, `factory/backlog/`, distribuce `aifactory`, `skill/factory`, HAIFA-LIBRARY. Storage klíče zůstávají při stejném originu. Migrační zálohy se nemažou; purge označeného home je zakázán, použij `--keep-data` / `-KeepData`.

## Licence

GIRO je pod licencí MIT. Licence převzatých částí jsou v souboru `THIRD_PARTY_NOTICES`.
