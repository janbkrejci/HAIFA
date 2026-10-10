# Plán: souběh `database is locked` při prvních paralelních bězích tasků

## Problém

`TaskRunStore.__init__` (`prototype/src/haifa_proto/run.py`, ř. ~247) otevře trace DB,
nastaví `busy_timeout` a spustí `_SCHEMA`. DB tak vznikne v režimu **rollback journal**
(výchozí). `claim()` a `serialized()` pak drží `BEGIN IMMEDIATE` (zápisový zámek),
`serialized()` navíc po dobu `git worktree add`.

Vendorový `Tracer.__init__` (`vendor/sssf/templates/adws/adw_modules/tracer.py:108-111`,
volaný z `session.py` uvnitř `run_workflow`) dělá:

```
connect → PRAGMA journal_mode=WAL → PRAGMA synchronous=NORMAL → PRAGMA busy_timeout=5000 → SCHEMA
```

Přepnutí rollback→WAL potřebuje exkluzivní zámek; protože `busy_timeout` je v tu chvíli
ještě 0, selže okamžitě s `database is locked`, pokud druhý proces právě drží
`BEGIN IMMEDIATE` v `claim`/`serialized`. Jakmile je soubor jednou ve WAL (režim je
perzistentní v hlavičce souboru), je `PRAGMA journal_mode=WAL` no-op bez zámku —
proto chyba nastává jen „při prvních bězích“ nad dosud neexistující DB.

`vendor/` se neupravuje.

## Oprava (jen `prototype/src/haifa_proto/run.py`)

V `TaskRunStore.__init__` přepnout DB do WAL **dřív, než ji kdokoli jiný (Tracer)
otevře**, a to až po nastavení `busy_timeout`, s ověřením výsledku:

```python
def __init__(self, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    self.db_path = db_path
    self.conn = sqlite3.connect(str(db_path), isolation_level=None)
    self.conn.execute("PRAGMA busy_timeout=5000;")
    _ensure_wal(self.conn)
    self.conn.executescript(_SCHEMA)
```

Nová modulová funkce (poblíž `_now`/`_alive`):

```python
_WAL_ATTEMPTS = 50  # × 0.1 s navíc k busy_timeout


def _ensure_wal(conn: sqlite3.Connection) -> None:
    """Switch the trace DB to WAL, which the vendored Tracer expects.

    The Tracer asks for WAL before it sets busy_timeout, so on a fresh (rollback
    journal) DB the switch fails at once when another run holds BEGIN IMMEDIATE.
    Once the file is WAL the Tracer's pragma is a lock-free no-op, so doing the
    switch here, with a busy timeout, closes that race.
    """
    for attempt in range(_WAL_ATTEMPTS):
        try:
            mode = conn.execute("PRAGMA journal_mode=WAL;").fetchone()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) and "busy" not in str(exc):
                raise
        else:
            if mode is not None and str(mode[0]).lower() == "wal":
                return
        time.sleep(0.1)
    raise TaskRunError("trace_db_locked", f"cannot switch {conn_path} to WAL")  # viz níže
```

Poznámky k implementaci:
- Retry smyčka je pojistka: SQLite u změny journal_mode ne vždy volá busy handler
  a dva `TaskRunStore` mohou přepínat současně. Rozhoduj podle výjimky/výsledku
  pragmy, ne podle textu výstupu mimo výjimku.
- Pro chybovou zprávu předej do funkce i `db_path` (signatura
  `_ensure_wal(conn, db_path)`), ať nevzniká neexistující `conn_path`.
  Po vyčerpání pokusů vyhoď `TaskRunError("trace_db_locked", ...)` (TaskRunError je
  definovaná výš v souboru – ověř pořadí; funkci umísti až za ni).
- Přidej `import time`, pokud tam ještě není.
- WAL nemění sémantiku zámků: `BEGIN IMMEDIATE` dál serializuje zapisovatele, takže
  `claim` (already_running) i `serialized` fungují stejně; čtenáři jen neblokují.
