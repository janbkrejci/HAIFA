---
id: HAIFA-REFINEMENT-T80
title: "Tajný terminál: PTY sezení i na Windows (ConPTY přes pywinpty)"
status: todo
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T79]
writes: [aifactory/pyproject.toml, aifactory/uv.lock, aifactory/src/aifactory/web/terminal.py, aifactory/src/aifactory/web/terminal_pty.py, aifactory/tests/web/test_web_terminal_pty_windows.py, aifactory/tests/web/test_web_terminal_pty.py, docs/decisions.md]
---

## Zadání
## Zadání
PTY sezení z HAIFA-REFINEMENT-T79 dnes na Windows vrací 501 `terminal_pty_unsupported`. Zprovozni je i na Windows přes ConPTY, aby tam šlo pustit např. claude, herdr nebo vim z Git for Windows.

Kde:
- `aifactory/pyproject.toml`: přidej závislost `pywinpty` jen pro Windows (`pywinpty>=2,<4; sys_platform == 'win32'`, horní mez podle aktuální verze) a aktualizuj `aifactory/uv.lock` (`uv lock`).
- `aifactory/src/aifactory/web/terminal.py` / `terminal_pty.py`: windowsová implementace sezení se stejným API. Spusť `winpty.PtyProcess.spawn` se shellem `%COMSPEC%` (případně `powershell.exe`, pokud je to výchozí shell uživatele, a ten pak vrať i v `GET /api/terminal`) a se stejným `cwd`, `cols`/`rows` a `TERM`. Čtení probíhá v threadu přes `asyncio.to_thread`/`anyio.to_thread`, resize přes `setwinsize`, ukončení přes `terminate(force=True)` a `oscompat.kill_group`.
- `GET /api/terminal` vrací na Windows `pty: true`, když jde `winpty` naimportovat.
- testy v `aifactory/tests/web/test_web_terminal_pty_windows.py` (na POSIX přeskočené). Pokud posixové testy v `aifactory/tests/web/test_web_terminal_pty.py` dnes kontrolují 501 na Windows, uprav je.
- doplň do `docs/decisions.md` jednu větu o ConPTY na Windows.

Tvrdá omezení: stejná jako v T79 (loopback, WriteGuard, nic se neukládá). Na POSIX se chování nemění a `pywinpty` se tam neinstaluje. Import `winpty` je jen uvnitř windowsové větve.

Mimo rozsah: frontend, POSIX implementace.

Hotovo znamená:
- Na Windows prochází `test_web_terminal_pty_windows.py`: vytvoření sezení, `echo pty-ok` ve výstupu, resize bez chyby a ukončení procesu po `DELETE` i po odpojení streamu.
- Na POSIX jsou tyto testy přeskočené a `aifactory/tests/web/test_web_terminal_pty.py` dál prochází.
- `uv lock --check` je v pořádku a `pywinpty` má marker `sys_platform == 'win32'`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
