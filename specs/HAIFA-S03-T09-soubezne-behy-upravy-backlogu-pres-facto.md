# HAIFA-S03-T09 — Souběžné běhy: úpravy backlogu přes factory během běhu

## Cíl

Hlídač běhu (`run/guard.py`) dnes vrátí a nahlásí každou změnu hlavního checkoutu během fáze agenta. Zápisy backlogu, které udělá operátor příkazem factory (`task add`, `task edit`, `task link`, `backlog auto-continue` z CLI i z dashboardu), se tím ztratí a běh selže. Hlídač je musí rozpoznat a nechat je být, stejně jako už dnes nechává posuny base zapsané v žurnálu `run/basemoves.py`.

## Návrh: žurnál zápisů factory do hlavního checkoutu

Postup je stejný jako u `basemoves.py`: každý zápis souboru backlogu příkazem factory přidá jeden JSON řádek do žurnálu ve společném git adresáři. Hlídač si při `snapshot` uloží offset žurnálu a při `enforce` přijme změny, které vysvětlí cizí záznamy, tedy záznamy bez vlastního `HAIFA_RUN_ID`.

### Nový modul `aifactory/src/aifactory/run/mainwrites.py`

Docstring má popsat totéž co v `basemoves.py`: proč žurnál existuje, `run` = `HAIFA_RUN_ID`, záznam s vlastním run id se počítá jako zápis agenta. Známý limit: agent, který podvrhne záznam, hlídač obelstí (stejně jako u basemoves).

- Umístění: `journal(root) -> Path | None` = `<git common dir>/haifa/main-writes.jsonl` (stejně jako `basemoves.journal`, jen jiný název souboru; `git rev-parse --path-format=absolute --git-common-dir`). Obsahy souborů se ukládají podle obsahu do `<git common dir>/haifa/main-writes/<sha256>`, zapisují se atomicky přes tmp + `os.replace` a už existující blob se znovu nezapisuje.
- `@dataclass(frozen=True) class MainWrite`: `checkout: str` (absolutní `resolve()` kořene checkoutu, do kterého se psalo), `path: str` (relativní cesta, POSIX), `old: str | None` (sha256 obsahu před zápisem; `None` = soubor neexistoval), `new: str` (sha256 zapsaného obsahu), `mode: int` (oprávnění souboru po zápisu, `& 0o777`), `run: str | None` (`os.environ.get(basemoves.RUN_ENV) or None`), `command: str`.
- `offset(root) -> int`: velikost žurnálu v bajtech, 0 když neexistuje.
- `record(root: Path, path: str, old: bytes | None, new: bytes, *, mode: int, command: str) -> None`: nikdy nevyhodí výjimku (zachytí `OSError, RuntimeError, ValueError`). Nejdřív uloží blob `new`, potom připojí řádek. Řádek zapisuj jedním `os.write` na fd otevřený s `os.O_WRONLY | os.O_APPEND | os.O_CREAT`, aby se souběžné zápisy neproložily. Digest počítej `hashlib.sha256(...).hexdigest()`, stejně jako `backup._sha`, aby šel přímo porovnat s `backup.FileState.digest`.
- `writes_since(root, start) -> list[MainWrite]`: robustní parsování jako `basemoves.moves_since`/`_parse` (vadné řádky přeskoč).
- `content(root, digest) -> bytes | None`: přečte blob.
- `@dataclass class Accepted`: `states: dict[str, tuple[bytes, int]]` (cesta → obsah a mode, které má mít podle factory) a `agent_first: list[str]` (cesty, kde agent zapsal před zápisem factory).
- `accept(root: Path, writes: Sequence[MainWrite], expected: Callable[[str], backup.FileState], own_run: str | None) -> Accepted`: čistá logika řetězení:
  - vezmi jen záznamy s `Path(w.checkout) == root.resolve()` a `w.run != own_run` (když `own_run is None`, jsou cizí všechny, jako v basemoves). Záznamy vlastního běhu ignoruj, takže jejich zápis zůstane nevysvětlený = porušení.
  - pro každou cestu, v pořadí žurnálu: `cur` = digest z `expected(path)` (`None`, když `kind == "absent"`). Pro každý záznam: když `w.new == cur`, přeskoč ho (zápis už byl zachycen v záloze, nebo nic neměnil). Jinak když `w.old != cur`, přidej cestu do `agent_first` (mezi stavem známým hlídači a zápisem factory do souboru psal někdo jiný). Pak `cur = w.new`.
  - když je pro cestu na konci `cur` digest některého cizího záznamu, který se dá načíst přes `content()`, ulož do `states` jeho obsah a mode. Když blob chybí, cestu nepřijímej a nech ji být porušením.
