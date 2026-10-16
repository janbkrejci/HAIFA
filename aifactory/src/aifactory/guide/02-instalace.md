# Instalace

Instalační příručka HAIFA (Helios AI Factory): co musí být na počítači, jak nainstalovat nástroj `factory` z distribučního balíčku `haifa-<verze>.zip` a jak instalaci ověřit. Stejný text je v balíčku jako `INSTALL.md` a v dashboardu jako kapitola **Instalace** příručky (ikona knihy v horní liště).

Přístup ke zdrojovému repu HAIFA nepotřebuješ. Balíček obsahuje wheel `aifactory`, přesné verze závislostí (`constraints.txt`), instalační skripty `install.sh` (macOS, Linux, WSL) a `install.bat` s `install.ps1` (Windows), odinstalační skripty `uninstall.sh` a `uninstall.bat` s `uninstall.ps1`, tento návod, licence převzatých částí a kontrolní součty `SHA256SUMS`.

## Co budeš potřebovat

- **Systém:** macOS, Linux, Windows přes WSL, nebo Windows 10/11 x64 nativně (bez WSL).
- **Git** s nastaveným jménem a e-mailem pro commity.
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** a Python 3.11 nebo novější. uv instaluje a aktualizuje nástroj `factory`.
- **Bash, `curl` a `unzip`** pro instalaci na macOS a Linuxu. Na Windows stačí `winget`, ostatní doinstaluje `install.bat`.
- **CLI hostingu** podle toho, kde máš repa: [GitHub CLI](https://github.com/cli/cli#installation) (`gh`) pro GitHub, Azure CLI `az` s rozšířením `azure-devops` pro Azure DevOps. Pro čistě lokální repa (provider `local`) žádné CLI nepotřebuješ.
- **Alespoň jeden harness**, tedy CLI agenta, nainstalovaný a přihlášený: [Claude Code](https://code.claude.com/docs/en/setup) (`claude`), [Codex CLI](https://github.com/openai/codex) (`codex`) nebo [pi](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent) (`pi`, potřebuje Node.js).
- **just**, pokud tvoje repa spouštějí testy přes `justfile`.

Co chybí, ti po instalaci ukáže `factory check` a v dashboardu sekce **Kontrola počítače** na stránce **Knihovna**.

## macOS

Nástroje přes [Homebrew](https://brew.sh/):

```bash
brew install git gh uv
uv python install 3.12
```

Pokračuj částí [Identita a přihlášení](#/guide/instalace/identita-a-prihlaseni).

## Linux a WSL

Například Ubuntu 24.04 (ve WSL stejně):

```bash
sudo apt update
sudo apt install git bash curl unzip gh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
```

Pokračuj částí [Identita a přihlášení](#/guide/instalace/identita-a-prihlaseni).

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

Poslední vydání najdeš na [stránce vydání HAIFA](https://github.com/janbkrejci/HAIFA/releases/latest) (soubor `haifa-<verze>.zip`), případně ho dostaneš od správce týmu. Rozbal ho a spusť instalační skript:

```bash
unzip haifa-<verze>.zip
cd haifa-<verze>
./install.sh
uv tool update-shell
```

Skript ověří součty v `SHA256SUMS`, nainstaluje nástroj `factory` přes `uv tool install` s verzemi závislostí z `constraints.txt` do samostatného prostředí uv a připraví a obnoví knihovnu (viz [Výchozí knihovna](#/guide/instalace/vychozi-knihovna)). `uv tool update-shell` přidá adresář nástrojů uv na PATH; pak otevři nový terminál.

## Windows bez WSL

Na Windows 10/11 x64 zařídí vše `install.bat`. Potřebuje jen `winget` (ověř `winget --version`, jinak nainstaluj **App Installer** z Microsoft Store).

1. Rozbal `haifa-<verze>.zip` (v Průzkumníku pravým tlačítkem **Extrahovat vše**).
2. Ve složce `haifa-<verze>` spusť dvojklikem `install.bat` (nebo ho spusť z `cmd` či PowerShellu).

Instalátor:

1. ověří součty v `SHA256SUMS`,
2. doinstaluje chybějící `git`, `uv`, `gh` a Node.js přes `winget` a harnessy `claude` a `codex` přes `npm`,
3. když git nemá jméno nebo e-mail pro commity, zeptá se na ně,
4. nainstaluje nástroj `factory` přes `uv tool install` s verzemi závislostí z `constraints.txt` a přidá adresář nástrojů uv na PATH,
5. na počítači bez knihovny naklonuje výchozí týmovou knihovnu (`factory library clone --seed-fallback`, viz [Výchozí knihovna](#/guide/instalace/vychozi-knihovna)) a pak knihovnu obnoví na semínko instalované verze (`factory library seed --all`).

Instalace přes `winget` si může vyžádat potvrzení správce. Opakované spuštění je bezpečné: přítomné nástroje znovu neinstaluje. Nakonec se přihlas tam, kde ještě nejsi (`gh auth login`, `gh auth setup-git`, `claude`, `codex login`), a otevři nový terminál, aby se načetl nový PATH.

## Výchozí knihovna

Instalátor (`install.sh` i `install.bat`) na počítači, který ještě knihovnu nemá, naklonuje výchozí týmovou knihovnu [HAIFA-LIBRARY](https://github.com/janbkrejci/HAIFA-LIBRARY) (veřejné repo, větev `main`). Firemní instalace nastaví jinou knihovnu proměnnou `HAIFA_LIBRARY_URL` (celá git URL) v prostředí nebo v `$HAIFA_HOME/env`, podobně jako `HAIFA_UPDATE_REPO` pro vydání.

Když se klon nepovede (bez sítě, bez přístupu), instalátor založí lokální knihovnu ze semínka a vypíše varování. Týmovou knihovnu pak naklonuješ později: lokální knihovnu smaž (nebo přesuň) a spusť `factory library clone`. Pak instalátor (nová i existující knihovna) spustí `factory library seed --all`: každou položku semínka v knihovně (agenty, workflow, rozšíření pi a skill `factory`) nahradí verzí z instalované HAIFA, i když ji tým upravil. Položky, které semínko nemá (týmové importy), zůstanou, a repa se nemění: vlastní úpravy patří do `.factory/` repa. Když obnovení selže, instalace doběhne s varováním a obnovíš ji sám přes `factory library seed --all`.

Změny knihovny se do HAIFA-LIBRARY dostávají jen pull requestem (kapitola [Knihovna a tým](#/guide/knihovna-a-tym)).

## Ověření instalace

```bash
factory --version
factory check
```

`factory --version` vypíše nainstalovanou verzi. `factory check` jen čte a nic nemění: mimo repo zkontroluje počítač a knihovnu, v repu navíc repo. Každé zjištění má kód, závažnost (`error`, `warning`, `info`) a radu, co udělat. Dokud kontrola hlásí `error`, tasky nespouštěj. Co dělat, když kontrola hlásí chybu, najdeš v kapitole [Řešení problémů](#/guide/aktualizace-a-reseni-problemu/reseni-problemu). Dotazy na hosting a přihlášení harnessů vynecháš přes `factory check --offline`.

Když shell `factory` nenajde, spusť `uv tool update-shell` a otevři nový terminál.

Dashboard spustíš příkazem `factory obs` (kapitola [První běh](#/guide/prvni-beh)), novější verzi nainstaluješ přes `factory upgrade haifa-<verze>.zip` (kapitola [Aktualizace a řešení problémů](#/guide/aktualizace-a-reseni-problemu)).

## Odinstalace

Ve složce rozbaleného balíčku spusť `uninstall.bat` (Windows) nebo `./uninstall.sh` (macOS, Linux, WSL). Skript odinstaluje nástroj `factory` a zeptá se, jestli smazat i domovský adresář HAIFA (`~/.config/haifa`, jinde podle proměnné `HAIFA_HOME`) s nastavením počítače, knihovnou a registrem repozitářů. Bez ptaní ho smaže přepínač `-Purge` (`--purge`), ponechá `-KeepData` (`--keep-data`). Neodeslané změny knihovny se smazáním ztratí, proto nejdřív spusť `factory library push`.

Bez balíčku stačí `uv tool uninstall aifactory`. Závislosti (git, uv, gh, Node.js, harnessy), konfigurace repozitářů (`.factory/`) a backlog zůstávají.

## Licence

HAIFA je pod licencí MIT. Licence převzatých částí jsou v souboru `THIRD_PARTY_NOTICES`.
