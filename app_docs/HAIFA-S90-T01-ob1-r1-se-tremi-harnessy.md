# HAIFA-S90-T01 — OB1: R1 se třemi harnessy

R1 je ověřený: jeden workflow `simple-sdlc` běžel na GitHubu přes claude, codex i pi
a `R1.json` má `outcome: passed`.

## Roster `aifactory/validation/rosters/claude-codex-pi/`

| agent | harness | model | proč |
|---|---|---|---|
| planner | claude | sonnet | jako šablona |
| builder | codex | gpt-5.5 | jako šablona (build, fix, revise) |
| reviewer | pi | `nous-portal-api-key/meituan/longcat-2.5-preview:free` | model vybraný v OB5 (roster `pi-longcat`) |
| documenter | claude | haiku | jako šablona |

`workflows/simple-sdlc.yaml` je workflow šablony beze změny kroků, jen s jiným
hlavičkovým komentářem. Příklad je v `aifactory/validation/README.md`.

## Oprava validace: roster platí i při počítačovém nastavení harnessů

První lokální běh R1 selhal (`document: codex (want claude)`) a ve stejném místě
selhala i samotná šablona. Příčina: `~/.config/haifa/harnesses.json` (počítačová
volba harnessů, `default_harness: codex`) přepisuje harness a model všech agentů
rosteru (`harness/settings.py::effective_override`). Validace tak neověřovala roster:
všechny agenty běžely na `gpt-6.1-sol` a documenter na codexu.

`validation/runner.py::isolated_haifa_home` teď každému běhu validace dá vlastní
`HAIFA_HOME` ve workdiru. Ten zrcadlí skutečný domov symlinky (`env`, `library`,
`logs` …, na Windows bez oprávnění k symlinkům kopie), jen bez `harnesses.json`
a `harness-tests.json`. O harnessu a modelu každého agenta tak rozhoduje jen roster.
Úklid workdiru symlinky nesleduje (`shutil.rmtree`), skutečný domov zůstane netknutý.
Produkt (`aifactory/src/`) se nemění. Testy:
`tests/validation/test_validation_unit.py::test_isolated_haifa_home_*`.
`runner.main` po běhu vrátí `HAIFA_HOME` na původní hodnotu.

Celá sada `just check` při testu tasku odhalila dva testy závislé na prostředí, ne na této změně:

- `tests/check/test_factory_check_system.py`: omezený PATH bral celý adresář gitu.
  Na Homebrew v něm leží i `uv`, takže chyběl nález `uv_missing`. Na PATH je teď jen
  symlink na samotný `git`.
- `tests/web/test_web_overview.py::test_slow_repo_times_out_and_the_others_answer`:
  limit 0,3 s nestačil rychlému repu při zatížené sadě (12 workerů xdist). Mimo Windows
  jsou meze teď 1,0 / 3,0 / 2,5 s (limit, spánek pomalého repa, mez odpovědi).

## Běh

```
HAIFA_SANDBOX_REPO=janbkrejci/haifa-sandbox \
  just validate --remote github --roster aifactory/validation/rosters/claude-codex-pi
```

`HAIFA_SANDBOX_REPO` nebyl nastavený v shellu, v `.env` ani v HAIFA home. Použil
jsem sandbox `janbkrejci/haifa-sandbox` („throwaway repo for validation runs“),
base `haifa-validate/20261009-192521`. Preflight prošel: `gh` přihlášený,
`factory harness check` kód 0 (claude, codex, pi), model longcat je v `pi --list-models`.

Výsledky: `aifactory/validation/results/2026-10-09/github-192521/`
(trace/ a logs/ git ignoruje).

| scénář | výsledek |
|---|---|
| R1 | passed |
| R10 | passed |
| R2 | passed |
| RESOLVE | passed |
| R3 | passed |
| R4 | passed |
| R5 | passed |
| B1 | passed |
| F2 | failed |

F2 selhal v kontrole `auto_chain`: `run_failed: accept not met` u řetězu
`M04-S01-T02 → M04-S01-T03`. Reviewer na pi (longcat) zamítl i ve druhém kole,
takže `accept` (`test.passed and review.approved`) neplatil. Jde o chování modelu
revieweru, ne o R1. Pro tento task to není podmínka, ale stojí za samostatný task.

### R1: `harness_per_phase` a měření

Fáze: `request → plan → commit_plan → build → test_1 → review_1 → revise_1 →
review_2 → retest → commit_build → changes → document → commit_docs`.

| fáze | harness | tokeny |
|---|---|---|
| plan | claude | 52 634 |
| build | codex | 85 133 |
| review_1 | pi (zamítl) | 15 370 |
| revise_1 | codex | 78 374 |
| review_2 | pi (schválil) | 67 000 |
| document | claude | 58 502 |

Celkem 357 013 tokenů, cena v trace 0,092 USD, běh R1 286 s.

## Řádek pro `docs/decisions.md`

`docs/decisions.md` není v povolených cestách tasku. Operátor vloží do tabulky tento řádek:

| OB1 R1 se třemi harnessy | 2026-10-09 | `aifactory/validation/results/2026-10-09/github-192521`, roster `claude-codex-pi`: R1 `passed` (plan claude, build a revise codex, review pi, document claude). R1 je ověřený. R10, R2, RESOLVE, R3, R4, R5 a B1 `passed`. F2 `failed` (`auto_chain`: reviewer pi longcat zamítl i ve druhém kole). Validace teď běží s vlastním `HAIFA_HOME` bez `harnesses.json`, aby roster nepřepsala počítačová volba harnessů. |

## Úklid na GitHubu

V `janbkrejci/haifa-sandbox` jsou zavřené PR #59 a #62, které po běhu zůstaly otevřené.
Smazané jsou hlavové větve všech deseti PR tohoto běhu (`factory/*-…`, `factory-sync/5`)
a base `haifa-validate/20261009-192521`. Starší PR a větve z dřívějších běhů zůstaly beze změny.
