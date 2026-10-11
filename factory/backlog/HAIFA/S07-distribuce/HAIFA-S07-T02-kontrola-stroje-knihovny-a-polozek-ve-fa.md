---
id: HAIFA-S07-T02
title: "Kontrola stroje, knihovny a položek ve `factory check`"
status: done
workflow: simple-sdlc
depends_on: [HAIFA-S01-T10, HAIFA-S05-T06, HAIFA-S05-T04, HAIFA-S05-T05, HAIFA-S07-T01, HAIFA-S06-T02]
---

## Zadání
Rozšiř `factory check` tak, aby kolegovi řekl, co na stroji chybí pro HAIFA a jeho repa: nástroje, přihlášení harnessů a hostingu, knihovna, verze HAIFA a prostředí. Mimo repo kontroluje jen stroj a knihovnu. V repu přidá stavy položek a další nálezy konfigurace.

Where: modul kontroly z M6, `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/harness/check.py`, `aifactory/src/aifactory/harness/__init__.py`, `aifactory/src/aifactory/library/` (z L2 až L4), `aifactory/src/aifactory/onboard/` (z O1), `aifactory/src/aifactory/engine/agent_pi.py` (katalog modelů jen ke čtení), `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/` (`tests/harness/test_harness_check_cli.py` jako vzor).

Done means:
- `factory check` mimo git repo vrátí nálezy se `scope` `machine` a `library` místo chyby. Návratové kódy zůstávají 0, 1 a 2.
- Stroj: `unsupported_platform` (jen macOS, Linux a WSL), `git_missing`, `git_identity_missing`, `uv_missing`, `harness_missing` pro harnessy rosteru (mimo repo všechny tři jako `info`), `node_missing` u rosteru s pi a `test_command_missing`, když první prvek testovacího příkazu není na PATH.
- Přihlášení (vynechá `--offline`): `harness_login` z `claude auth status`, `codex login status` a `pi auth check --model <model> --json --no-refresh`, `pi_model_unknown` z katalogu pi, `gh_login` z `gh auth status` a `az_login` z `az account show` podle `git_provider`.
- Instalace a knihovna: `factory_outdated` proti `min_factory_version` knihovny, `library_missing`, `library_dirty`, `library_behind` a `library_unpushed` z posledních refů (bez fetch) a `seed_update_available`.
- Prostředí: `env_file_mode` (`$HAIFA_HOME/env` jiný než 0600), `env_override` pro `CLAUDE_SAFE_MODE`, `CLAUDE_MCP_CONFIG`, `CLAUDE_PERMISSION_MODE`, `CODEX_SAFE_MODE`, `CODEX_SANDBOX` a `PI_SAFE_MODE` a `codex_not_isolated` u rosteru s codexem.
- Repo navíc: nález pro každou položku, která není `synced` (s akcí `update`, `export` nebo `adopt`), `workflow_not_in_repo` (backlog v base jmenuje workflow, které repo s manifestem nemá), `roles_full_copy`, `unknown_thinking` a `sssf_leftover`.
- `factory harness check --config CESTA` načte roster loaderem HAIFA a chyby vrátí jako obálku místo pádu na `prompt_engineering`.
- `factory` bez příkazu vypíše nápovědu a řádek „První spuštění: factory check“.
- `factory --skill` popisuje nálezy a opravy. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) s falešnými binárkami na PATH: mimo repo, každý kód, `--offline` nespustí žádné volání hostingu ani přihlášení, `harness check --config .factory/agents.yaml`, kontrola nezmění repo, knihovnu ani domov.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: instalace nástrojů a přihlašování, fetch, dashboard, `factory upgrade`.

Pevná omezení:
- Kontrola nic nezapisuje.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-06 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/73 · náklady $7.75
