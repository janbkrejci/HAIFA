# Interaktivní PTY API tajného terminálu (POSIX)

Globální aplikace pro více repozitářů nabízí vedle samostatného `/api/terminal/exec` také trvalé interaktivní shellové sezení. `GET /api/terminal` obsahuje `pty`, které na POSIX hlásí podporu, na Windows `false`.

| Metoda a cesta | Tělo / výsledek |
| --- | --- |
| `POST /api/terminal/sessions` | `{cols, rows, cwd?}` → JSON envelope s `{id}` |
| `GET /api/terminal/sessions/{id}/stream` | Surové bajty `application/octet-stream`, jediný odběratel |
| `POST /api/terminal/sessions/{id}/input` | `{data: str}`, zápis UTF-8 včetně řídicích znaků |
| `POST /api/terminal/sessions/{id}/resize` | `{cols, rows}`, ioctl TIOCSWINSZ a automatický SIGWINCH |
| `DELETE /api/terminal/sessions/{id}` | Ukončení sezení a úklid |

Rozměry musí být celá čísla 1–1000, cwd existující adresář; výchozí cwd je domov. Shell se vybírá z `$SHELL`, jinak `/bin/sh`, a běží s `-il`, `TERM=xterm-256color`, `COLORTERM=truecolor`. Spouštěcí Python proces po `start_new_session=True` převezme slave jako controlling TTY přes TIOCSCTTY a nahradí se shellem. Nevzniká nová závislost ani WebSocket.

Master FD je neblokující. `add_reader` předává jednotlivé bloky bajtů, bez dekódování a bez čekání na konec řádku. Omezený výstupní buffer zastaví čtení při pomalém odběrateli. Zápis zpracovává částečné zápisy a při zaplnění PTY čeká přes `add_writer`; event loop zůstává volný. Ctrl+C zpracovává line discipline a job control terminálu.

Sezení žijí pouze v `app.state`. Vytváření je serializované, limit jsou čtyři souběžná sezení. Konec shellu, odpojení streamu, DELETE nebo vypnutí aplikace ukončí skupinu shellu i skupinu popředí přes `oscompat.kill_group`, zavře master a odstraní sezení. Sezení nemá časový limit. Příkazy, vstup ani výstup se nepersistují ani netrasují.

Všechny routy vyžadují současně loopback `allowed_hosts` a loopback klienta. POST i DELETE procházejí běžným WriteGuardMiddleware. Chyby používají JSON envelope: 403 `terminal_disabled` / `cross_origin`, 400 `usage_error`, 404 `terminal_session_not_found`, 409 `terminal_attached`, 429 `terminal_busy`, 501 `terminal_pty_unsupported` na Windows.

Regrese ověřují skutečný shell, echo, isatty, stty size, Ctrl+C, binární výstup bez newline, ukončení shellu i procesu popředí, odpojení při zablokovaném odesílání, zaplněný vstup, shutdown, souběžný limit, validaci a bezpečnostní kontroly. POSIX soubor se na Windows přeskakuje. Frontend a stávající exec API zůstávají mimo rozsah změny.

Ověření: `just pytest tests/web/test_web_terminal_pty.py tests/web/test_web_terminal.py -n0`; lint, formátování a mypy cíleně na změněné Python soubory. Hledání přímých volajících ve všech testech odhalilo pouze stávající terminálové testy a browser test obrazovky terminálu; obrazovka se nemění, browser test není nutný.
