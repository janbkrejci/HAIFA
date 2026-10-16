---
id: GUIDE-S02-T01
title: "Backend AI průvodce: read-only konverzace nad všemi repy"
status: done
depends_on: []
related: [GUIDE-S02-T02, GUIDE-S02-T03, GUIDE-S01-T01]
writes: [aifactory/src/aifactory/web/, aifactory/src/aifactory/harness/, aifactory/src/aifactory/engine/, aifactory/src/aifactory/seed/, aifactory/src/aifactory/library/, aifactory/tests/]
---

## Zadání
Uživatel chce z prohlížeče diskutovat o všech repech, tascích, bězích, PR, konfiguraci a knihovně. Odpověď má být opřená o data, ne o obecnou nápovědu. Tento task dodává jen backend (API, běh agenta, prompt). Panel v dashboardu řeší GUIDE-S02-T02 a navrhování akcí GUIDE-S02-T03.

Zadání:
1. API `/api/assistant`: založení vlákna, odeslání zprávy, streamování odpovědi a seznam vláken. Vlákno pokračuje v session harnessu (`claude --resume`, `codex exec resume`, pi `--session-id`) stejně jako retry běhu. Zápisové požadavky API procházejí stávající ochranou (Origin, Sec-Fetch-Site, JSON).
2. Agent běží s harnessem a modelem z nastavení počítače. Volba se řeší stejně jako u stávajícího poradce (`harness_settings`, nastavitelné v dashboardu). Běží v izolovaném pracovním adresáři mimo repa a nemá právo zápisu.
3. Kontext tvoří `factory --skill`, kapitoly příručky a seznam registrovaných rep. Data agent čte jen přes allowlist read-only příkazů `factory` s `--json`: `task list/show/runs`, `backlog list/check`, `check`, `config show`, `library list/show`, `workflow show`. K tomu smí dělat read-only dotazy na trace DB. Žádný zápisový příkaz, žádný `.env` ani jiná tajemství.
4. Zpráva může nést kontext obrazovky (repo, task, běh), který dashboard pošle automaticky. Backend ho přijme a předá agentovi.
5. Prompt průvodce je v semínku knihovny, stejně jako ostatní agenti v `seed/agents/`.

Hotovo znamená:
- Testy s fake harnessem ověří, že:
  - druhá zpráva ve vlákně pokračuje ve stejné session harnessu,
  - příkaz mimo allowlist (např. `factory task run`, `factory config set`) se odmítne,
  - pokus agenta o zápis do registrovaného repa selže a repo zůstane beze změny,
  - obsah `.env` ani jiných tajemství se do kontextu agenta nedostane,
  - kontext obrazovky (repo/task/běh) ze zprávy se dostane do promptu.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/69 · náklady $6.34
