---
id: HAIFA-S05-T05
title: Harnessy načítají instrukce a skilly repa nativně
status: done
workflow: simple-sdlc
depends_on: [HAIFA-S05-T01]
---

## Zadání
Agenti factory mají používat instrukce a skilly repa nativně, jako by harness běžel z CLI v repu: CLAUDE.md, AGENTS.md a skilly repa. Osobní a globální konfigurace operátora (`~/.claude`, `~/.codex`, `~/.pi/agent`, `~/.agents`) se do běhu nedostane, kde to harness umí. Dnes claude běží s `--safe-mode` (vypne CLAUDE.md, skilly, hooky, pluginy i MCP), codex s `project_doc_max_bytes=0` (nečte AGENTS.md) a pi izolovaně. Skill repa má zdroj v `.claude/skills/<jméno>/` (čte ho claude) a kopii v `.agents/skills/<jméno>/` (čte ji codex a pi), bez symlinků (rozhodnutí Skilly v repu v `docs/decisions.md`).

Where: `aifactory/src/aifactory/engine/agent_cc.py`, `aifactory/src/aifactory/harness/codex.py`, `aifactory/src/aifactory/engine/agent_pi.py`, `factory check`, nový příkaz `factory skills sync` v `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/harness/` (`harness_fakes.py`) a `aifactory/tests/`.

Done means:
- claude: místo `--safe-mode` načte nastavení, CLAUDE.md a skilly jen z repa (například `--setting-sources project,local`, přesný mechanismus podle `claude --help`). MCP zůstávají vypnuté (`--strict-mcp-config`). Hooky, pluginy, skilly ani CLAUDE.md z `~/.claude` operátora se nenačtou.
- codex: čte AGENTS.md a `.agents/skills/` repa (`project_doc_max_bytes=0` se nenastavuje). Co z globální konfigurace operátora vyloučit nejde (například `~/.codex/AGENTS.md`), nahlásí `factory check` jako varování.
- pi: čte AGENTS.md, CLAUDE.md a `.agents/skills/` repa a v běhu bez obsluhy mu factory udělí důvěru v projekt, aby projektové skilly načetl. Osobní rozšíření, prompt templates a skilly z `~/.pi/agent` a `~/.agents` se nenačtou, pokud to pi umí. Co vyloučit nejde, nahlásí `factory check`.
- System prompt agenta (`--system-prompt`, `developer_instructions`) zůstává zdrojem role agenta. Instrukce repa přidá harness svým nativním mechanismem.
- `factory skills sync` zapíše `.agents/skills/` jako přesnou kopii `.claude/skills/` (nové, změněné i smazané skilly). `factory check` nahlásí skill, který v `.agents/skills/` chybí, se liší nebo tam zbyl navíc.
- `CLAUDE_SAFE_MODE=1`, `CODEX_SAFE_MODE=1` a `PI_SAFE_MODE=1` vrátí úplnou izolaci jako dnes. Výchozí je nativní načítání repa.
- `factory --skill` popisuje nativní načítání instrukcí a skillů repa, zrcadlo `.agents/skills/` a přepínače `*_SAFE_MODE`. Nové kódy jsou v `skill/codes.py`.
- Testy s falešným harnessem (FakePopen z `tests/harness/harness_fakes.py`): argv claude, codex a pi ve výchozím režimu i s `*_SAFE_MODE=1`, důvěra v projekt u pi, `factory skills sync` a hlášení rozdílu v `factory check`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: přiřazování skillů jednotlivým agentům v `.factory/` (`skills:`, `.factory/skills/`, rejstřík skillů v promptu), rozšíření pi z `.factory/`, instalace skillů z knihovny, dashboard, ověření proti skutečným CLI.

Pevná omezení:
- Každá změna logiky v `aifactory/src/aifactory/engine/` má značku `# aifactory` jako dnešní úpravy (`# aifactory 2.9:`).
- HAIFA nezapisuje do `~/.claude`, `~/.codex`, `~/.agents` ani `~/.pi/agent`.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/45 · náklady $4.32
