---
id: HAIFA-S01-T43
title: Návrh ze záměru sám zvolí projekt a step
status: todo
workflow: build-test-review
depends_on: [HAIFA-S01-T42]
writes: [aifactory/src/aifactory/workflow/propose.py, aifactory/src/aifactory/workflow/propose_check.py, aifactory/src/aifactory/seed/agents/proposer/, aifactory/src/aifactory/cli.py, aifactory/src/aifactory/skill/skill.md, aifactory/src/aifactory/skill/codes.py, aifactory/tests/workflow/test_backlog_propose.py, aifactory/tests/workflow/test_propose_check.py, aifactory/tests/intent_fixture.py, aifactory/tests/skill/]
---

## Zadání
## Zadání

`factory backlog propose` dnes vyžaduje `--project` nebo `--step`. Bez obou přepínačů nově navrhne i umístění. Agent `proposer` rozhodne, jestli tasky patří do existujícího stepu, do nového stepu existujícího projektu, nebo do nového projektu s novým stepem.

1. `aifactory/src/aifactory/workflow/propose.py`:
   - `Target()` bez projektu i stepu znamená automatické umístění. `_check_target` ho povolí. Kombinace projektu i stepu zůstává chybou.
   - `context()` v tomto režimu pošle `target: {"kind": "auto"}` a `target_container: null`. Ke každému projektu a stepu v `containers` přidá oříznuté tělo (`_clip`), pokud se vejde pod `_CONTEXT_LIMIT`. Jinak těla vynechá a zapíše poznámku do `context_notes`.
   - `BacklogProposalOutput` dostane volitelná pole:
     - `project: ProposedProject | null` (code, title, body) pro nový projekt,
     - `existing_project: str | null`,
     - `existing_step: str | null`,
     - `placement_reason: str` (jedna věta, proč právě sem).
   - Pravidla v režimu auto: právě jedno z `existing_step` a `step`. U nového `step` právě jedno z `existing_project` a `project`. Id musí existovat a mít správnou úroveň. V backlogu bez úrovně projektu je nový projekt chyba a nový step bez projektu je mimo rozsah (smí se jen `existing_step`).
   - V režimech `--project` a `--step` jsou nová pole `null`, jinak `invalid_value` jako dnes u `step`.
   - Nová funkce `resolve(proposal, target)` vrátí skutečné umístění. Používají ji `plan` (volá `add_batch` z HAIFA-S01-T42 i s novým projektem), `_step_id`, `candidates`, `review` a `to_json`.
   - `to_json` přidá `project: {id, title, body, path, new}`, `placement_reason` a `target` (vyřešené umístění: `{project, step}`).
   - `refinement_prompt` v režimu auto řekne agentovi, že na pokyn z připomínky smí umístění změnit (např. „dej to do HAIFA-S03“).
   - `format_preview` ukáže nad stepem řádek projektu (nový/existující) a důvod umístění.
2. `aifactory/src/aifactory/seed/agents/proposer/system.md` doplní pravidla pro režim auto:
   - přednost má existující step, jehož cíl záměr pokrývá, potom nový step v projektu, kam záměr věcně patří,
   - nový projekt jen tehdy, když záměr nepatří do žádného projektu,
   - nepoužívat kódy, které už existují,
   - vždy vyplnit `placement_reason`.
3. `aifactory/src/aifactory/cli.py`: `--project` a `--step` jsou nepovinné a vzájemně výlučné. Bez nich se umístí automaticky. Uprav help a description. `aifactory/src/aifactory/skill/skill.md` popíše automatické umístění a nová pole JSON výstupu. Případné nové kódy chyb patří do `aifactory/src/aifactory/skill/codes.py`.

Mimo rozsah: dashboard (`web/`), knihovna v domově uživatele (semínko se do ní dostane běžnou cestou).

Hotovo znamená:
- `aifactory/tests/workflow/test_backlog_propose.py` s fake harnessem pokrývá všechny tři výsledky automatického umístění a jejich zápis s `--apply`:
  - existující step,
  - nový step existujícího projektu,
  - nový projekt se stepem.
- Test pokrývá odmítnutí neplatného umístění: oba nebo žádný z `existing_step`/`step`, neznámé id, nový projekt v backlogu bez úrovně projektu, nová pole v režimu `--step`.
- Test ověřuje, že `--project` a `--step` fungují jako dřív.
- `factory backlog propose "…" --json` bez přepínačů vrátí `data.project`, `data.step`, `data.target` a `data.placement_reason`.
- `just lint`, `just typecheck` a `just pytest tests/workflow/ tests/backlog/` projdou, plus dotčené testy `skill` a `library/test_library_seed.py`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
