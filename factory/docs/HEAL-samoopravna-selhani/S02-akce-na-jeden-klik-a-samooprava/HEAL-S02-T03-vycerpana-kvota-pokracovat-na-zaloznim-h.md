# HEAL-S02-T03: Vyčerpaná kvóta: pokračovat na záložním harnessu

## Co se změnilo

Běh, kterému harness ohlásí vyčerpanou kvótu, může pokračovat na jiném harnessu: sám
podle nastavené zálohy, nebo po volbě operátora.

### Záloha v konfiguraci

```yaml
# .factory/agents.yaml
defaults:
  harness: codex
  model: gpt-6.1-sol
  fallback:
    harness: claude
    model: claude-opus-5-5   # volitelné, stejně jako thinking
agents:
  - name: builder
    fallback: {harness: pi, model: anthropic/claude-sonnet}   # jen pro buildera
```

```yaml
# .factory/local.yaml (jen tento počítač, má přednost)
fallback:
  harness: claude
```

Pořadí přednosti: `local.yaml`, pak `fallback` agenta, jehož harness kvótu ohlásil, pak
`defaults.fallback`. Přepíná se celý běh (všichni agenti), protože kvóta patří účtu
harnessu.

### Automatické přepnutí

- Po selhání `quota` factory jednou spustí retry se zálohou (`run/fallback.py`). Agenti
  dostanou `## Continuation` s řádkem o přepnutí a novou session.
- Retry, který harness už přepnul, znovu nepřepíná. Záloha na harness, kterému kvóta
  došla, se nezkouší (varování v CLI). Když selže i záloha, běh skončí selháním `quota`.
- Když retry nejde spustit (např. base nejde stáhnout), běh zůstane selhaný s `quota` a
  CLI vypíše varování.

### Ruční přepnutí

- CLI: `factory task retry ID --harness claude [--model …] [--thinking …]`.
- Dashboard: karta „Vyčerpaná kvóta“ má tlačítko **Pokračovat s jiným harnessem**. Nabídne
  jen harnessy povolené na tomto počítači s otestovaným modelem
  (`GET /api/runs/{id}/harness-choices`) a spustí `POST /api/runs/{id}/retry` s `{harness}`.

### Kde je přepnutí vidět

- Detail běhu, řádek pokusu: „přepnuto codex/gpt-6.1-sol → claude/claude-opus-5-5 (kvóta,
  automaticky)“.
- `task_runs.retries[].harness_switch` (`factory task runs ID --json`).
- Událost fáze `request` daného pokusu (`harness_switch`).
- Popis PR, sekce `### Přepnutí harnessu`. Poznámka běhu nese nový přepis rosteru.

## Testy

- `tests/run/test_quota_fallback.py` (fake harnessy):
  - codex vrátí kvótu, záložní claude doběhne: běh je úspěšný, přepnutí je v `retries`,
    v událostech, v poznámce i v PR a záložní agent dostal `## Continuation`,
  - bez zálohy se nepřepíná a běh zůstane selhaný s `quota`,
  - selže i záloha: jen jeden pokus, ruční retry pak běží na záloze a zpět nepřepne,
  - `factory task retry --harness` zapíše ruční přepnutí a PR body ho vypíše,
  - přednost `local.yaml` před agentem a `defaults`.
- `tests/web/test_web_harness_switch.py`: nabídka harnessů (povolené, otestované, bez
  vyčerpaného) a retry jen s nabízeným harnessem.
- `web/src/components/runs/FailureCard.test.ts`, `RunDetail.test.ts`: tlačítko, výběr a
  POST, prázdná nabídka, řádek pokusu s přepnutím.