- `wait_for_writes(root, start, paths_off, ..., tries=10, delay=0.1)`: obdoba `basemoves.wait_for_chain`. Když po `accept` zbývají porušené cesty bez cizího záznamu, krátce počkej na záznam, který se možná ještě zapisuje (žurnál se píše až po zápisu souboru). Čekej jen tehdy, když nějaká cesta z `off` nemá záznam.

### `aifactory/src/aifactory/backlog/edit.py`

- `_write_checked(backlog, baseline, changes, command: str)`: pro každý soubor v `pending` přečti před `_atomic_write` starý obsah (`targets[rel].read_bytes()`, nebo `None`, když soubor neexistuje). Po úspěšném zápisu zavolej `mainwrites.record(root, rel, old, text.encode("utf-8"), mode=<st_mode & 0o777 po zápisu>, command=command)`. Modul importuj líně uvnitř funkce, jak to dělá `commit.py` s `basemoves`, aby nevznikl importní cyklus. Pozor: `staged.write_text`/`_atomic_write` zapisují `text` v UTF-8 bez převodu konců řádků, takže zaznamenané bajty musí být bajty zapsané na disk. Ověř, že `tempfile.NamedTemporaryFile("w", ...)` nepřevádí `\n` (na POSIX nepřevádí). Jistější je zaznamenat `targets[rel].read_bytes()` hned po `os.replace`.
- `command`: `_commit` předá `f"task {action}"` (`task add`/`task edit`/`task link`), `set_auto_continue` předá `"backlog auto-continue"`. Jiná místa volání `_write_checked` nejsou (ověř grepem).
- Docstring modulu doplň o větu, že každý zápis se zaznamená do žurnálu `run/mainwrites.py`, aby ho hlídač souběžného běhu nebral jako zápis agenta.
- CLI (`cli.py`) ani dashboard (`web/backlog.py`, `web/app.py`) nemusí nic měnit, obojí volá tytéž funkce z `aifactory.backlog`. Dashboard spouští běhy jako podprocesy (`web/launcher.py`), takže sám `HAIFA_RUN_ID` nemá a jeho zápisy jsou cizí.

### `aifactory/src/aifactory/backlog/commit.py`

Funkčně nic nového: posun base už zapisuje `basemoves.record`. Commit nových souborů z `task add` během fáze bude fungovat, protože hlídač soubory přijme (viz níže) a pak přepne zálohu na nový `HEAD` a index z žurnálu posunů. Docstring jen doplň o zmínku o souběžných bězích.

### `aifactory/src/aifactory/run/backup.py`

Přidej `supersede(backup: CheckoutBackup, path: str, data: bytes, mode: int) -> None`: nastaví očekávaný stav cesty na zápis factory. Když existuje `backup.dir/"files"/path`, přesune ho do `backup.dir/"superseded"/path` (nic se nemaže; při kolizi přidej příponu `.N` jako `_set_aside`). Pak zapíše `data` do `backup.dir/"files"/path`, nastaví `backup.files[path] = FileState("file", sha256(data), mode)`, smaže případný `backup.links[path]` a přepíše `manifest.json` (vytáhni zápis manifestu z `capture` do privátní `_write_manifest(backup)`). Díky tomu `verify` a `restore` fungují beze změny: cesta zapsaná factory se porovnává s obsahem od factory a v případě potřeby se na něj vrátí.

### `aifactory/src/aifactory/run/guard.py`

