Zrychli testovou sadu `aifactory`: sada běží paralelně a pomalé testy nečekají zbytečně. Dnes běží přes 10 minut (po úkolu 2.18 to bylo 9 min 6 s pro 666 testů) a fáze test v ADW naráží na limit.

Where: `aifactory/tests/`, `aifactory/validation/` (testy validace), a `aifactory/src/aifactory/` jen tam, kde pomalost způsobuje čekání v kódu.

Done means:
- `just test` projde a běží paralelně.
- Časové cíle se neověřují: stroj je souběžnými běhy přetížený (load average kolem 80 na 4 jádrech) a měření by nebylo férové. Výsledek `pytest --durations=15` z jednoho běhu je v souhrnu buildu jen pro informaci.
- Počet testů neklesne a žádný test není přeskočený ani oslabený.

Out of scope: nové funkce, úpravy nesouvisející s dobou běhu testů.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Výchozí chování CLI a běhů se nemění. Kratší čekání v testech se nastavuje parametrem nebo konfigurací, ne změnou výchozích hodnot.
