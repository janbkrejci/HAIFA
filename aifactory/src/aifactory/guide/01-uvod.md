# Co je HAIFA

HAIFA (Helios AI Factory) je lokální dashboard a nástroj `factory`, který pouští kódovací agenty (Claude Code, Codex, pi) na tasky z backlogu v tvých Git repech. Pole **Hledat v příručce** hledá ve všech kapitolách bez ohledu na diakritiku.

## Jak HAIFA funguje

1. **Backlog** je strom markdown souborů v repu (`factory/backlog/<projekt>/<step>/<task>.md`) se zadáními a parametry tasků.
2. **Běh** založí tasku worktree a větev a provede jeho **workflow**: role agentů (planner, builder, tester, reviewer…) a kódové kroky (testy, commit).
3. **Pull request** je výsledek. Schválíš ho, vrátíš s poznámkou, nebo se mergne sám.
4. **Konfigurace** je v `.factory/` a běhy ji čtou z commitu ve větvi **base** (typicky `main`). Co repo nemá, dědí ze sdílené **knihovny**.

**Harness** je CLI, přes které běží model (`claude`, `codex`, `pi`). **Domovský adresář HAIFA** je `~/.config/haifa` (jinde `HAIFA_HOME`).

## Bezpečnost

- Dashboard naslouchá jen na `127.0.0.1`; `--host 0.0.0.0` ho zpřístupní síti bez přihlášení.
- Agent smí měnit jen povolené cesty tasku ve svém worktree, jiný zápis HAIFA vrátí. `.factory/` běh nemění.
- Klíče patří do `$HAIFA_HOME/env` (práva `600`) nebo lokálního `.env`, nikdy do gitu.
- Tvoje osobní konfigurace harnessů se do běhu nedostane; kde to harness neumí, upozorní `factory check`.

## Příkazová řádka

Vše z dashboardu umí i `factory`: přehled vypíše `factory --help`, podrobnosti `factory <příkaz> --help`. Příkazy pracují s repem v aktuálním adresáři, jiné určí `--repo CESTA`. S `--json` vrací obálku `{ok, data, error, warnings}` s kódy chyb. Návod pro agenty vypíše `factory --skill`. Nejčastější příkazy:

- `factory check`: kontrola počítače, knihovny a repa,
- `factory obs`: dashboard,
- `factory task list`, `factory task add STEP TITLE`: tasky,
- `factory task run ID`, `factory task retry ID`: spuštění a navázání běhu,
- `factory task approve ID`, `factory task return ID --note TEXT`: schválení a vrácení,
- `factory backlog commit`, `factory config commit`: commit backlogu a konfigurace do base.
