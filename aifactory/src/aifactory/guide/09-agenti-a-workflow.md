# Agenti a workflow

## Agenti

Agent je pojmenované nastavení modelu pro jednu roli: účel, harness, model, úroveň thinking, nástroje a cesty, které smí měnit. Výchozí agenti ze semínka:

| Agent | Úloha |
| --- | --- |
| planner | Z tasku napíše krátký plán pro buildera. |
| scout | Jen čte a hlásí, kde co v repu je. |
| builder | Implementuje plán nebo task; opravuje a přepracovává. |
| tester | Vybere kontroly, které ověří změnu; nic nemění. |
| test-reviewer | Posoudí plán testů, než se spustí; nic nemění. |
| reviewer | Ověří, že postavené odpovídá zadání; nic nemění. |
| documenter | Popíše dokončenou změnu. |

Agent z knihovny je složka s `agent.yaml` (výchozí harness, model, thinking, `writes`) a prompty `system.md` a `user.md`. Vlastní prompty repa jsou v `.factory/prompts/<agent>/`.

## Roster: agents.yaml

`.factory/agents.yaml` určuje, kteří agenti v repu pracují a s jakým harnessem a modelem:

```yaml
defaults:
  harness: claude
agents:
  - name: builder
    purpose: Implement the plan exactly; report every changed file.
    harness: claude
    model: claude-opus-5-5
    thinking: medium
  - name: reviewer
    purpose: Confirm that what was built is what was asked for; change nothing.
    harness: codex
    model: gpt-6.1-sol
    thinking: high
    writes: []
```

Pole agenta:

