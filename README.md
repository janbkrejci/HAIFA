# HAIFA — Helios AI Factory

HAIFA je lokální dashboard a CLI `factory` pro agentní úkoly ve více Git repozitářích. Backlog je v markdownu v repu, každý běh úkolu má vlastní worktree a větev, provede workflow agentů (build, testy, review) a skončí pull requestem, který schválíš nebo se mergne sám. Modely spouští přes přihlášené CLI harnessy Claude Code, Codex nebo pi.

## Prerekvizity

- macOS, Linux nebo Windows 10/11 (nativně, bez WSL).
- Git s nastaveným jménem a e-mailem.
- [GitHub CLI (`gh`)](https://github.com/cli/cli#installation) přihlášené k účtu s právem zápisu do tvých repozitářů.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) a Python 3.11 nebo novější.
- Bash, `curl` a `unzip` pro instalaci.
- Alespoň jeden nainstalovaný a přihlášený harness: [Claude Code](https://code.claude.com/docs/en/setup), [Codex CLI](https://github.com/openai/codex) nebo [pi](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent).

Co chybí, ukáže po instalaci `factory check`.

## Instalace na macOS a Linuxu

Nástroje na macOS s [Homebrew](https://brew.sh/):

```bash
brew install git gh uv
uv python install 3.12
```

Na Linuxu, například Ubuntu 24.04:

```bash
sudo apt update
sudo apt install git bash curl unzip gh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
```

Identita pro commity a přihlášení GitHub CLI:

```bash
git config --global user.name "Tvoje jméno"
git config --global user.email "tvuj@email.cz"
gh auth login
gh auth setup-git
```

Harness, například Claude Code: `curl -fsSL https://claude.ai/install.sh | bash`, pak v novém terminálu `claude` a dokonči přihlášení.

Z [posledního vydání](https://github.com/janbkrejci/HAIFA/releases/latest) stáhni `haifa-<verze>.zip` a nainstaluj ho:

```bash
unzip haifa-<verze>.zip
cd haifa-<verze>
bash install.sh
uv tool update-shell
```

Skript ověří SHA-256 součty a nainstaluje `factory` s připnutými závislostmi do samostatného prostředí uv. V novém terminálu:

```bash
factory --version
factory check
factory obs
```

## Instalace na Windows bez WSL

Postup je pro Windows 10/11 x64 a PowerShell. Git Bash z Git for Windows spouští instalační skript, HAIFA i Python běží nativně.

1. Ověř `winget --version` (jinak nainstaluj **App Installer** z Microsoft Store) a nainstaluj nástroje:

   ```powershell
   winget install --id Git.Git --exact --source winget
   winget install --id GitHub.cli --exact --source winget
   winget install --id astral-sh.uv --exact --source winget
   ```

   Ponech výchozí cestu Gitu `C:\Program Files\Git`. Otevři nový PowerShell.

2. Dej Git Bash na PATH před systémový `bash.exe`, nainstaluj Python a nastav identitu:

   ```powershell
   $env:Path = "$env:ProgramFiles\Git\bin;$env:Path"
   uv python install 3.12
   git config --global user.name "Tvoje jméno"
   git config --global user.email "tvuj@email.cz"
   gh auth login
   gh auth setup-git
   ```

   `bash --version` musí ukázat Git Bash, ne WSL.

3. Nainstaluj a přihlas harness, například `winget install --id Anthropic.ClaudeCode --exact --source winget`, pak v novém PowerShellu `claude`.

4. Stáhni a nainstaluj poslední vydání:

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

5. V novém PowerShellu:

   ```powershell
   $env:Path = "$env:ProgramFiles\Git\bin;$env:Path"
   factory check
   factory obs
   ```

   Řádek s PATH opakuj v každém novém PowerShellu před `factory obs`.

## První spuštění

`factory obs` otevře dashboard na <http://127.0.0.1:4700> (jiný port: `--port 4710`). Terminál nech otevřený, `Ctrl+C` server zastaví.

1. Dokonči nastavení počítače a založení knihovny podle průvodce.
2. Klikni na harnessy v horní liště, povol harness, vyber model a thinking level a spusť **Test**.
3. Na přehledu přidej lokální Git repozitář. HAIFA do něj nainstaluje `.factory/` a změnu commitne.
4. Přidej projekt, step a task, zvol workflow a spusť běh.

**Nalezeny problémy** v horní liště otevře seznam problémů s návody a tlačítky k řešení.

Nastavení počítače a knihovna jsou v `~/.config/haifa` (jinde podle `HAIFA_HOME`). Konfigurace repa je v `.factory/` a běhy ji čtou z commitu v base, musí tedy být commitnutá. Přístupové klíče patří do lokálního `.env`, ne do gitu.

## Aktualizace

Chip v horní liště ukazuje, zda je k dispozici novější vydání. Kliknutím ho dashboard stáhne, ověří, nainstaluje a restartuje se. Aktualizace čeká na dokončení běžících tasků. Ručně: `factory upgrade /cesta/haifa-<verze>.zip`.

## Vývoj

Navíc potřebuješ [Bun](https://bun.com/docs/installation) a [just](https://github.com/casey/just#installation) (`uv tool install rust-just`). Na Windows používej Git Bash na PATH.

```bash
uv sync --project aifactory
just web-build      # frontend do aifactory/src/aifactory/web/static
just dash           # dashboard ze zdrojů
just web-dev        # Vite na :4701 proti běžícímu `just dash`
just check          # frontend, pytest, mypy, ruff
just e2e            # browserové testy (just e2e-install stáhne Chromium)
just bundle         # aifactory/dist/haifa-<verze>.zip
```

Struktura kódu a konvence jsou v [CLAUDE.md](CLAUDE.md), platná rozhodnutí v [docs/decisions.md](docs/decisions.md). Návod pro agenty, kteří HAIFA ovládají, vypíše `factory --skill`.

[GitHub Actions](.github/workflows/ci.yml) na každém commitu do `main` spustí testy, typovou kontrolu a lint, ověří instalaci na Windows a vydá release `haifa-<major>.<minor>.<číslo běhu>.zip`. Commity jen backlogu nebo `.factory/` CI přeskakuje, pull requesty se jen testují.

## Licence

HAIFA je pod licencí [MIT](LICENSE). Licence převzatých částí jsou v [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).
