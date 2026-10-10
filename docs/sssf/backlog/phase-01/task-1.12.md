Oprav souběh při prvních paralelních bězích tasků: dva souběžné běhy nad dosud neexistující trace DB občas selžou s `database is locked`. `TaskRunStore` v `prototype/src/haifa_proto/run.py` založí DB v režimu rollback journal a při `claim` a `serialized()` drží `BEGIN IMMEDIATE`, zatímco `Tracer.__init__` ve vendoru volá `PRAGMA journal_mode=WAL` ještě před `PRAGMA busy_timeout`, takže přepnutí selže, když druhé spojení drží zápisový zámek.

Where: `prototype/src/haifa_proto/run.py`, `prototype/tests/`.

Done means:
- `tests/test_auto_continue.py::test_parallel_runs_of_different_tasks` projde ve 20 po sobě jdoucích bězích.
- Nový test ověří, že dva souběžné běhy nad dosud neexistující trace DB oba doběhnou bez `database is locked`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: zrychlení testové sady (úkol 1.11), příprava trace DB v testech předem, která by chybu skryla.

Pevná omezení:
- `vendor/` se neupravuje. Oprava je v `prototype/`.
