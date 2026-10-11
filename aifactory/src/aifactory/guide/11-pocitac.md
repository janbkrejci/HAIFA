# Počítač a harnessy

## Domovský adresář HAIFA

Nastavení tohoto počítače je v domovském adresáři HAIFA: `$HAIFA_HOME`, jinak `$XDG_CONFIG_HOME/haifa`, jinak `~/.config/haifa`.

| Soubor | Obsah |
| --- | --- |
| `env` | Proměnné prostředí `KLÍČ=hodnota` pro HAIFA a harnessy. Načte se při startu a nepřepíše proměnné, které už jsou nastavené. Práva musí být `600`. |
| `dashboard.yaml` | Registr dashboardu: port a zaregistrovaná repa. |
| `harnesses.json` | Výchozí harness a pro každý harness zapnutí, model a thinking. |
| `harness-tests.json` | Výsledky testů harnessů. |
| `library/` | Knihovna (jiná cesta přes `HAIFA_LIBRARY`). |
| `logs/` | Výstupy běhů spuštěných z dashboardu. |
| `test_slots/` | Zámky slotů pro kroky testů. |
| `database.yaml` | Adresa sdíleného databázového serveru (`url`). |

Data běhů (trace DB, sessions, worktree) jsou v repu pod `.factory/` a do gitu nejdou.

## Harnessy tohoto počítače

Dialog otevřeš kliknutím na **Harnessy** v horní liště. Volby platí pro všechna repa na tomto počítači; projekt, task a volba pro jeden běh je mohou přepsat (kapitola [Agenti a workflow](#/guide/agenti-a-workflow/odkud-se-bere-harness-a-model)).

Pro každý harness (claude, codex, pi):

- přepínač **Zapnutý** / **Vypnutý**: vypnutý harness běhy nepoužijí,
- **Výchozí harness**: který harness dostanou agenti, když nic jiného neurčí,
- **Výchozí model** a **Výchozí thinking level**,
- **Test**: krátký dotaz na model. Harness, jehož test selhal, nejde použít jako výchozí a v liště limitů se nezobrazí.

**Uložit nastavení** zapíše volby do `harnesses.json`.

Instalace a přihlášení harnessů:

| Harness | CLI | Přihlášení | Poznámka |
| --- | --- | --- | --- |
| Claude Code | `claude` | `claude auth login` | Jediný vynutí `disallowed_commands` agenta. |
| Codex | `codex` | `codex login` | |
| pi | `pi` | `pi auth login` | Potřebuje Node.js; modely z `pi --list-models`. |

CLI, které není na PATH, nastavíš proměnnou `CLAUDE_CODE_PATH`, `CODEX_PATH` nebo `PI_PATH`.

## Limity předplatného

Lišta **Harnessy** v horní liště ukazuje pro každý harness pětihodinové a týdenní okno a kolik procent zbývá. Hodnoty jsou ty, které harness sám vrátil při posledním běhu; dashboard se nikam neptá. „nedostupné“ znamená, že harness zatím nic nehlásil; pi limity nehlásí.

## Proměnné prostředí

Nastav je v shellu, nebo v `$HAIFA_HOME/env`. Ty, které mění chování harnessů, ohlásí `factory check` jako `env_override`.

| Proměnná | Účel |
| --- | --- |
| `HAIFA_HOME` | Jiný domovský adresář HAIFA. |
| `HAIFA_LIBRARY` | Jiná cesta ke knihovně. |
| `HAIFA_DASH_HOST` | Adresa, na které naslouchá dashboard (výchozí `127.0.0.1`). |
| `HAIFA_DATABASE_URL` | Sdílený databázový server. |
| `HAIFA_UPDATE_REPO` | GitHub repo s vydáními HAIFA (výchozí `janbkrejci/HAIFA`). |
| `CLAUDE_SAFE_MODE`, `CODEX_SAFE_MODE`, `PI_SAFE_MODE` | `1` = úplná izolace harnessu, bez instrukcí a skillů repa. |
| `CLAUDE_PERMISSION_MODE` | Režim oprávnění Claude Code (výchozí `bypassPermissions`). |
| `CLAUDE_MCP_CONFIG` | Konfigurace MCP serverů pro Claude Code (výchozí žádné MCP). |
| `CODEX_SANDBOX` | Sandbox Codexu: `read-only`, `workspace-write` nebo `danger-full-access`; prázdné = bez sandboxu. |
| `CODEX_HOME`, `PI_CODING_AGENT_DIR` | Domovské adresáře Codexu a pi. |
| `CLAUDE_CODE_PATH`, `CODEX_PATH`, `PI_PATH` | Cesta k CLI harnessu. |
| `AZURE_DEVOPS_EXT_PAT` | Token pro Azure DevOps místo `az login`. |

## Přístupové klíče

Tokeny a klíče patří do `$HAIFA_HOME/env` (s právy `600`, jinak `env_file_mode`) nebo do lokálního `.env` mimo git, nikdy do `.factory/` ani do backlogu. HAIFA tokeny do konfigurace neukládá; remote knihovny ukládá bez jména a hesla.

## Sdílená databáze

Běhy, trace, metadata PR a backlog jsou standardně v lokální SQLite v repu. Tým je může sdílet přes databázový server HAIFA. Spustíš ho zvlášť od dashboardu, ze zdrojů HAIFA:

```bash
just shared-db --data-dir ./team-db --host 0.0.0.0 --port 4710
```

nebo z nainstalovaného balíčku `python -m aifactory.database.server --data-dir ./team-db --host 0.0.0.0 --port 4710` (Python z prostředí nástroje uv). Bez `--host` naslouchá jen na `127.0.0.1`. Server je **bez přihlašování**: kdokoli, kdo na něj dosáhne, může data číst i měnit. Provozuj ho jen v důvěryhodné síti, případně za reverzní proxy s HTTPS. Adresář `--data-dir` zálohuj.

Připojení (od nejsilnějšího): `database_url` v `.factory/local.yaml` repa, proměnná `HAIFA_DATABASE_URL`, `url` v `$HAIFA_HOME/database.yaml`. Adresa nesmí obsahovat jméno a heslo. Po změně restartuj dashboard.

```yaml
url: http://db-host:4710
```

Projekty se spárují podle síťového remote repa (`origin`); různé lokální cesty nevadí, repo bez síťového remote sdílet nejde. Starší lokální běhy se do nové databáze nepřenesou. Před prvním připojením commitni lokální změny backlogu.

Agentní procesy a worktree zůstávají na počítači, který běh spustil. Pauzu a pokračování jde požádat z jiného počítače, zastavení jen z původního. Při souběžné úpravě stejného souboru backlogu dostaneš `remote_backlog_conflict`: odlož svou úpravu, načti aktuální backlog a aplikuj ji znovu. Task neodstraňuj smazáním souboru, ale `status: cancelled`.

## Dashboard v síti

`factory obs --host 0.0.0.0` nebo `HAIFA_DASH_HOST=0.0.0.0` zpřístupní dashboard celé síti **bez přihlášení**. Port nastavíš na stránce **Tento počítač** (platí po restartu), nebo `factory obs --port N`.