- Aktualizuj modulový docstring (odstavec „Runs of different tasks may go on…“,
  ř. ~28-35) o větu: `TaskRunStore` přepíná trace DB do WAL dřív, než ji otevře
  Tracer enginu, protože ten nastavuje WAL před `busy_timeout`.
- Všechny cesty, které otevírají trace DB přes `TaskRunStore`
  (`_run`, `task_runs_for`, `task_prs_for`, `queue.py`, `review.py`, web), tím
  automaticky dostanou WAL — nic dalšího měnit netřeba. V `_run` se `TaskRunStore`
  vytváří před `run_workflow`, takže Tracer vždy najde DB už ve WAL.

## Testy (`prototype/tests/test_auto_continue.py`, sekce „parallel runs“)

Nepřipravovat trace DB předem (to by chybu skrylo) — testy naopak ověří, že
DB před startem **neexistuje**.

1. **Deterministický regresní test** `test_tracer_opens_fresh_trace_db_while_store_holds_lock`
   (bez forku, `tmp_path`):
   - `db = tmp_path / "trace.db"`; `assert not db.exists()`.
   - `store = TaskRunStore(db)`; `Tracer = engine.load_engine_module("tracer").Tracer`
     (`from haifa_proto import engine`).
   - V hlavním vlákně `with store.serialized():` spusť `threading.Thread`, který
     zkonstruuje `Tracer(db, tmp_path / "events.jsonl")` a výjimku/úspěch uloží do
     seznamu; drž zámek ~0.5 s (`time.sleep(0.5)`), pak blok opusť a `thread.join(10)`.
   - Assert: vlákno skončilo bez výjimky; `PRAGMA journal_mode` na nové spojení
     vrací `wal`. Tracer i store zavři (`tracer.conn.close()` pokud Tracer nemá
     `close()`, ověř v tracer.py).
   - Bez opravy test spadne okamžitě na `database is locked` (journal_mode pragma
     bez busy_timeout); s opravou je pragma no-op a `SCHEMA` Traceru počká na
     uvolnění zámku díky jeho busy_timeoutu.
   - Pokud Tracer v tomto prostředí vyžaduje další argumenty, přizpůsob se signatuře
     `Tracer(db_path, events_jsonl)`.

2. **End-to-end test** `test_parallel_runs_on_fresh_trace_db`:
   - Stejný vzor jako `test_parallel_runs_of_different_tasks` (`_setup`, `_fork`,
     `_child`, `_collect`), ale před startem procesů
     `assert not trace_db_path(repo, load_config(repo), env.cfg).exists()`.
   - Zvětši okno souběhu: `before` = společná `ctx.Barrier(2)` (oba procesy startují
     `run_task` současně), `inside` = druhá bariéra (oba ve workflow zároveň).
   - Assert: oba výsledky `("ok", factory/<tid>-1)`, žádný `"crash"`/`"failed"`
     s `database is locked`; oba řádky `succeeded`.
   - Volitelně `@pytest.mark.parametrize("attempt", range(3))` pro víc pokusů
     v jedné sadě, pokud to nezpomalí sadu znatelně (zrychlení sady je mimo rozsah,
     ale nezhoršuj ji víc než o pár sekund).

3. Volitelně v `prototype/tests/test_task_run.py`: jednoduchý test, že
   `TaskRunStore(tmp_path/"x.db")` nechá DB v `journal_mode = wal`.

## Ověření

```
cd /Users/jbk/Documents/HAIFA
for i in $(seq 1 20); do just test tests/test_auto_continue.py::test_parallel_runs_of_different_tasks -q -p no:cacheprovider || break; done   # musí projít 20×
just test tests/test_auto_continue.py -k "fresh_trace_db or tracer_opens" -q
just test
just typecheck
just lint
```

Úspěch posuzuj podle exit statusu, ne podle textu výstupu. Před opravou ověř
(volitelně), že deterministický test 1 selže — potvrzuje, že testuje skutečnou chybu.

## Mimo rozsah
- Úpravy `vendor/`.
- Zrychlení testové sady (úkol 1.11).
- Předvytváření trace DB v testech/fixture.
