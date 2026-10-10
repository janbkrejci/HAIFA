# HAIFA-S03-T08: Souběžné běhy: posun base od factory není porušení hlídače

## Co se změnilo a proč

Hlídač běhu (`TaskWriteGuard` v `aifactory/src/aifactory/run/guard.py`) po fázi agenta porovnává `HEAD` hlavního checkoutu s jeho stavem před fází. Když souběžně jiný příkaz factory (např. `factory task approve` jiného běhu) fast-forwardem posunul `main`, hlídač to připsal agentovi a běh selhal s hláškou „main checkout: HEAD — moved to refs/heads/main, not rolled back“ (incident 2026-10-03, běh b71b5aaf / HAIFA-S01-T04).

Teď příkazy factory, které posouvají base, zapisují **žurnál posunů base**. Podle něj hlídač pozná, že posun udělal jiný proces, a běh nechá pokračovat.

### Žurnál posunů base (`aifactory/src/aifactory/run/basemoves.py`, nový)

- Soubor `<git common dir>/haifa/base-moves.jsonl`. Každý posun base je jeden JSON řádek (`BaseMove`): `ref`, `old`, `new`, `run`, `index_tree`, `command`.
- `run` je hodnota proměnné prostředí `HAIFA_RUN_ID` (`RUN_ENV`) v procesu, který posun udělal. `index_tree` je strom indexu checkoutu, kde je base checkoutnutá.
- `record()` nikdy nevyhazuje výjimku, takže selhání žurnálu příkaz nerozbije. `moves_since()` čte od daného bajtového offsetu a poškozené řádky přeskakuje.
- `factory_chain()` / `wait_for_chain()` hledají řetěz posunů daného refu od `HEAD` před fází po `HEAD` teď. Pokud některý článek nese vlastní id běhu, řetěz neplatí. `wait_for_chain` chvíli počká (výchozí nastavení 10× po 0,1 s) na článek, který se ještě zapisuje.
- Známé omezení (uvedené v docstringu): agent, který do žurnálu zapíše podvržený záznam s cizím `run`, hlídač obejde.

### Kdo do žurnálu zapisuje

- `providers/git.py`: `advance_branch()` dostala parametr `command` (výchozí `"advance"`). Posun zapíše po update-ref i po fast-forwardu v checkoutu.
- `providers/local.py` (merge) a `review/flow.py` (`_catch_up_base`) volají `command="task approve"`.
- `providers/publish.py`: `_advance` zapisuje `"config commit"`, `pull_base` volá `advance_branch(..., command="config pull")`.
- `backlog/commit.py`: `commit_backlog` zapisuje `"backlog commit"`.
- `run/backup.py`: nová veřejná funkce `index_tree()` (obal nad `_write_tree`).

### Id běhu v prostředí (`run/task.py`)

`_execute` po dobu workflow nastaví `HAIFA_RUN_ID` na `row.run_id` a pak vrátí původní hodnotu. Agenti i příkazy `factory`, které agent spustí, tuto proměnnou zdědí. Jejich posun base proto nese vlastní id a zůstává porušením.

### Hlídač (`run/guard.py`)

- Před fází si uloží offset žurnálu (`base_moves`).
- Po fázi: pokud je větev stejná, `HEAD` se pohnul a `wait_for_chain` najde řetěz cizích posunů, přepne se záloha (`main_backup`) na nový `HEAD` a na `index_tree` z posledního článku. `HEAD` se pak nehlásí jako porušení.
- Soubory hlavního checkoutu se dál ověřují a vracejí, nově proti novému `HEAD`.
- Porušením dál zůstává: commit, reset, checkout nebo přepnutí větve od agenta (i když ve stejné fázi proběhl i posun od factory), chybějící článek řetězu a posun od příkazu se stejným `HAIFA_RUN_ID`.

## Testy a ověření

- `aifactory/tests/run/test_basemoves.py`: umístění žurnálu, zápis a čtení od offsetu, přeskakování poškozených řádků, `record` bez výjimky mimo repo, řetězy (cizí, s vlastním článkem, s chybějícím článkem), `wait_for_chain` u vlastního běhu, zápis z `commit_backlog` a `advance_branch`.
- `aifactory/tests/run/test_guard_base_moves.py` (falešný harness, `foreign()` odebere `HAIFA_RUN_ID` a tím simuluje cizí proces):
  - posun od factory projde, běh skončí `succeeded` a nevznikne záloha hlídače,
  - posun od agenta je porušení,
  - posun od factory a k tomu commit agenta, resp. přepnutí větve agentem, je porušení,
  - změněný soubor se vrátí proti novému `HEAD` a hlásí se jen soubor, ne `HEAD`,
  - dva běhy: během fáze plan běhu A se schválí běh B, PR B je `merged` a běh A doběhne úspěšně. Když schválení spustí agent běhu A, je to porušení.

Spuštění:

```
just test
just typecheck
just lint
```

Spec úlohy: `specs/HAIFA-S03-T08-soubezne-behy-posun-base-od-factory-neni.md`.
