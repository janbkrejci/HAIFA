# Co je GIRO

Goal in. Release out.

GIRO je lokální dashboard a nástroj `giro`, který pouští kódovací agenty (Claude Code, Codex, pi) na tasky z backlogu v tvých Git repech. **Hledat v příručce** hledá ve všech kapitolách, i bez diakritiky.

## Jak GIRO funguje <!-- section:jak-haifa-funguje -->

1. **Backlog** je strom markdown souborů v repu (`factory/backlog/<projekt>/<step>/<task>.md`) se zadáními a parametry tasků.
2. **Běh** založí tasku worktree a větev a provede jeho **workflow**: role agentů (planner, builder, tester, reviewer…) a kódové kroky (testy, commit).
3. **Pull request** je výsledek. Schválíš ho, vrátíš s poznámkou, nebo se mergne sám.
4. **Konfigurace** je v `.factory/` a běhy ji čtou z commitu ve větvi **base** (typicky `main`). Co repo nemá, dědí ze sdílené **knihovny**.

**Harness** je CLI, přes které běží model (`claude`, `codex`, `pi`). **Domovský adresář GIRO** je `~/.config/giro` (jinde `GIRO_HOME`).

## Bezpečnost

- Dashboard naslouchá jen na `127.0.0.1`; `--host 0.0.0.0` ho zpřístupní síti bez přihlášení.
- Agent smí měnit jen povolené cesty tasku ve svém worktree, jiný zápis GIRO vrátí. `.factory/` běh nemění.
- Klíče patří do `$GIRO_HOME/env` (práva `600`) nebo lokálního `.env`, nikdy do gitu.
- Tvoje osobní konfigurace harnessů se do běhu nedostane; kde to harness neumí, upozorní `giro check`.

## Příkazová řádka

Vše z dashboardu umí i `giro`: přehled vypíše `giro --help`, podrobnosti `giro <příkaz> --help`. Příkazy pracují s repem v aktuálním adresáři, jiné určí `--repo CESTA`. S `--json` vrací obálku `{ok, data, error, warnings}` s kódy chyb. Návod pro agenty vypíše `giro --skill`. Nejčastější příkazy:

- `giro check`: kontrola počítače, knihovny a repa,
- `giro obs`: dashboard,
- `giro task list`, `giro task add STEP TITLE`: tasky,
- `giro task run ID`, `giro task retry ID`: spuštění a navázání běhu,
- `giro task approve ID`, `giro task return ID --note TEXT`: schválení a vrácení,
- `giro backlog commit`, `giro config commit`: commit backlogu a konfigurace do base.
