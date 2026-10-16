---
id: GUIDE-S02-T01
title: "Backend AI průvodce: read-only konverzace nad všemi repy"
status: todo
depends_on: []
---

## Zadání
Uživatel chce z prohlížeče diskutovat o všech repech, tascích, bězích, PR, konfiguraci a knihovně a dostat odpověď opřenou o data, ne o obecnou nápovědu.

Zadání:
1. API `/api/assistant`: založení vlákna, odeslání zprávy, streamování odpovědi, seznam vláken. Vlákno pokračuje v session harnessu (`claude --resume`, `codex exec resume`, pi `--session-id`) jako retry běhu.
2. Agent běží s harnessem a modelem z nastavení počítače (nastavitelné v dashboardu), v izolovaném pracovním adresáři mimo repa, bez práva zápisu.
3. Kontext: `factory --skill`, kapitoly příručky a seznam registrovaných rep. Data čte jen přes allowlist read-only příkazů `factory` s `--json` (`task list/show/runs`, `backlog list/check`, `check`, `config show`, `library list/show`, `workflow show`) a read-only dotazy na trace DB. Žádný zápisový příkaz, žádný `.env` ani tajemství.
4. Zpráva může nést kontext obrazovky (repo, task, běh), který dashboard pošle automaticky.
5. Prompt průvodce je v semínku knihovny.

Hotovo znamená:
- Testy s fake harnessem: vlákno pokračuje v session, zakázaný příkaz se odmítne, zápis do repa selže, `.env` se do kontextu nedostane.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
