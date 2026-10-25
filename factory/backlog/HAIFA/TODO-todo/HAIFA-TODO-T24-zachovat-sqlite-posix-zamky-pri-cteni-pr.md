---
id: HAIFA-TODO-T24
title: Zachovat SQLite POSIX zámky při čtení Přehledu
status: done
archived: true
depends_on: []
follows: HAIFA-TODO-T23
writes: [aifactory/src/aifactory/web/overview.py, aifactory/tests/web/test_web_overview.py, aifactory/tests/web/test_web_db_busy.py, aifactory/tests/e2e/test_retry_browser.py, aifactory/tests/e2e/test_multi_repo_browser.py]
---

## Zadání
Diagnostika T23 konečně zachytila konkrétní chybu v main CI https://github.com/janbkrejci/HAIFA/actions/runs/39524730103: retry z Backlogu vrací HTTP 500 s internal_error „DatabaseError: database disk image is malformed (in _ensure_wal, store.py:639)“. GET /runs současně selže stejně, zatímco subprocess log ukazuje úspěšně dokončený druhý pokus. Úplný důkaz je /tmp/haifa-main-v2-failure.log.

Pravděpodobný konkrétní mechanismus je web/overview.py::_closed_wal: s db.open("rb") přečte 20 bajtů hlavičky a zavře fd. Přehled běží v témže serverovém procesu jako SQLite writer connection RunLauncher/TaskRunStore. SQLite výslovně dokumentuje, že raw open/read/close stejného DB souboru zruší všechny POSIX advisory locks daného procesu pro ten soubor, a může poškodit DB při dalších writerech. Viz https://www.sqlite.org/howtocorrupt.html oddíl 2.2. Obrany SQLite >=3.51 nejsou plným řešením, neměnit proto jen runtime verzi.

Ověř a oprav tento mechanismus: žádná přímá četba/zavírání živého DB souboru mimo SQLite v Přehledu. Zvol bezpečné rozlišení readonly/immutable režimu bez raw hlavičky (například pouze metadata/stat sidecarů, nebo jiný bezpečný postup), zachovej aktuální data živé WAL DB a existující read-only chování. Chybějící DB se nesmí vytvořit. Přehled uzavřené DB má pokud možno zachovat dosavadní absenci nových -wal/-shm souborů a projít původními testy. Vysvětli očekávané chování při souběhu writeru a readonly čtenáře.

Doplň deterministickou POSIX regresi, která před opravou selže: proces drží otevřenou SQLite WAL connection se skutečnou write/read transakcí; druhý proces zkusí přes fcntl získat konfliktní lock téhož DB souboru. Dokud je první SQLite spojení aktivní, konfliktní lock musí být odmítnut před čtením Přehledu i po něm. Starý raw header open/close lock shodí. Probe musí běžet v jiném procesu, protože fcntl zámky jsou per-process. Na ne-POSIX lze tento konkrétní test přeskočit; ostatní testy běží všude. Ověř zachování zapsaných dat a integrity. Neobcházej ochrany, neopakuj HTTP požadavek kvůli zamaskování chyby, nechytej malformed pro vrácení falešného úspěchu a nemaž žádnou DB/WAL.

Hotovo: prokázaná regrese a oprava zámků, původní testy Přehledu a oba retry browser scénáře projdou. Povinné just lint, just typecheck, cílené pytest přímých volajících a relevantní browser testy; celou suite ponech CI. Testy jsou bez živých modelů a služeb. Čti /tmp CI diagnostiku, přidej vysvětlení do dokumentace tasku.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-21 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/138 · náklady $0.00
