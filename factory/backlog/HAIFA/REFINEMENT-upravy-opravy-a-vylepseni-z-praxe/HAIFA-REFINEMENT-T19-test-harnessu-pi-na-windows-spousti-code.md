---
id: HAIFA-REFINEMENT-T19
title: Test harnessu pi na Windows spouští codex.exe a pi bez PI_PATH nevidí modely
status: todo
depends_on: []
---

## Zadání
Na Windows tlačítko Test v nastavení harnessů u `pi` vždy selže: „Harness skončil s chybou (exit 2). Zkontrolujte přihlášení a dostupnost modelu.“ Model (`nous-portal-api-key/meituan/longcat-2.5-preview:free`, thinking `high`) přitom z konzole funguje. Neúspěšný test pak brání nastavit `pi` jako výchozí harness a zobrazit ho v topbaru.

Příčina: `harness/probe.py:102` volá u všech harnessů `launch_command` z `harness/codex.py`. Ta na Windows najde npm shim (`pi.cmd`) a ve stejné složce `npm` dohledá `node_modules/@openai/.../codex.exe`, takže test spustí Codex s argumenty pro `pi` (`error: unexpected argument '--provider' found`, exit 2).

Související: `engine/agent_pi.py:33` má výchozí `PI_PATH = "pi"`. Na Windows `subprocess.run(["pi", ...])` bez shellu shim `pi.cmd` nenajde (`FileNotFoundError`), `_pi_catalog()` chybu spolkne a dashboard nevidí žádné modely. Obchvat byl `PI_PATH=...\npm\pi.cmd` v `$HAIFA_HOME/env`.

Zadání:
1. `probe.py` volá `launch_command` jen pro Codex, `pi` spouští stejnou binárkou jako běh (`agent_pi.PI_PATH`).
2. Výchozí `PI_PATH` na Windows najde npm shim (`shutil.which("pi")` vrátí `pi.cmd`), takže výpis modelů i běh fungují bez nastavené proměnné.

Hotovo znamená:
- Test: na Windows (nebo se simulovaným `os.name == "nt"` a shimem `pi.cmd` vedle `codex.exe`) sestaví probe pro `pi` příkaz s `pi`, ne s `codex.exe`.
- Test: bez `PI_PATH` vrátí `_pi_catalog()` modely přes shim `pi.cmd`.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
