---
id: HAIFA-S05-T07
title: "`factory config add`, `set` a `remove`"
status: done
workflow: simple-sdlc
depends_on: [HAIFA-S05-T04, HAIFA-S05-T05, HAIFA-S05-T02, HAIFA-S01-T12]
---

## Zadání
Přidej příkazy, které spravují položky v `.factory/` repa podle knihovny: přidat položku z knihovny se závislostmi, nastavit vazby agenta (harness, model, thinking, tools, writes, color) a odebrat položku. Zápis jde přes plán s digestem do pracovního stromu nebo jedním commitem do base.

Where: `aifactory/src/aifactory/cli.py`, `aifactory/src/aifactory/library/` (z L1, L2 a L4), plán a zveřejnění commitu z M7 a M8, `aifactory/src/aifactory/config/` (`loader.py`, `status.py`), `aifactory/src/aifactory/workflow/` (`parse.py`, `check.py`), `aifactory/src/aifactory/backlog/`, `aifactory/pyproject.toml`, `aifactory/uv.lock`, `aifactory/src/aifactory/skill/` (`skill.md`, `codes.py`), testy v `aifactory/tests/library/`.

Done means:
- `factory config add TYP JMÉNO [--as SLOT] [--harness H] [--model M] [--thinking T] --json` zkopíruje položku z knihovny (bez knihovny ze semínka) a zapíše záznam do manifestu. Uzávěr: workflow přidá agenty svých kroků (role z registru repa nebo `agent:` kroku). Skill se nainstaluje do `.claude/skills/<jméno>/` a zkopíruje do `.agents/skills/<jméno>/` (rozhodnutí Skilly v repu v `docs/decisions.md`). Vazby nového slotu jsou `defaults` položky (`$specs_dir/` a `$docs_dir/` nahrazené z `config.yaml`) přepsané volbami. Obsazený slot s jiným obsahem dá `slot_taken` (oprava `--as`), stejný obsah je no-op.
- `factory config set agent SLOT [--harness] [--model] [--thinking] [--tools] [--writes] [--color] --json` změní jen vazby slotu. Neznámé `thinking` odmítne (`invalid_value`).
- `factory config remove TYP JMÉNO [--prune] --json` odmítne položku, kterou používá zapsané workflow, vazba jiného agenta nebo backlog v base (`in_use`). `--prune` odebere i závislosti, které nikdo jiný nepoužívá.
- `.factory/agents.yaml`, `config.yaml` a `roles.yaml` se upravují round tripem ruamel.yaml (nová běhová závislost s horní mezí), takže komentáře a pořadí klíčů zůstanou.
- Režimy jako `init`: `--dry-run` (plán s digestem), bez volby zápis do pracovního stromu (přijme `--expect DIGEST`, blokuje `run_in_progress`), `--commit [--pr] [--expect DIGEST] [-m TEXT]` jedním commitem cestou z M7. Plán projde `load_config` a preflight všech workflow v repu. Repo bez manifestu odmítne (`not_onboarded`, oprava `factory onboard`).
- `factory --skill` popisuje příkazy. Nové kódy jsou v `skill/codes.py`.
- Testy (pytest) s dočasnou knihovnou a holým remote repa: add workflow s uzávěrem, add agenta do jiného slotu (`--as`), `slot_taken`, add skillu do `.claude/skills/` i `.agents/skills/`, set se zachovanými komentáři, neplatné thinking, remove s `in_use` a `--prune`, `--commit` a `plan_changed`, `run_in_progress`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: export do knihovny a návrat verze (L8), aktualizace (M9), operace ve více repech (L9), dashboard.

Pevná omezení:
- Bez `--commit` nic necommituje.
- `.factory/` repa HAIFA se nemění.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-06 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/71 · náklady $8.20
