# HAIFA-REFINEMENT-T82 — Prohlížečový test interaktivního terminálu

Test používá dodaný statický dashboard, skutečný server na `127.0.0.1` a PTY shell. Sekvence Control, Shift, Control, Shift otevře dialog s viditelným `.xterm` a fokusem v jeho textarea. Výstup se ověřuje v `.xterm-rows`.

Scénář ověřuje výstup `echo`, zachování pracovního adresáře, `sys.stdin.isatty()` a interaktivní Python program se dvěma voláními `input()`. První přijme `q`, druhé znak Esc; výstup s hodnotou 27 dokládá předání Esc programu a dialog zůstane otevřený. Python se spouští přes `sys.executable` testovacího procesu. Markery výsledků nejsou doslova v příkazech, aby nestačilo jejich echo.

Ctrl+C přeruší `sleep 100` a nový příkaz musí vypsat vlastní marker. Na Windows čekání zajišťuje Python `time.sleep(100)`. Dialog zavře znovu tajná sekvence. Samostatný scénář zachovává ověření, že vložené A sekvenci přeruší; stávající test vimu zůstává zachován.

Fixture před otevřením dashboardu ověří úspěšnou odpověď `GET /api/terminal`. Na Windows při `pty: false` test přeskočí. POSIX shell je izolovaný `/bin/sh`. Testy nevyžadují živý model ani externí službu.

Rozsah implementace je omezen na tento prohlížečový test a dokumentaci úkolu. Backend, frontend a ostatní prohlížečové testy se nemění.
