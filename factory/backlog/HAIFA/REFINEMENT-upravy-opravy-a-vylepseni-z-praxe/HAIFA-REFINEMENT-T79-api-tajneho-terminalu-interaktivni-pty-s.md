---
id: HAIFA-REFINEMENT-T79
title: "API tajného terminálu: interaktivní PTY sezení (POSIX)"
status: done
archived: true
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/web/terminal.py, aifactory/src/aifactory/web/terminal_pty.py, aifactory/src/aifactory/web/app.py, aifactory/tests/web/test_web_terminal_pty.py, aifactory/tests/web/test_web_terminal.py, docs/decisions.md]
---

## Zadání
## Zadání
Tajný terminál dnes spouští každý příkaz zvlášť přes `POST /api/terminal/exec` (`$SHELL -c`, bez TTY, stdin `DEVNULL`), viz `aifactory/src/aifactory/web/terminal.py`. Proto v něm nejde pustit vim, mc, claude, herdr ani nic jiného, co potřebuje TTY. Přidej backend interaktivního sezení nad pseudoterminálem, aby se terminál choval jako skutečný.

Kde:
- `aifactory/src/aifactory/web/terminal.py`: logika sezení. Pokud by modul příliš narostl, dej ji do nového `aifactory/src/aifactory/web/terminal_pty.py`.
- routy zaregistruj v `aifactory/src/aifactory/web/app.py` vedle stávajících `/terminal` a `/terminal/exec`. Popiš je v docstringu modulu `app.py` ve stejném stylu.
- testy v `aifactory/tests/web/test_web_terminal_pty.py`,
- doplň rozhodnutí „Tajný terminál“ v `docs/decisions.md` (sekce „Dashboard a distribuce“).

API (vše v aplikaci pro více repozitářů, JSON envelope jako dnes):
- `GET /api/terminal` vrací navíc `pty: bool`, tedy zda tento stroj umí PTY sezení (POSIX ano, Windows zatím ne).
- `POST /api/terminal/sessions` s `{cols, rows, cwd?}` spustí interaktivní shell (`$SHELL`, jinak `/bin/sh`, jako login/interaktivní shell) na slave straně PTY (stdlib `pty.openpty`/`os.openpty`, `start_new_session=True`, slave jako controlling TTY). Prostředí: `TERM=xterm-256color`, `COLORTERM=truecolor`, výchozí `cwd` je domovský adresář. Velikost nastav přes `TIOCSWINSZ`. Vrací `{id}`, kde id je náhodný token (`secrets.token_urlsafe`). Sezení se drží v `app.state`, nejvýš 4 najednou (další vrátí HTTP 429 `terminal_busy`). Na Windows zatím vrací HTTP 501 `terminal_pty_unsupported`.
- `GET /api/terminal/sessions/{id}/stream` je `StreamingResponse` (`application/octet-stream`, `Cache-Control: no-store`, `X-Accel-Buffering: no`) se surovými bajty z PTY master, jak přijdou, bez dekódování a bez bufferování po řádcích. Na sezení smí běžet jen jeden stream (druhý vrátí 409 `terminal_attached`). Když shell skončí, stream se uzavře.
- `POST /api/terminal/sessions/{id}/input` s `{data: str}` zapíše `data` (UTF-8) do PTY master. Klávesy jako Ctrl+C a Esc přijdou jako bajty a signály řeší line discipline PTY, ne server.
- `POST /api/terminal/sessions/{id}/resize` s `{cols, rows}` nastaví velikost (`TIOCSWINSZ`) a pošle skupině popředí `SIGWINCH` (jádro to při změně udělá samo).
- `DELETE /api/terminal/sessions/{id}` ukončí sezení.
- Když se klient odpojí od streamu, nebo když shell skončí, server ukončí celou skupinu procesů (`oscompat.kill_group`), zavře master FD a sezení smaže. Neznámé id vrací 404 `terminal_session_not_found`.
- Neplatné `cols`/`rows` (mimo 1–1000), neexistující `cwd` nebo nevalidní tělo vrací 400 `usage_error`.

Tvrdá omezení (jde o vzdálené spouštění kódu):
- Všechny nové endpointy používají stejnou kontrolu `_enabled` jako dnes: loopback `allowed_hosts` a zároveň loopback klient, jinak 403 `terminal_disabled`.
- POST a DELETE projdou stávajícím `WriteGuardMiddleware`. Nevynechávej ho.
- Nic se neloguje do trace DB ani do repa a vstup ani výstup se neukládá.
- Žádný celkový časový limit sezení (vim smí běžet hodiny). Ukončení řídí jen odpojení, `DELETE` nebo konec shellu.
- Žádná nová závislost v `pyproject.toml`, žádné WebSockety (uvicorn je instalovaný bez nich).
- Čtení z master FD nesmí blokovat event loop: použij `loop.add_reader` nebo neblokující FD, ne synchronní `os.read` v korutině.

Mimo rozsah: frontend, Windows (samostatný task), odstranění stávajícího `POST /api/terminal/exec`. Stávající testy terminálu uprav jen tehdy, když je rozbije nové pole `pty` v `GET /api/terminal`.

Hotovo znamená:
- `aifactory/tests/web/test_web_terminal_pty.py` prochází na POSIX (na Windows je přeskočený) a ověřuje: vytvoření sezení a čtení streamu; po vstupu `echo pty-ok\r` se ve výstupu objeví `pty-ok`; `python3 -c "import sys;print(sys.stdin.isatty())"` vypíše `True`; po resize vrátí `stty size` nové rozměry; vstup `\x03` přeruší běžící `sleep 100` a shell dál odpovídá; `DELETE` i odpojení streamu ukončí proces (pid už neběží); 403 `terminal_disabled` pro host i klienta mimo loopback; 403 `cross_origin` s cizím `Origin`; 404 pro neznámé id; 400 pro neplatné rozměry; limit počtu sezení.
- `GET /api/terminal` vrací pole `pty`.
- Stávající `aifactory/tests/web/test_web_terminal.py` a ostatní webové testy dál procházejí.
- Docstring `app.py` a `docs/decisions.md` popisují PTY sezení a omezení na loopback.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-25 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/168 · náklady $0.00