1. `snapshot`: offsety žurnálů (`basemoves.offset` i nový `mainwrites.offset`) čti **před** `backup.capture`, ne po ní. Jinak se zápis nebo posun mezi capture a offsetem ztratí a vypadá jako porušení. Zápis zachycený zálohou a zároveň v žurnálu ošetří pravidlo „`w.new == cur` → přeskoč“. Do slovníku přidej `"main_writes": mainwrites.offset(...)`.
2. `enforce`, část hlavního checkoutu, v tomto pořadí:
   - `original = before["main_backup"]` (záloha před případným přepnutím na nový HEAD).
   - Logika basemoves beze změny (`main_backup` se případně nahradí přes `dataclasses.replace` s novým `head`/`index_tree`). Pozor: `dataclasses.replace` sdílí slovníky `files`/`links` s originálem. `supersede` je mění na místě, což je tady v pořádku, protože originál se dál používá jen v `expected` při řetězení, a to proběhne před supersede. Kvůli čitelnosti ale nejdřív spočti `accepted`, teprve potom supersede.
   - `writes = mainwrites.writes_since(self.main_root, before.get("main_writes", 0))`, `accepted = mainwrites.accept(self.main_root, writes, lambda p: backup.expected(original, p), getattr(run, "adw_id", None))`. `expected` se počítá proti **původní** záloze (HEAD před fází), protože `old` prvního zápisu odpovídá stavu před fází.
   - Pro každou cestu v `accepted.states`, která neleží v `main_ignored`: `backup.supersede(main_backup, path, data, mode)`.
   - `off = backup.verify(main_backup, self.main_ignored)`. Když `off` obsahuje cestu bez cizího záznamu, použij `wait_for_writes`, znovu spočti `accepted`, proveď supersede a `verify`.
   - Restore a hlášení jako dosud. Pro cestu z `accepted.states`, kterou restore vrátil, použij výsledek `"restored to the factory write"` místo `"restored from backup"` (přepiš `outcomes[path]`, když začíná na `"restored"`).
   - Pro každou cestu v `accepted.agent_first`, která není v `off`, přidej problém `f"{MAIN}: {path} — changed by the agent before a factory write; factory content kept"`.
   - Pozor na `head_moved` v `backup.restore`: když HEAD posunul cizí `backlog commit`, je `main_backup.head` už nový HEAD, takže `head_moved` je False a restore funguje. Bez posunu se nic nemění.
3. Index: zápisy `task add/edit/link/auto-continue` index nemění. `backlog commit` mění index i HEAD a to pokrývá basemoves (`move.index_tree`). Nic dalšího není potřeba.
4. Docstring modulu: doplň odstavec o žurnálu zápisů factory (paralela k odstavci o basemoves). Factory zápis během fáze se nevrací ani nehlásí. Zápis s vlastním run id je zápis agenta. Když do stejného souboru zapíše factory i agent, zůstane obsah od factory a zápis agenta se vrátí a nahlásí (ať byl před zápisem factory, nebo po něm).
5. `ConflictWriteGuard` (`run/resolve.py`) dědí `snapshot`/`enforce`, takže se nemění.

### Shrnutí chování (mapování na „Done means“)

| Situace | Výsledek |
|---|---|
| Operátor/dashboard (bez `HAIFA_RUN_ID` nebo s cizím) `task add/edit/link`, `backlog auto-continue` během fáze | `accept` cestu přijme, `verify` ji nehlásí, soubor zůstane |
| Následný `backlog commit` | basemoves přijme posun HEAD a nové soubory jsou čisté vůči novému HEAD, běh pokračuje |
| Agent spustí `factory task add` (zdědí `HAIFA_RUN_ID` běhu) | záznam s vlastním run id se ignoruje, takže porušení a vrácení jako dnes |
| Ruční zápis jinam / bez záznamu | beze změny, vrátí se a nahlásí |
| Factory zapíše X, pak agent přepíše X | `states[X]` = obsah od factory, `verify` X hlásí, restore vrátí obsah od factory a problém se nahlásí |
| Agent zapíše X, pak factory edit X | `old != cur`, takže `agent_first`: obsah od factory zůstane a problém se nahlásí |

## Testy (`aifactory/tests/`)

### Jednotkové: nový `aifactory/tests/run/test_mainwrites.py`

Vzor: `test_basemoves.py`, git repo v `tmp_path`.
- `record` + `writes_since` + `offset`: řádek má `run` z env (`monkeypatch.setenv/delenv(basemoves.RUN_ENV)`) a `content(root, new)` vrací bajty. Mimo repo (`tmp_path` bez gitu) je `record` no-op a `offset == 0`.
- `accept`: (a) cizí zápis nového souboru je přijat, (b) záznam s vlastním run id přijat není, (c) řetěz dvou cizích zápisů téže cesty je přijat s posledním obsahem, (d) `old` neodpovídá → `agent_first`, (e) záznam s `new == expected` se přeskočí (zápis zachycený zálohou), (f) záznam z jiného `checkout` se ignoruje.
- `backup.supersede`: po supersede vrací `verify` prázdný seznam pro obsah od factory. Po přepsání agentem `restore` vrátí obsah od factory a původní kopie leží v `superseded/`.

