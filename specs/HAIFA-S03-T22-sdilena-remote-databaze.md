# HAIFA-S03-T22: Sdílená remote databáze

Factory a dashboard mohou namísto lokálního trace SQLite používat společnou databázi na vzdáleném počítači nebo v Docker kontejneru. Implementovaný backend je SQLite na serveru, přístupný přes veřejné read/write HTTP RPC. MSSQL/ODBC připojení není součástí této implementace.

## Konfigurace a identita

Celofactory nastavení je `<HAIFA home>/database.yaml` s jediným klíčem `url`; home se určuje standardně podle `HAIFA_HOME`, `XDG_CONFIG_HOME` nebo `~/.config/haifa`. `HAIFA_DATABASE_URL` má přednost před souborem. Volitelné `.factory/local.yaml: database_url` má přednost před oběma. Bez URL zůstává původní `trace_db` a nativní SQLite.

Identita projektu je SHA-256 normalizované URL remote z `.factory/config.yaml: remote` (výchozí `origin`). Normalizace sjednocuje HTTPS, SSH a SCP zápis, zahazuje uživatele a `.git`, normalizuje hostname a standardní porty; zachovává velikost písmen cesty a nestandardní port. Lokální cesta do identity nevstupuje. Fork a jiná repository zůstávají oddělené. Chybějící síťový remote nebo chybná konfigurace se hlásí jako chyba, bez přepnutí zápisů do lokální DB.

## Databáze

`aifactory.database.connect` nahrazuje šest míst otevírajících trace SQLite: run store, engine tracer, přehled, live watcher, review a výpočet nákladů PR. Nativní SQL, parametry, rowid, migrace a `PRAGMA data_version` zůstávají zachovány. Každé klientské připojení má vlastní serverovou SQLite connection; explicitní transakce probíhají přes více RPC na téže connection. Claim běhu využívá `BEGIN IMMEDIATE`, takže dva počítače nemohou současně claimnout stejný task. Dashboardové read-only připojení nastavuje `query_only`.

Server drží po jednom SQLite souboru na identitu projektu. Opouštěné connection po 120 s nečinnosti uzavírá, čímž vrátí otevřené transakce. Klient obnoví nečinné připojení; expirovanou transakci automaticky neopakuje. Síťové chyby se překládají do SQLite chyb používaných existujícím API. Služba nemá autentizaci; odpovídá požadovanému public read/write režimu.

Runy a chainy mají v DB identitu původního počítače. Reaping podle PID smí provádět pouze tento počítač. Stop vzdáleného běhu vrací `remote_run`, místo aby signalizoval lokální proces se stejným PID. Pause/resume zůstávají sdílenými DB požadavky. Git checkouty, filesystem zámky, agentní procesy a log soubory zůstávají lokální.

## Backlog

Tabulka `haifa_backlog` uchovává Markdown soubory včetně projektových a step indexů. První klient naplní prázdnou DB; další klienti synchronizují lokální mirror při načtení backlogu a při live pollingu. Při prvním připojení nesmí vzdálený obsah přepsat necommitnuté změny backlogu. Každý checkout si ve factory data ukládá poslední společný snapshot. Změny na různých souborech se sloučí, souběžné rozdílné úpravy stejného souboru vrátí `remote_backlog_conflict` a zachovají místní editaci.

CLI/dashboard validují add/edit/link jako doposud. Publikování všech změněných souborů je atomické a kontroluje, že DB stále odpovídá načtenému snapshotu. Zápisy lokálního mirroru procházejí existujícím journalem mainwrites a cestovým guardem. Dočasné validační stromy bez `.git` se nesynchronizují. Lokální smazání dříve synchronizovaného souboru je konflikt; týmové mazání/tombstones se nezavádí.

## Ověření

`tests/test_remote_database.py` spouští skutečný HTTP server na loopbacku a používá dva nezávislé checkouty. Pokrývá identitu remote, konfiguraci, izolaci projektů, transakce/rollback, read-only přístup, live změny, atomický souběžný claim, ochranu cizích PID, backlog konflikty, obnovu expirovaného připojení a engine tracing. Regrese se ověřují cílenými stávajícími testy konfigurace, backlogu, runů a dashboardu; dále strict mypy a Ruff. Testy nepotřebují modely ani externí DB.
