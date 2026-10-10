Zrychli testovou sadu prototypu tak, aby `just test` doběhl do 2 minut. Dnes 299 testů běží 7 min 42 s a desítky testů trvají kolem 10 s, nejpomalejší jsou v `test_auto_continue.py`, `test_pr_flow_github.py`, `test_cli_task.py` a `test_web.py`.

Where: `prototype/tests/`, a `prototype/src/haifa_proto/` jen tam, kde pomalost způsobuje čekání v kódu.

Done means:
- `just test` projde a celý doběhne do 120 s.
- Žádný test netrvá déle než 5 s (`pytest --durations=10`).
- Počet testů neklesne pod 299 a žádný test není přeskočený ani oslabený.

Out of scope: nové funkce, úpravy nesouvisející s dobou běhu testů.

Pevná omezení:
- `vendor/` se neupravuje.
- Výchozí chování CLI a běhů se nemění. Kratší čekání v testech se nastavuje parametrem nebo konfigurací, ne změnou výchozích hodnot.
