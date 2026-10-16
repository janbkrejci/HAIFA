# HEAL-S02-T03: Vyčerpaná kvóta: pokračovat na záložním harnessu

## Cíl

Běh, kterému harness ohlásí vyčerpanou kvótu (`failure_kind: quota`), nemá skončit, když je
na počítači k dispozici jiný harness.

## Konfigurace

Klíč `fallback: {harness, model?, thinking?}` (`harness/fallback.py`, model `Fallback`):

1. `.factory/local.yaml` `fallback`: tento počítač, platí pro všechny agenty.
2. `.factory/agents.yaml` `fallback` u agenta, jehož harness kvótu ohlásil.
3. `.factory/agents.yaml` `defaults.fallback`.

Platí první nastavený. Bez `model` se použije model počítače pro ten harness
(`harnesses.json`), jinak výchozí model harnessu. Rozhodnutí je v `docs/decisions.md`.

## Chování

- `run_task` i `retry_run` po selhání `quota` zavolají `run/fallback.continue_on_fallback`.
  Když je záloha nastavená a je to jiný harness než ten, kterému kvóta došla, factory
  jednou spustí `retry_run(agents_override=záloha)`: všichni agenti běhu pokračují na
  záložním harnessu od fáze, která selhala.
- Agent s jiným harnessem nebo modelem dostane novou session a `## Continuation` jako
  každý retry, navíc s řádkem o přepnutí harnessu. Session se znovu použije jen při stejném
  harnessu i modelu (`engine/agents._agent_session_id`).
- Retry, který harness přepnul (automaticky nebo operátor), znovu nepřepíná. Selže-li i
  záloha, běh zůstane selhaný s druhem svého selhání (`quota`).
- Retry s přepnutím nahradí přepis rosteru v poznámce běhu, takže další ruční retry
  pokračuje na novém harnessu.

## Viditelnost

- `task_runs.retries[].harness_switch`: `from`, `to` (harness, model, thinking), `reason`
  (druh selhání), `auto`, případně `agent` a `source` (kde je záloha nastavená).
- Událost `log` fáze `request` pokusu s klíčem `harness_switch` (řádek
  `codex/gpt → claude/opus (quota, automaticky, …)`).
- Popis PR: sekce `### Přepnutí harnessu`. Detail běhu: řádek pokusu „přepnuto … (kvóta,
  automaticky)“.

## Ruční přepnutí

- CLI: `factory task retry ID --harness NAME [--model NAME] [--thinking LEVEL]`.
- Dashboard: karta selhání `quota` nabídne **Pokračovat s jiným harnessem**.
  `GET /api/runs/{id}/harness-choices` vrátí harnessy povolené v `harnesses.json`, jejichž
  model prošel testem (`harness-tests.json`), bez harnessu, kterému kvóta došla.
  `POST /api/runs/{id}/retry` s `{harness}` přijme jen harness z této nabídky
  (`invalid_value` jinak) a spustí retry s jeho modelem a thinking.
