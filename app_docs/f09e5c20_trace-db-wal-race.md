# Oprava souběhu `database is locked` nad novou trace DB

## Co se změnilo a proč

Při prvních paralelních bězích tasků nad dosud neexistující trace DB občas jeden z běhů
spadl s `database is locked`. Příčina:

- `TaskRunStore` založil DB ve výchozím režimu **rollback journal** a v `claim()`
  a `serialized()` drží `BEGIN IMMEDIATE` (zápisový zámek).
- Vendorový `Tracer.__init__` volá `PRAGMA journal_mode=WAL` **před**
  `PRAGMA busy_timeout`. Přepnutí rollback → WAL potřebuje exkluzivní zámek, a protože
  busy timeout je v tu chvíli 0, selže okamžitě, pokud jiný běh drží zápisový zámek.
- Jakmile je soubor ve WAL (režim je uložen v hlavičce souboru), je tatáž pragma no-op
  bez zámku, proto se chyba projevovala jen u čerstvé DB.

Oprava (bez zásahu do `vendor/`): `TaskRunStore.__init__` přepne DB do WAL sám, hned po
nastavení `busy_timeout=5000` a ještě před `_SCHEMA`. Tracer pak DB najde už ve WAL
a jeho pragma nic nezamyká. Sémantika zámků se nemění — `BEGIN IMMEDIATE` dál
serializuje zapisovatele, takže `claim` (`already_running`) i `serialized` fungují jako dřív.

## Soubory

- `prototype/src/haifa_proto/run.py`
  - nová funkce `_ensure_wal(conn, db_path)`: až `_WAL_ATTEMPTS = 50` pokusů po 0,1 s
    (navíc k `busy_timeout`) spustí `PRAGMA journal_mode=WAL`; chyby obsahující
    `locked`/`busy` opakuje, ostatní `OperationalError` propustí dál; uspěje, jen když
    pragma vrátí `wal`. Po vyčerpání pokusů vyhodí
    `TaskRunError("trace_db_locked", "cannot switch <db> to WAL")`.
  - `TaskRunStore.__init__` ji volá mezi `busy_timeout` a `_SCHEMA`.
  - přidán `import time` a věta v modulovém docstringu vysvětlující důvod.
- `prototype/tests/test_auto_continue.py` — dva nové testy (trace DB se předem
  nepřipravuje, testy naopak ověřují, že před startem neexistuje):
  - `test_tracer_opens_fresh_trace_db_while_store_holds_lock` — deterministický
    regresní test: v jednom vlákně drží `store.serialized()` zámek ~0,5 s, v druhém se
    konstruuje vendorový `Tracer` (přes `engine.load_engine_module("tracer")`). Ověřuje,
    že Tracer doběhne bez výjimky a DB je ve `wal`.
  - `test_parallel_runs_on_fresh_trace_db` — end-to-end: dva forkované běhy (T01, T03)
    startují přes společnou `Barrier` současně nad neexistující DB; oba musí skončit
    `ok` na `factory/<tid>-1` se stavem `succeeded`.
- `specs/f09e5c20_trace-db-wal-race.md` — plán opravy (analýza, návrh, testy, ověření).

## Ověření

```
cd /Users/jbk/Documents/HAIFA   # justfile je v kořeni repa
for i in $(seq 1 20); do just test tests/test_auto_continue.py::test_parallel_runs_of_different_tasks -q -p no:cacheprovider || break; done
just test tests/test_auto_continue.py -k "fresh_trace_db or tracer_opens" -q
just test && just typecheck && just lint
```

Posuzujte podle exit statusu. Existující trace DB v rollback journal režimu se při
příštím otevření přes `TaskRunStore` přepne do WAL automaticky.
