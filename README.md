# HAIFA — Helios AI Factory

HAIFA je lokální dashboard a CLI `factory` pro práci s agentními úkoly ve více Git repozitářích. Spravuje projekty, backlog, workflow, modely a běhy agentů, jejich testy, review a pull requesty. Dashboard běží na tvém počítači; modely spouští přes přihlášené CLI harnessy Claude Code, Codex nebo pi.

## Prerekvizity

Pro běžnou instalaci potřebuješ:

- macOS, Linux nebo Windows 10/11 (nativně, bez WSL; postup níže).
- Bash, `curl` a `unzip` pro instalaci.
- Git s nastaveným jménem a e-mailem pro vytváření commitů.
- [GitHub CLI (`gh`)](https://github.com/cli/cli#installation), přihlášené k účtu s přístupem k repozitářům, ve kterých chceš pracovat. Workflow vytvářející PR potřebují GitHub remote a právo zapisovat.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) a Python 3.11 nebo novější. Python lze nainstalovat pomocí uv, viz níže.
- [just](https://github.com/casey/just#installation), který používají výchozí příkazy pro testování projektů.
- Alespoň jeden nainstalovaný a přihlášený harness s přístupem k modelu. Jeho používání může vyžadovat předplatné nebo API kredit.
- Internet pro stažení závislostí, práci s GitHubem, modely a aktualizacemi.

Na macOS s [Homebrew](https://brew.sh/) nainstaluj nástroje:

```bash
brew install git gh uv just
uv python install 3.12
```

Na Linuxu nainstaluj nástroje balíčkovým správcem distribuce, například na Ubuntu 24.04 nebo novějším:

```bash
sudo apt update
sudo apt install git bash curl unzip gh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Otevři nový terminál. Potom nainstaluj Python a `just` (balíček `rust-just` uvádí [oficiální návod just](https://just.systems/man/en/packages.html)):

```bash
uv python install 3.12
uv tool install rust-just
uv tool update-shell
```

Otevři nový terminál, aby měl `just` na PATH. Na jiných distribucích postupuj podle odkazu na instalaci GitHub CLI výše.

Nastav identitu pro commity a přihlas GitHub CLI; dosaď své údaje:

```bash
git config --global user.name "Tvoje jméno"
git config --global user.email "tvuj@email.cz"
gh auth login
gh auth setup-git
```

Například [Claude Code](https://code.claude.com/docs/en/setup) na macOS/Linux/WSL nainstaluješ a přihlásíš takto:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Otevři nový terminál a spusť `claude`, dokonči přihlášení a ověř, že dokáže odpovědět. Alternativou jsou [Codex CLI](https://github.com/openai/codex) nebo [pi](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent); postup instalace a přihlášení je v jejich dokumentaci. Pro HAIFA nemusíš instalovat všechny tři.

## Windows bez WSL: od čistého systému po dashboard

Následující postup je pro Windows 10/11 x64 a běžný **PowerShell**. HAIFA i Python běží nativně ve Windows. Git Bash z Git for Windows slouží k instalačnímu skriptu a receptům `just`; WSL ani Linux neinstaluj.

### 1. Nainstaluj nástroje

Otevři PowerShell a ověř `winget --version`. Pokud příkaz chybí, nainstaluj nebo aktualizuj **App Installer** z Microsoft Store podle [návodu Microsoftu](https://learn.microsoft.com/en-us/windows/package-manager/winget/). Potom spusť:

```powershell
winget install --id Git.Git --exact --source winget
winget install --id GitHub.cli --exact --source winget
winget install --id astral-sh.uv --exact --source winget
```

Instalátor Gitu může požádat o oprávnění správce. Ponech výchozí cestu `C:\Program Files\Git` a zpřístupnění Gitu pro příkazovou řádku. Zavři PowerShell a otevři nový, aby načetl PATH.

V tomto terminálu dej Git Bash před systémový launcher `bash.exe`. Pokud jsi Git instaloval jinam, uprav první řádek:

```powershell
$gitBashBin = "$env:ProgramFiles\Git\bin"
if (-not (Test-Path "$gitBashBin\bash.exe")) { throw "Uprav cestu ke Git Bash." }
$env:Path = "$gitBashBin;$env:Path"

uv python install 3.12
uv tool install rust-just
uv tool update-shell
```

Zavři PowerShell a otevři nový. Ověř nástroje a nastav svou identitu a GitHub přihlášení:

```powershell
$env:Path = "$env:ProgramFiles\Git\bin;$env:Path"
git --version
gh --version
uv --version
just --version
bash --version

git config --global user.name "Tvoje jméno"
git config --global user.email "tvuj@email.cz"
gh auth login
gh auth setup-git
```

`bash --version` musí ukázat Git Bash; pokud se pokusí spustit WSL, zkontroluj pořadí PATH.

### 2. Nainstaluj a přihlas harness

Například nativní [Claude Code pro Windows](https://code.claude.com/docs/en/setup#install-on-native-windows):

```powershell
winget install --id Anthropic.ClaudeCode --exact --source winget
```

Otevři nový PowerShell, spusť `claude --version` a potom `claude`. Dokonči přihlášení a ověř odpověď. Git Bash už je nainstalovaný z předchozího kroku. Claude z WinGet aktualizuješ přes `winget upgrade --id Anthropic.ClaudeCode --exact`.

Stačí jeden funkční harness; ostatní můžeš v dashboardu vypnout. Node.js ani Bun nejsou pro tuto instalaci HAIFA a nativního Claude potřeba.

### 3. Stáhni a nainstaluj aktuální ZIP

V PowerShellu přejdi do složky, kam chceš balíček stáhnout. Tyto příkazy vyberou instalační ZIP posledního stabilního vydání, rozbalí ho a spustí dodaný skript přes Git Bash:

```powershell
$haifaRelease = Invoke-RestMethod "https://api.github.com/repos/janbkrejci/HAIFA/releases/latest"
$haifaVersion = $haifaRelease.tag_name -replace '^v', ''
$haifaZipName = "haifa-$haifaVersion.zip"
$haifaAsset = $haifaRelease.assets | Where-Object { $_.name -eq $haifaZipName }
if (-not $haifaAsset) { throw "Vydání neobsahuje instalační ZIP." }
Invoke-WebRequest -UseBasicParsing $haifaAsset.browser_download_url -OutFile $haifaZipName
Expand-Archive -Path $haifaZipName -DestinationPath ".\haifa-install-$haifaVersion"
Set-Location ".\haifa-install-$haifaVersion\haifa-$haifaVersion"
& "$env:ProgramFiles\Git\bin\bash.exe" ./install.sh
if ($LASTEXITCODE -ne 0) { throw "Instalace HAIFA selhala." }
uv tool update-shell
```

Instalační skript ověří SHA-256 součty a nainstaluje `factory` s připnutými závislostmi do izolovaného prostředí uv. Otevři nový PowerShell a spusť:

```powershell
$env:Path = "$env:ProgramFiles\Git\bin;$env:Path"
factory --version
factory check
factory obs
```

Dashboard běží na <http://127.0.0.1:4700>. Terminál nech otevřený; `Ctrl+C` server zastaví. Při každém spuštění v novém PowerShellu nejdřív přidej Git Bash na PATH řádkem výše a pak spusť `factory obs`. Pokračuj sekcí **První spuštění** níže. Výsledek `factory check` může před prvním nastavením hlásit chybějící knihovnu nebo konfiguraci; dokonči průvodce v dashboardu.

Pokud příkaz není nalezený, znovu spusť `uv tool update-shell` a otevři nový terminál. Nastavení počítače najdeš ve `%USERPROFILE%\.haifa`. Projekty mohou mít vlastní prerekvizity podle použitého jazyka a testovacího příkazu.

## Instalace z distribučního ZIPu na macOS/Linux

Z nejnovějšího vydání tohoto repozitáře na GitHubu stáhni soubor `haifa-<verze>.zip`. Rozbal jej a spusť instalační skript; v příkladu dosaď skutečnou verzi:

```bash
unzip haifa-0.1.0.zip
cd haifa-0.1.0
bash install.sh
uv tool update-shell
```

Otevři nový terminál. Instalační skript ověřuje SHA-256 součty souborů a instaluje `factory` s připnutými závislostmi do samostatného prostředí uv. Bun ani zdrojové repo pro tuto instalaci nepotřebuješ.

```bash
factory --version
factory check
factory obs
```

Dashboard otevře prohlížeč na <http://127.0.0.1:4700>. Terminál se serverem nech otevřený; `Ctrl+C` jej zastaví. Další spuštění je opět `factory obs`. Jiný port lze zvolit příkazem `factory obs --port 4710`.

## První spuštění

1. V dashboardu dokonči nastavení počítače a inicializaci knihovny podle průvodce.
2. Klikni na oblast harnessů v horní liště. Povol harness, vyber výchozí model a thinking level a spusť **Test**. Funkční harness můžeš označit jako výchozí pro tento počítač. Projekty a tasky toto nastavení dědí, dokud si nezvolíš vlastní.
3. Na přehledu přidej lokální Git repozitář. Pokud obsahuje starší instalaci factory/SSSF, dashboard upozorní na její nahrazení; při instalaci odstraní původní instalaci a změny commitne.
4. Přidej projekt a úkol, zvol workflow a spusť běh. Testovací příkaz projektu musí odpovídat jeho nástrojům; například výchozí `just check` potřebuje odpovídající recept v jeho `justfile`.

Horní lišta ukazuje kontrolu systému. **Nalezeny problémy** otevře seznam problémů s tlačítky pro řešení; kliknutí na **Systém v pořádku** kontrolu zopakuje. Přehled zůstává viditelný.

Konfigurace počítače, knihovna a seznam repozitářů jsou v `~/.haifa` (lze změnit proměnnou `HAIFA_HOME`). Přihlášení spravují jednotlivé harnessy. Repo konfigurace patří do `.factory/` a musí být commitnutá, aby ji běhy používaly. Přístupové klíče ukládej do lokálních `.env`, nikoli do Git historie.

## Aktualizace

Chip vlevo od kontroly systému zobrazuje serverovou kontrolu nových stabilních vydání. **Systém je aktuální** a **Nepodařilo se zkontrolovat aktualizace** po kliknutí spustí novou kontrolu. **Je k dispozici aktualizace** stáhne instalační ZIP, ověří součty i verzi, nainstaluje jej a restartuje dashboard. Po restartu server automaticky spustí čerstvou kontrolu systému a UI načte její výsledek. Kontroly běží na pozadí serveru; reload stránky znovu nespouští systémové sondy ani objevování harnessů.

Aktualizace vyžaduje dokončení aktivních tasků a dostupné `uv` na PATH. Během instalace jsou zápisy z dashboardu pozastavené. Neúspěšná instalace zobrazí chybu a dashboard nerestartuje. Ruční instalace staženého vydání je také možná:

```bash
factory upgrade /cesta/haifa-<verze>.zip
```

Automatická instalace je určená pro distribuční instalaci přes `uv tool`. Vývojový checkout aktualizuj pomocí Gitu a příkazů níže.

## Spuštění ze zdrojů a vývoj

Na Windows používej také Git Bash na PATH podle postupu výše. Pro vývoj frontendu nainstaluj Bun v PowerShellu podle [oficiálního návodu](https://bun.com/docs/installation) příkazem `powershell -c "irm bun.sh/install.ps1|iex"` a otevři nový terminál.

Navíc potřebuješ [Bun](https://bun.com/docs/installation) pro frontend. Naklonuj tento repozitář, přejdi do jeho kořene a spusť:

```bash
uv sync --project aifactory
just web-build
just dash
```

Pro vývoj frontendu nech dashboard běžet a ve druhém terminálu spusť `just web-dev`; Vite běží na <http://127.0.0.1:4701> a API směruje na dashboard. Po změně backendu dashboard restartuj. Aktualizace zdrojové instalace:

```bash
git pull --ff-only
uv sync --project aifactory
just web-build
```

Před `git pull` zastav běžící tasky a dashboard; poté jej spusť znovu přes `just dash`.

Python zdroje jsou v `aifactory/src/aifactory/`, testy v `aifactory/tests/`, Vue/TypeScript frontend v `aifactory/web/` a distribuční nástroje v `aifactory/bundle/`.

```bash
just check          # frontend, pytest, mypy, Ruff
just e2e-install    # Chromium, pokud nemáš systémový Chrome
just e2e            # browser acceptance testy
just bundle         # aifactory/dist/haifa-<verze>.zip
```

Licence převzatých částí jsou v [THIRD_PARTY_NOTICES](aifactory/THIRD_PARTY_NOTICES).

## Vydávání buildů

[GitHub Actions](.github/workflows/ci.yml) při změně `main` nejdřív spustí frontendové, backendové a browserové testy, typovou kontrolu a lint. Ve veřejném repozitáři po úspěšném ověření bundle testů a čisté nativní instalace na Windows také sestaví distribuční ZIP, ověří čistou instalaci a zveřejní GitHub Release včetně ZIPu. Neúspěšná pipeline aktualizaci nezveřejní; pull requesty pouze testuje.

Verze buildu je `<major>.<minor>.<číslo běhu pipeline>`, například `0.1.42`. Stejná verze je ve wheelu, tagu `v0.1.42` a souboru `haifa-0.1.42.zip`. Opakování téhož běhu již vydaný build nepřepisuje. Zdroj aktualizací se při sestavení nastaví na repozitář, kde pipeline běží. Aktualizační chip porovnává tuto verzi s nainstalovanou; nový úspěšný build tedy rozpozná i bez ručního zvýšení verze ve zdrojích.
