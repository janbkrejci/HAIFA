---
id: HAIFA-REFINEMENT-T12
title: Prompt agenta mimo příkazovou řádku (WinError 206 u návrhu parametrů)
status: todo
depends_on: []
---

## Zadání
Na Windows nefunguje v dashboardu **Navrhnout parametry tasku**. Agent se vůbec nespustí a běh návrhu skončí chybou `[WinError 206] The filename or extension is too long` (např. `.factory/data/workflow-advice/672351b408f045e892ea454399901eea/events.jsonl`). Navržení workflow ve stejném dashboardu funguje.

Příčina: všechny harnessy dostávají prompt jako argument příkazové řádky. Claude a pi berou uživatelský prompt jako poslední argument a systémový prompt přes `--system-prompt` (`engine/agent_cc.py`, `engine/agent_pi.py`). Codex bere systémový prompt přes `-c developer_instructions=...` a uživatelský za `--` (`harness/codex.py`, `build_command`). Windows omezuje příkazovou řádku `CreateProcess` na 32 767 znaků. Payload návrhu parametrů (`workflow/adaptive.py`, `recommend`) obsahuje `available_tasks` (až 1000 tasků, `web/workflow_advice.py`), které ořezávání kontextu nehlídá, a limit snadno překročí. Návrh workflow má menší payload, ale ořezávání mu dovolí až stovky KB, takže na stejný limit narazí s větším kontextem.

Oprava: posílat uživatelský prompt (a systémový, kde to CLI umí) jinak než na příkazové řádce, tedy přes stdin nebo soubor, u všech tří harnessů (claude, codex, pi). Jinak by stejná chyba mohla shodit i běhy tasků s dlouhým promptem. Velikost payloadu návrhu parametrů včetně `available_tasks` ať hlídá stejný rozpočet jako zbytek kontextu.

Hotovo, když:
- návrh parametrů tasku funguje na Windows i v repu s velkým backlogem,
- žádný harness nedostane prompt delší než pár KB na příkazové řádce,
- test ověří, že argv spuštěného harnessu nepřesáhne limit Windows ani s payloadem nad 32 767 znaků,
- běhy tasků i návrh workflow fungují dál na Linuxu, macOS i Windows.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
