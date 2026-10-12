# HAIFA — Helios AI Factory

HAIFA je lokální dashboard a CLI `factory` pro agentní úkoly ve více Git repozitářích. Backlog je v markdownu v repu, každý běh úkolu má vlastní worktree a větev, provede workflow agentů (build, testy, review) a skončí pull requestem, který schválíš nebo se mergne sám. Modely spouští přes přihlášené CLI harnessy Claude Code, Codex nebo pi.

## Prerekvizity

- macOS, Linux nebo Windows 10/11 (nativně, bez WSL). Na Windows stačí `winget`, ostatní doinstaluje instalátor.
- Git s nastaveným jménem a e-mailem.
- [GitHub CLI (`gh`)](https://github.com/cli/cli#installation) přihlášené k účtu s právem zápisu do tvých repozitářů.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) a Python 3.11 nebo novější.
- Bash, `curl` a `unzip` pro instalaci na macOS a Linuxu.
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

1. Z [posledního vydání](https://github.com/janbkrejci/HAIFA/releases/latest) stáhni `haifa-<verze>.zip` a rozbal ho (v Průzkumníku pravým tlačítkem **Extrahovat vše**).
2. Ve složce `haifa-<verze>` spusť dvojklikem `install.bat`.

Instalátor ověří SHA-256 součty, doinstaluje chybějící `git`, `uv`, `gh` a Node.js přes `winget` a harnessy `claude` a `codex` přes `npm`, zeptá se na jméno a e-mail pro git, pokud chybí, nainstaluje `factory` s připnutými závislostmi a založí knihovnu ze semínka. Instalace přes `winget` si může vyžádat potvrzení správce. Opakované spuštění je bezpečné.

Pak se přihlas tam, kde ještě nejsi, a v novém terminálu spusť dashboard:

```powershell
gh auth login
gh auth setup-git
claude
codex login
factory check
factory obs
```

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

## Odinstalace

Ve složce rozbaleného vydání spusť `uninstall.bat` (Windows) nebo `bash uninstall.sh` (macOS a Linux). Skript odinstaluje `factory` a zeptá se, jestli smazat i `~/.config/haifa` s knihovnou a nastavením. Neodeslané změny knihovny nejdřív pošli přes `factory library push`. Bez rozbaleného vydání stačí `uv tool uninstall aifactory`.

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
