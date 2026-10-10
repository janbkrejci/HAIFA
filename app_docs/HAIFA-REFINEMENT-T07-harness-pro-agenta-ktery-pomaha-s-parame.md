# Harness a model pro návrh parametrů tasku

Agent „Navrhnout parametry tasku“ dřív nabízel jen agenty z rosteru repa. Typicky šlo jen o codex. Teď uživatel vybírá jakýkoli povolený harness počítače a jeho model, nebo nechá systémový default.

## Co změna dělá

1. **Výběr v UI** (`aifactory/web/src/components/backlog/TaskAdvice.vue`) má dva selecty:
   - „Harness pro návrh“. První volba je „Systémový default (harness · model)“, za ní následují povolené harnessy.
   - „Model pro návrh“. Zobrazí se jen po výběru harnessu. Volba „Default harnessu (…)“ vezme model z nastavení počítače, za ní jsou modely z katalogu harnessu. Změna harnessu model vynuluje.
   - Výběr se ukládá jako JSON `{harness, model}` do `localStorage` pod klíčem `haifa.task-advice.choice.<repo>` (dřív `haifa.task-advice.agent.<repo>`). Uložený harness nebo model, který už není nabízený, se zahodí.
   - Když není ani default, ani žádný povolený harness, místo selectů se zobrazí hláška a tlačítko je neaktivní.
2. **Nabídka** (`AdviceManager.options` v `aifactory/src/aifactory/web/workflow_advice.py`) bere data z `harness_settings.catalog(haifa_home())`. Vrací harnessy z `HARNESSES`, které jsou v nastavení počítače povolené a mají dostupné CLI, i s jejich `default_model` a `models`. `default` je to, co by se použilo bez výběru, nebo `null`.
3. **Rozlišení harnessu** (`_resolve` ve stejném souboru) zkusí explicitní výběr přes `effective_override`, tedy stejný mechanismus jako běh tasku. Ten bere i výchozí harness a model počítače. Pokud nastavení harnessů neexistuje, použije harness a model agenta role `plan` z rosteru. Chyba nastavení (např. vypnutý harness) se vrací jako `UsageError`.
4. **Spuštění** (`AdviceManager.start`): s `task_parameters` přijímá místo `agent` klíče `harness` a `model`. Ověří, že harness je nabízený a že model patří k vybranému harnessu. Výsledek uloží do `ctx["advisor"]`. Provider pro zobrazení ceny se čte z `ctx["advisor"]`, ne z rosteru.
5. **Běh agenta** (`recommend` v `aifactory/src/aifactory/workflow/adaptive.py`): pro návrh parametrů tasku se na roster aplikuje `ctx["advisor"]` přes `apply_agents_override`. Vždy běží agent role `plan`, jen s přepsaným harnessem a modelem. Návrh workflow (bez `task_parameters`) dál používá `effective_override(ctx["effective"])`.

## API

`GET /api/backlog/task-advice/options`:

```json
{
  "default": {"harness": "claude", "model": "sonnet"},
  "harnesses": [{"name": "codex", "default_model": "gpt-5.5", "models": ["gpt-5.5"]}]
}
```

`POST /api/backlog/task-advice` přijímá `task_id`, `draft` a volitelně `harness` a `model`. 400 vrátí:

- nenabízený harness,
- model bez harnessu nebo mimo jeho seznam,
- hodnota, která není řetězec,
- starý klíč `agent`.

## Ověření

- `cd aifactory && uv run pytest tests/web/test_web_task_advice.py -n0`. Testy `test_repeat_select_cost_and_save` a `test_advisor_defaults` pokrývají výběr, odmítnutí neplatných kombinací a fallback na roster.
- `just web-test` spustí `TaskAdvice.test.ts`: odeslání výběru, reset modelu při změně harnessu, hlášku bez harnessů, obnovení a zahození uloženého výběru. Upravený je i `FactoryView.test.ts`.
- Ručně: `just dash`, otevřít formulář tasku, ověřit nabídku harnessů a spustit návrh s defaultem i s explicitním modelem.

Statický frontend v `aifactory/src/aifactory/web/static/` je přebuildovaný (`just web-build`).
