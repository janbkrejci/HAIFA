---
id: HAIFA-REFINEMENT-T76
title: "API tajného terminálu: spouštění příkazů na stroji dashboardu jen přes loopback"
status: todo
workflow: build-test-review
depends_on: []
writes: [aifactory/src/aifactory/web/terminal.py, aifactory/src/aifactory/web/app.py, aifactory/tests/web/test_web_terminal.py, docs/decisions.md]
---

## Zadání
Přidej do dashboardu (`factory obs`) backend skrytého terminálu. Ten spustí shellový příkaz na stroji, kde dashboard běží, a jeho výstup vrací průběžně.

Kde:
- nový modul `aifactory/src/aifactory/web/terminal.py`,
- routy zaregistruj v `aifactory/src/aifactory/web/app.py` v aplikaci pro více repozitářů (ne pod `/api/repos/{id}/`) a endpointy popiš v docstringu modulu `app.py` (stejným stylem jako u průvodce),
- testy v `aifactory/tests/web/test_web_terminal.py`,
- krátké rozhodnutí v `docs/decisions.md` v sekci „Dashboard a distribuce“ (tajný terminál, jen loopback, bez přihlášení).

API:
- `GET /api/terminal` vrací `{enabled: bool, cwd, shell}`. `cwd` je výchozí adresář, tedy domovský adresář uživatele. `shell` je shell, který se použije.
- `POST /api/terminal/exec` s JSON `{command: str, cwd?: str}` spustí `command` v shellu systému v adresáři `cwd` (výchozí je z `GET`). Na POSIX je to `$SHELL`, jinak `/bin/sh -c`, na Windows `cmd /c`. Pro rozdíly mezi systémy použij `aifactory.oscompat`, např. `NEW_GROUP` a `kill_group`. Odpověď je `StreamingResponse` NDJSON s řádky `{"type":"out","stream":"stdout"|"stderr","text":...}` a nakonec `{"type":"exit","code":int,"cwd":str}`. stdin je `DEVNULL`. Výstup se dekóduje jako UTF-8 s `errors="replace"`.
- Příkaz `cd <cesta>` (i samotné `cd`) se nespouští, server ho vyřeší sám. Vrátí `exit` s novým absolutním `cwd`. Když adresář neexistuje, vrátí kód 1 a hlášku na stderr. Klient si `cwd` drží a posílá ho s dalším příkazem.
- Když klient zavře spojení (zrušený fetch) nebo uplyne limit `TERMINAL_TIMEOUT_S` (např. 600 s), server ukončí proces i s jeho potomky.
- Prázdný `command` nebo neexistující `cwd` vrací HTTP 400 `usage_error`.

Tvrdá omezení (bezpečnost, jde o vzdálené spouštění kódu):
- Terminál je povolený jen tehdy, když dashboard poslouchá na loopbacku (`web_server.LOOPBACK`, tedy `allowed_hosts` jen loopback) a zároveň je klient požadavku (`request.client.host`) loopback. Jinak `GET` vrací `enabled: false` a `POST /api/terminal/exec` vrací HTTP 403 `terminal_disabled`. Při `--host 0.0.0.0` nebo s `HAIFA_DASH_HOST` mimo loopback terminál nejde použít nikdy.
- `POST` prochází stávajícím `WriteGuardMiddleware` (Origin, Sec-Fetch-Site, JSON). Nevynechávej ho.
- Nic se neloguje do trace DB ani do repa a příkazy se neukládají.

Mimo rozsah: frontend a klávesová zkratka (samostatný task), interaktivní programy s TTY (vim, top), pty a websockets, nová závislost v `pyproject.toml`, úpravy stávajících testů.

Hotovo znamená:
- `aifactory/tests/web/test_web_terminal.py` prochází a ověřuje: výstup `echo` přijde jako `out` a `exit` s kódem 0; nenulový exit kód se vrátí; `cd` do existujícího adresáře změní `cwd`, do neexistujícího vrátí kód 1; 403 `terminal_disabled` pro aplikaci vytvořenou s hostem mimo loopback a pro klienta mimo loopback; 403 `cross_origin` s cizím `Origin`; 400 pro prázdný příkaz; dlouhý příkaz se po limitu (v testu zkráceném) ukončí.
- Stávající webové testy dál procházejí.
- Docstring `app.py` a `docs/decisions.md` popisují endpointy a omezení na loopback.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
