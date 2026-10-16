# HEAL-S02-T02: Builder bez práce ukončí běh jako hotový bez změn

## Co se změnilo

Builder, který zjistí, že nemá co dělat, už běh nenechá viset jako selhaný. Rozlišuje dva
případy:

| Případ | Co builder vrátí | Jak běh skončí |
| --- | --- | --- |
| práci už udělal jiný task nebo commit | `status: success` a `already_done: {evidence, reason}` | úspěšně, bez PR, task `done` v base |
| zadání žádá jen změnu backlogu (front matter, stav, text tasku) | `status: fail` a `fail_kind: nothing_to_do` | selhání `nothing_to_do`, karta nabídne **Hotovo** nebo **Zrušit task** |

### Už hotovo

- `BuildOutput.already_done` (`engine/data_types.py`, typ `AlreadyDone`) nese `evidence`:
  aspoň jeden commit (sha nebo subject) nebo soubor repa, kde změna je, a volitelně `reason`.
  Prázdný důkaz nebo `already_done` u `status: fail` envelope neprojde validací.
- První build běhu s `already_done` workflow hned ukončí (`workflow/interpreter.py`). Testy,
  review ani commit se nespustí a `accept` se nevyhodnocuje, protože nic nevzniklo.
  `WorkflowRun.already_done` nese důkaz. Pozdější build (`fix`, `revise`), který nic
  neopravuje, běh neukončí. Kroky po něm dál ověřují dřívější práci.
- Běh bez commitu na větvi pak skončí podle rozhodnutí „Prázdný commit“ (`run/unchanged.py`):
  task dostane `status: done` v base a v `## Běhy` záznam
  `bez změn, běh <id> · už hotovo: <důkaz> · náklady $…`. Commit backlogu má subject
  `<task>: hotovo bez změn (běh <id>)`.

### Jen změna backlogu

- Karta selhání `nothing_to_do` v detailu běhu nabízí **Hotovo** a **Zrušit task**.
- Hotovo po potvrzení zavolá `POST /api/runs/{id}/done` (`finish_nothing_to_do` v
  `run/unchanged.py`): task dostane `status: done` v base se záznamem
  `bez změn, běh <id> · důvod: <agent>: <shrnutí agenta> · náklady $…` a commit backlogu jde
  do base podle `base_changes`.
- Odpověď: `{task_id, commit, run}`. Chyby: `unknown_run` (404), `already_running` a
  `not_nothing_to_do` (409, běh neselhal na `nothing_to_do`), chyby úpravy a commitu
  backlogu jako u ostatních zápisů (`TaskEditError`, např. zrušený task).

### Prompt buildera

Semínko `seed/agents/builder/user.md` popisuje obě cesty. U „už hotovo“ builder nic nemění
a uvádí jen důkaz, který v repu ověřil. U změny backlogu backlog sám neupravuje a v
`summary` řekne, co a kde se má změnit.

## Testy

- `tests/run/test_unchanged.py` (fake harness):
  - builder vrátí `already_done`, workflow skončí po buildu (tester se nevolá), běh je
    úspěšný bez PR a task má `done` se záznamem „bez změn“ a důkazem,
  - `already_done` z pozdějšího buildu běh neukončí, commit a PR vzniknou,
  - validace `already_done` (prázdný důkaz, `status: fail`),
  - builder vrátí `nothing_to_do`, běh selže s tímto druhem a `finish_nothing_to_do` označí
    task hotový s důvodem agenta. Jiné selhání skončí `not_nothing_to_do`, neznámý běh
    `unknown_run`. Totéž přes `POST /api/runs/{id}/done`.
- `web/src/components/runs/FailureCard.test.ts`: karta `nothing_to_do` má akce Hotovo
  a Zrušit task. Hotovo po potvrzení pošle POST, ohlásí hotovo a tlačítka zablokuje.
  Odmítnutí zobrazí chybu.