- `name`, `purpose`: jméno a účel (účel jde do promptu),
- `harness`: `claude`, `codex` nebo `pi`; vždy explicitně, nikdy se neodvozuje z modelu,
- `model`, `thinking`: model a úroveň přemýšlení (`off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, `ultra`; co model podporuje, závisí na harnessu),
- `tools`: povolené nástroje,
- `writes`: cesty, které smí agent měnit; bez pole bez omezení (v rámci tasku), `[]` jen pro čtení,
- `disallowed_commands`: zakázané příkazy (vynutí jen harness claude),
- `skills`: skilly, které agent dostane; `harness_engineering` jen pro pi.

Agenti z knihovny, které roster nevyjmenuje, se zdědí. Položka rosteru jen s vazbami (harness, model, thinking) přepíše výchozí hodnoty agenta z knihovny.

Celý roster přepneš předvolbou `factory config roster set claude` nebo `factory config roster set codex`; jednoho agenta přes `factory config roster set --agent reviewer --harness codex --model …`. Změnu commitni (`factory config commit`).

## Odkud se bere harness a model

Od nejslabšího po nejsilnější:

1. roster repa (`agents.yaml`),
2. výchozí harness, model a thinking tohoto počítače (dialog **Harnessy tohoto počítače**),
3. `harness`, `model`, `thinking` tasku, nebo zděděné z projektu,
4. volba jen pro jeden běh (dialog **Spustit task**, `factory task run --harness … --model … --thinking …`),
5. přepis na kroku workflow.

Úrovně 2 až 4 platí pro **všechny** agenty běhu. Přepis na kroku workflow má přednost před vším; tak může jedno workflow kombinovat harnessy. Vypnutý harness, nebo harness, jehož výchozí model neprošel testem, běh odmítne.

## Workflow

Workflow je YAML se jménem, popisem, kroky a podmínkou přijetí (`accept`). Vestavěná workflow:

| Workflow | Co dělá |
| --- | --- |
| `build` | Implementace jedním tahem a commit, bez testů a review. |
| `build-test` | Implementace, opravy do zelených testů, commit jen zeleného kódu. |
| `build-review` | Implementace a review s přepracováním. |
| `build-test-review` | Implementace, testy s opravami, review s přepracováním; bez samostatného plánu. Pro tasky s přesným zadáním. |
| `plan` | Jen plán k přečtení člověkem. |
| `plan-build` | Plán, implementace, commit bez testů. |
| `plan-build-test` | Plán, implementace, opravy do zelených testů. |
| `plan-build-test-quality` | Navíc lint, typová kontrola, build a testy celého repa. |
| `simple-sdlc` | Plán, implementace, testy, review, dokumentace; každý výstup zvlášť commitnutý. Pro velké nebo vágní tasky. |
| `scout` | Jen průzkum repa, nic nemění. |
| `document` | Dokumentace hotové změny. |
| `quality` | Lint, typová kontrola, build a testy celého repa beze změn. |
| `heal` | Celá sada testů a opravy, dokud není zelená. |
| `resolve`, `resolve-reviewed` | Vyřešení konfliktu PR s base (používá Review a auto-merge). |

Vlastní workflow ulož do `.factory/workflows/<jméno>.yaml` repa, nebo do knihovny. Ověříš ho přes `factory workflow check .factory/workflows/<jméno>.yaml`.

## Kroky workflow

**Kroky agentů** (role z registru rolí):

| Krok | Agent | Účel |
| --- | --- | --- |
| `plan` | planner | Plán. |
| `scout` | scout | Průzkum. |
| `build` | builder | Implementace. |
| `fix` | builder | Oprava podle selhaných testů. |
| `revise` | builder | Přepracování podle review. |
| `ask` | builder | Přímá odpověď na požadavek, bez pevného tvaru výstupu. |
| `resolve` | builder | Vyřešení konfliktu. |
| `test_plan` | tester | Výběr kontrol. |
| `test_review` | test-reviewer | Posouzení plánu testů. |
| `review` | reviewer | Review. |
| `document` | documenter | Dokumentace. |

Krok agenta může mít `agent` (jiný agent), `harness`, `model`, `thinking`, `when`, `id`, `description` a `input` (výstupy kterých kroků dostane).

**Kódové kroky** (bez modelu): `test` (spustí kontroly vybrané testerem, všechny i po prvním selhání), `commit`, `changes` (diff celého běhu pro dokumentaci), `command` (vlastní příkaz: `id`, `argv`, `timeout`), `rebase` a `rebuild` (přegenerování souborů z `generated`).

**Smyčky a podmínky:**

- `repeat: {max: N, until: podmínka}` s vnořenými `steps` opakuje kroky; `until` se vyhodnocuje po každém kroku a smyčka hned končí,
- `when: podmínka` krok přeskočí, když neplatí,
- `accept: podmínka` rozhodne, zda běh uspěl.

Podmínky čtou pole výstupů kroků, například `test.passed`, `review.approved` nebo `rebase.conflict`, a umějí `and`, `or`, `not` a porovnání. Nikdy se nevyhodnocují jako kód.

Příklad (zkrácené `build-test-review`):

```yaml
name: build-test-review
description: Build, test with repairs, review with revision
steps:
  - build
  - test_plan
  - repeat: {max: 3, until: test.passed}
    steps:
      - test
      - fix
      - test_plan
  - repeat: {max: 2, until: review.approved}
    steps:
      - review:
          input: [build, fix, revise]
      - revise
  - commit:
      when: test.passed and review.approved
accept: test.passed and review.approved
```

## Výběr workflow pro task

- Malá a přesně zadaná změna: `build-test-review`.
- Velká nebo vágní změna: `simple-sdlc`, nebo nejdřív `plan` a plán si přečti.
- Rychlá oprava bez rizika: `build-test`.
- Zjištění stavu bez změn: `scout`, `quality`.

Ve formuláři tasku pomůže tlačítko **Navrhnout workflow**.

## Role: roles.yaml

`.factory/roles.yaml` přepisuje, který agent vykonává který krok. Nech v něm jen role, které měníš; úplná kopie vestavěného registru (`roles_full_copy`) by tě odstřihla od jeho budoucích změn.

## Instrukce a skilly repa

Agenti používají `CLAUDE.md`, `AGENTS.md` a skilly repa tak, jak je jejich harness načte při spuštění v repu. Zdroj skillů je `.claude/skills/<jméno>/`; `.agents/skills/` je jeho kopie pro codex a pi, kterou udržuje `factory skills sync`. Osobní a globální konfigurace (tvoje `~/.claude`, `~/.codex`…) se do běhu nedostane tam, kde to harness umí; jinak to hlásí `factory check`. Proměnné `CLAUDE_SAFE_MODE=1`, `CODEX_SAFE_MODE=1` a `PI_SAFE_MODE=1` zapnou úplnou izolaci, bez instrukcí a skillů repa.
