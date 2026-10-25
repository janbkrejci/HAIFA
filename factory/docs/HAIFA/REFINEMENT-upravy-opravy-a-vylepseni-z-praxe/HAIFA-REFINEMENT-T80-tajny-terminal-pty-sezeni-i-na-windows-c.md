# Tajný terminál: PTY na Windows

Windows používá ConPTY z pywinpty; závislost `pywinpty>=2,<4` má marker
`sys_platform == 'win32'` a na POSIX se neinstaluje. Import winpty probíhá pouze
ve windowsové větvi. `GET /api/terminal` hlásí `pty: true`, pokud lze winpty
naimportovat; bez něj vytvoření sezení vrátí 501 `terminal_pty_unsupported`.

Shell určuje `%COMSPEC%` s náhradou `cmd.exe`; stejná cesta se vrací v informacích
terminálu a používá pro spuštění. Sezení přebírá cwd, rozměry a proměnné
`TERM=xterm-256color` a `COLORTERM=truecolor`. Čtení, zápis a resize běží mimo
event loop. ConPTY poskytuje text, který server streamuje jako UTF-8 bajty.

DELETE, odpojení streamu i konec shellu odstraní sezení a uvolní transport.
Při ukončení se nejdřív přes `oscompat.kill_group` zabije strom procesů,
pak zavolá `terminate(force=True)`. Uzavření socketu uvolní blokované čtení.
Počet sezení zůstává omezen na čtyři a stream má jediného odběratele.
Loopback kontrola, WriteGuard a zákaz ukládání vstupu či výstupu zůstávají zachovány.

## Ověření

Z adresáře `aifactory`:

```sh
uv lock --check
uv run pytest tests/web/test_web_terminal.py tests/web/test_web_terminal_pty.py tests/web/test_web_terminal_pty_windows.py -n0
```

Windowsové testy používají skutečné ConPTY a ověřují výstup `echo pty-ok`,
rozměry, ukončení shellu i potomka po DELETE a odpojení včetně blokovaného
odesílání, přirozený konec shellu, limit sezení a ochrany přístupu.
Na POSIX se přeskočí; samostatný test s blokujícím transportem zde ověřuje
windowsovou větev bez instalace pywinpty. POSIX PTY testy dál používají skutečné PTY.