### Hlídač: nový `aifactory/tests/run/test_guard_backlog_writes.py`

Vzor: `test_guard_base_moves.py`, falešný harness `run_repo.fake_env`/`Script`, `foreign()` (zkopíruj helper, nebo ho importuj z `test_guard_base_moves`, pokud to konvence importů v testech dovoluje; `run_repo` a `test_auto_continue` se importují stejně).
1. `test_factory_backlog_write_is_not_a_breach`: v efektu planneru `with foreign(): add_task(repo, "M01-S01", "Nový task")` a `edit_task` na `M01-S01-T02`. Běh `run_task(repo, T01)` doběhne `succeeded` a soubory v `repo/backlog/...` mají obsah od factory (neprázdný `git status --porcelain -- backlog`).
2. `test_factory_write_started_by_the_agent_is_a_breach`: totéž bez `foreign()` (env má run id běhu). Běh `failed`, chyba obsahuje `main checkout: backlog/...` a soubor je vrácený nebo smazaný.
3. `test_agent_write_after_factory_write_keeps_factory_content`: `with foreign(): edit_task(...)`, pak `write(repo, <ta cesta>, "hijacked\n")`. Běh `failed`, chyba jmenuje cestu a obsah na disku je obsah od factory.
4. `test_agent_write_before_factory_write_is_reported`: nejdřív `write(repo, path, ...)`, pak `with foreign(): edit_task(...)`. Běh `failed`, chyba obsahuje `changed by the agent before a factory write` a obsah je od factory.
5. `test_other_main_checkout_change_is_still_a_breach`: cizí `add_task` plus agent zapíše `README.md`. Běh `failed`, `README.md` se vrátí, nový task zůstane.
6. `test_add_and_commit_backlog_during_phase` (požadovaný test přes falešný harness): `with foreign(): add_task(...); commit_backlog(repo)`. Běh A `succeeded`, `git cat-file -e main:<cesta nového tasku>` projde, `git status --porcelain` hlavního checkoutu je prázdný a HEAD je `refs/heads/main`.
7. `test_auto_continue_during_phase`: `with foreign(): set_auto_continue(repo, "M01-S01", True)`. Běh `succeeded`.

Volitelně jeden test přes CLI (`aifactory.cli.main([...])` s `--repo`, jak to dělají existující CLI testy; najdi je grepem `"task", "add"` v `tests/`) a jeden přes dashboard API (TestClient, vzor v `tests/web/`) uvnitř efektu fáze. Tím se ověří, že CLI i dashboard jdou přes `_write_checked`.

Než přidáš testy, spusť existující `tests/run/test_guard_base_moves.py`, `test_guard_backup.py`, `test_parallel_runs.py` a `tests/backlog/`. Po změně musí projít beze změn.

## Ověření

```
just test
just typecheck
just lint
```
Všechny tři musí skončit s exit 0. Testy nevolají model ani síť (falešný harness). Neměň `vendor/` ani `prototype/`.

## Dokumentace

`app_docs/HAIFA-S03-T09-soubezne-behy-upravy-backlogu-pres-facto.md`: krátký popis žurnálu `main-writes.jsonl` + blobů, pravidel přijetí v hlídači, chování při souběhu factory a agenta a známých limitů (podvržený záznam, gitignored cesty, mimo rozsah: zápisy `.factory/` konfigurace).

## Soubory

- nový `aifactory/src/aifactory/run/mainwrites.py`
- `aifactory/src/aifactory/run/backup.py` (`supersede`, `_write_manifest`)
- `aifactory/src/aifactory/run/guard.py` (snapshot offsety před capture, přijetí zápisů factory, docstring)
- `aifactory/src/aifactory/backlog/edit.py` (`_write_checked` zaznamenává, `command`)
- `aifactory/src/aifactory/backlog/commit.py` (jen docstring)
- nové testy `aifactory/tests/run/test_mainwrites.py`, `aifactory/tests/run/test_guard_backlog_writes.py`
- `app_docs/HAIFA-S03-T09-soubezne-behy-upravy-backlogu-pres-facto.md`
