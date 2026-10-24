# T72 — Binding nového vlákna AI průvodce

`POST /api/assistant/threads` přijímá `{title?, screen?: {repo?, task?, run?}}`.
Task v registrovaném repozitáři získá zděděné hodnoty přes `harness_values` a binding
počítače přes `context_binding` z T69. Run se dohledá pouze pro čtení v trace DB
repozitáře a použije aktuální task v backlogu, nikoli historické nastavení běhu.
Při uvedení tasku i běhu musí jejich identifikátory souhlasit.

Samotné repo a chybějící, null nebo prázdný screen používají nastavení počítače
z `harnesses.json`. Nerozhodnutý binding používá `guide_defaults()`. Explicitní
binding tasku funguje také bez nastavení počítače. Repo se vždy hledá v registru,
nikoli podle cesty dodané klientem.

Produkční `GUIDE_HARNESSES` zůstává pouze Claude. Codex a pi přecházejí přes
stávající `claude_fallback`, včetně modelu a thinking pro Claude. Chyby nastavení
nebo nedostupný harness vracejí HTTP 409 `harness_unavailable`. Vlákno uloží
harness, model, thinking a session; další zprávy ani restart binding nepřepočítají.

Neznámé klíče, neplatný tvar screen, neznámé repo/task/run, task či run bez repa
a nesoulad tasku s během vracejí HTTP 400 `usage_error` před vytvořením vlákna.
Zprávy používají stejnou syntaktickou validaci screen, ale jejich screen zůstává
popiskem obrazovky bez kontroly existence identifikátorů.

Oproti plánu se backlog načítá přes `load_backlog(create_missing=False)`:
`load_for_edit()` by mohl vytvořit chybějící backlog. Lookup běhu používá
`trace_db_of` a `_trace_view`, takže chybějící DB nevytváří ani nemění schéma.

## Ověření

- `just pytest tests/web/test_web_assistant.py -n0`: 57 testů prošlo.
- `uv run ruff check` a `uv run ruff format --check` nad změněnými soubory
  `src/aifactory/web/assistant.py`, `src/aifactory/web/app.py` a
  `tests/web/test_web_assistant.py`: úspěch (spuštěno z `aifactory/`).
- `uv run mypy` nad stejnými třemi soubory: úspěch.
- Testy ověřují převzetí Codex bindingu s lokálně rozšířeným allowlistem i produkční
  Claude fallback, uložené thinking, stabilní session, restart, run přes aktuální
  task, neplatné kontexty, chybějící backlog a nečitelnou či chybějící trace DB.

Frontend se nemění; předání screen z obrazovky řeší T73.
