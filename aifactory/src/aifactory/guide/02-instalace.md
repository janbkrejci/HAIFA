# Instalace

Instalační příručka HAIFA (Helios AI Factory): co musí být na počítači, jak nainstalovat nástroj `factory` z distribučního balíčku `haifa-<verze>.zip` a jak instalaci ověřit. Stejný text je v balíčku jako `INSTALL.md` a v dashboardu jako kapitola **Instalace** příručky (ikona knihy v horní liště).

Přístup ke zdrojovému repu HAIFA nepotřebuješ. Balíček obsahuje wheel `aifactory`, přesné verze závislostí (`constraints.txt`), instalační skript `install.sh`, tento návod, licence převzatých částí a kontrolní součty `SHA256SUMS`.

## Co budeš potřebovat

- **Systém:** macOS, Linux, Windows přes WSL, nebo Windows 10/11 x64 nativně (bez WSL, s Git Bash z Git for Windows).
- **Git** s nastaveným jménem a e-mailem pro commity.
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** a Python 3.11 nebo novější. uv instaluje a aktualizuje nástroj `factory`.
- **Bash, `curl` a `unzip`** pro instalaci (na Windows Git Bash a PowerShell).
- **CLI hostingu** podle toho, kde máš repa: [GitHub CLI](https://github.com/cli/cli#installation) (`gh`) pro GitHub, Azure CLI `az` s rozšířením `azure-devops` pro Azure DevOps. Pro čistě lokální repa (provider `local`) žádné CLI nepotřebuješ.
- **Alespoň jeden harness**, tedy CLI agenta, nainstalovaný a přihlášený: [Claude Code](https://code.claude.com/docs/en/setup) (`claude`), [Codex CLI](https://github.com/openai/codex) (`codex`) nebo [pi](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent) (`pi`, potřebuje Node.js).
- **just**, pokud tvoje repa spouštějí testy přes `justfile`.

Co chybí, ti po instalaci ukáže `factory check` a v dashboardu stránka **Tento počítač**.

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

Skript ověří součty v `SHA256SUMS` a nainstaluje nástroj `factory` přes `uv tool install` s verzemi závislostí z `constraints.txt` do samostatného prostředí uv. `uv tool update-shell` přidá adresář nástrojů uv na PATH; pak otevři nový terminál.

## Windows bez WSL

Postup je pro Windows 10/11 x64 a PowerShell. Git Bash z Git for Windows spouští instalační skript, HAIFA i Python běží nativně.

1. Ověř `winget --version` (jinak nainstaluj **App Installer** z Microsoft Store) a nainstaluj nástroje příkazy z bloku pod tímto seznamem. Ponech výchozí cestu Gitu `C:\Program Files\Git` a pak otevři nový PowerShell.
2. Dej Git Bash na PATH před systémový `bash.exe`, nainstaluj Python, nastav identitu a přihlas se (druhý blok). `bash --version` musí ukázat Git Bash, ne WSL.
3. Nainstaluj a přihlas harness, například `winget install --id Anthropic.ClaudeCode --exact --source winget`, pak v novém PowerShellu `claude`.
4. Rozbal balíček a spusť instalaci (třetí blok).

```powershell
winget install --id Git.Git --exact --source winget
winget install --id GitHub.cli --exact --source winget
winget install --id astral-sh.uv --exact --source winget
```

```powershell
$env:Path = "$env:ProgramFiles\Git\bin;$env:Path"
uv python install 3.12
git config --global user.name "Tvoje jméno"
git config --global user.email "tvuj@email.cz"
gh auth login
gh auth setup-git
```

```powershell
Expand-Archive -Path haifa-<verze>.zip -DestinationPath .\haifa-install
Set-Location .\haifa-install\haifa-<verze>
$env:Path = "$env:ProgramFiles\Git\bin;$env:Path"
& "$env:ProgramFiles\Git\bin\bash.exe" ./install.sh
if ($LASTEXITCODE -ne 0) { throw "Instalace HAIFA selhala." }
uv tool update-shell
```

Otevři nový PowerShell. Řádek `$env:Path = "$env:ProgramFiles\Git\bin;$env:Path"` opakuj v každém novém PowerShellu, než spustíš `factory`.

## Ověření instalace

```bash
factory --version
factory check
```

`factory --version` vypíše nainstalovanou verzi. `factory check` jen čte a nic nemění: mimo repo zkontroluje počítač a knihovnu, v repu navíc repo. Každé zjištění má kód, závažnost (`error`, `warning`, `info`) a radu, co udělat. Dokud kontrola hlásí `error`, tasky nespouštěj. Kódy a jejich opravy jsou v kapitole [Řešení problémů](#/guide/reseni-problemu). Dotazy na hosting a přihlášení harnessů vynecháš přes `factory check --offline`.

Když shell `factory` nenajde, spusť `uv tool update-shell` a otevři nový terminál. Na nativních Windows kontrola zatím hlásí také `unsupported_platform` (zná jen macOS, Linux a WSL); ostatní zjištění platí.

## Spuštění dashboardu

```bash
factory obs
```

Otevře dashboard na `http://127.0.0.1:4700` (jiný port: `factory obs --port 4710`). Terminál nech otevřený, `Ctrl+C` server zastaví. Konkrétní repo rovnou zaregistruješ přes `factory obs --repo ~/cesta/k/repu`.

Další kroky (knihovna, harnessy, první repo a první task) popisuje kapitola [První spuštění](#/guide/prvni-spusteni).

## Aktualizace

Chip v horní liště dashboardu ukáže, že je k dispozici novější vydání; kliknutím ho dashboard stáhne, ověří, nainstaluje a restartuje se. Ručně z balíčku nebo `https` URL:

```bash
factory upgrade haifa-<verze>.zip
```

Podrobnosti v kapitole [Aktualizace a vydání](#/guide/aktualizace).

## Odinstalace

```bash
uv tool uninstall aifactory
```

Nastavení počítače, knihovna a registr repozitářů zůstanou v domovském adresáři HAIFA (`~/.config/haifa`, jinde podle proměnné `HAIFA_HOME`); smaž ho, pokud je už nepotřebuješ. Konfigurace repozitářů (`.factory/`) a backlog zůstávají v repech.

## Licence

HAIFA je pod licencí MIT. Licence převzatých částí jsou v souboru `THIRD_PARTY_NOTICES`.
