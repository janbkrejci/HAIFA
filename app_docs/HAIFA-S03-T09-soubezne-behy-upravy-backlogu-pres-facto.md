# HAIFA-S03-T09 — Souběžné běhy: úpravy backlogu přes factory během běhu

## Co se změnilo

Operátor může během fáze agenta jiného běhu upravovat backlog příkazy factory
(`task add`, `task edit`, `task link`, `backlog auto-continue`, z CLI i z dashboardu)
a potom spustit `backlog commit`. Hlídač běhu takový zápis nevrátí ani nenahlásí a běh
pokračuje.

## Žurnál zápisů factory (`run/mainwrites.py`)

- Každý zápis souboru v `backlog/edit.py` (`_write_checked`) přidá po nahrazení souboru
  jeden JSON řádek do `<git common dir>/haifa/main-writes.jsonl`: checkout, cestu,
  sha256 obsahu před zápisem (`null` = soubor neexistoval) a po zápisu, mode, příkaz
  a `run` = `HAIFA_RUN_ID` zapisujícího procesu.
- Zapsaný obsah se uloží podle digestu do `<git common dir>/haifa/main-writes/<sha256>`.
  Hlídač ho potřebuje, aby mohl soubor vrátit na obsah od factory.
- Řádek se připojí jedním `os.write` s `O_APPEND`, takže se souběžné zápisy neproloží.
  Chyba žurnálu nikdy neshodí příkaz.

## Pravidla v hlídači (`run/guard.py`)

- `snapshot` si offsety žurnálů posunů base a zápisů factory přečte ještě před zálohou
  hlavního checkoutu.
- `enforce` vezme záznamy zapsané během fáze, které patří k hlavnímu checkoutu a nemají
  vlastní run id běhu. Pro každou cestu je zřetězí od stavu před fází. Záznam, jehož
  obsah už záloha zachytila, přeskočí. Poslední obsah od factory pak nastaví jako
  očekávaný stav cesty (`backup.supersede`, původní kopie ze zálohy jde do
  `superseded/`). `verify` a `restore` pracují beze změny.
- Zápis s vlastním run id (agent spustil `factory task …`) se nepřijme, takže se vrátí
  a nahlásí jako dřív.
- Factory i agent zapsali stejný soubor:
  - agent po factory: soubor se vrátí na obsah od factory a hlásí se
    `restored to the factory write`;
  - agent před factory: obsah od factory zůstane a hlásí se
    `changed by the agent before a factory write; factory content kept`.
- Ostatní změny hlavního checkoutu se vracejí a hlásí jako dřív.
- Žurnál se píše až po zápisu souboru. U nevysvětlených `.md` cest proto hlídač chvíli
  počká na záznam, který se možná ještě zapisuje.
- Následný `backlog commit` pokrývá stávající žurnál posunů base (`run/basemoves.py`).
  Záloha se přepne na nový `HEAD` a commitnuté soubory jsou vůči němu čisté.

## Známé limity

- Agent, který do žurnálu podvrhne záznam s cizím run id a k němu blob, hlídač obelstí
  (stejně jako u `basemoves`).
- Cesty v `.gitignore` git nevidí, takže je hlídač nekontroluje.
- Mimo rozsah: zápisy konfigurace v `.factory/` během běhu (Nastavení, `config set`).

## Testy

- `aifactory/tests/run/test_mainwrites.py`: žurnál, `accept` a `backup.supersede`.
- `aifactory/tests/run/test_guard_backlog_writes.py`: hlídač s falešným harnessem.
  Zápis od factory projde, zápis od agenta je porušení, při zápisu obou zůstane obsah
  od factory. Dál pokrývá `task add` s `backlog commit` během fáze a zápisy přes CLI
  a dashboard.
