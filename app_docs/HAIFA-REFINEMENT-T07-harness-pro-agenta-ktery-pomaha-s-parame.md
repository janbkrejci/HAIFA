# Harness a model pro návrh parametrů tasku

Blok „Navrhnout parametry tasku“ ve formuláři tasku nabízí dva výběry:

1. **Harness pro návrh**: první volba je „Systémový default (harness · model)“, dál každý harness (claude, codex, pi), který je povolený v nastavení harnessů počítače (`$HAIFA_HOME/harnesses.json`) a má nainstalované CLI.
2. **Model pro návrh**: zobrazí se jen po výběru harnessu. První volba „Default harnessu (model)“ vezme model z nastavení počítače, dál následují modely harnessu z katalogu.

Návrh vždy spouští agenta role `plan` z rosteru repa (jeho prompty zůstávají), jen mu přepíše harness a model stejným mechanismem jako běh tasku (`effective_override` + `apply_agents_override`). Bez nastavení harnessů počítače a bez výběru se použije harness a model agenta role `plan` z rosteru.

Poslední výběr se pamatuje v prohlížeči pod klíčem `haifa.task-advice.choice.<repo>`. Uložený harness, který už není nabízený, se zahodí.

Návrh workflow (`WorkflowAdvice`) se nemění.

## API

`GET /api/backlog/task-advice/options`:

```json
{
  "default": {"harness": "claude", "model": "sonnet"},
  "harnesses": [{"name": "codex", "default_model": "gpt-5.5", "models": ["gpt-5.5"]}]
}
```

`default` je `null`, když se nedá určit žádný harness.

`POST /api/backlog/task-advice` přijímá `task_id`, `draft` a volitelně `harness` a `model`. Neznámý harness, model mimo seznam harnessu, model bez harnessu nebo starý klíč `agent` vrací 400.
