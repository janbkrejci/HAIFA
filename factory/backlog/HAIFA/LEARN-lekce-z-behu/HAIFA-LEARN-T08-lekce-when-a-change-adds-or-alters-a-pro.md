---
id: HAIFA-LEARN-T08
title: "Lekce: When a change adds or alters a protection or limit (write guards, timeouts, proces…"
status: done
workflow: build-review
depends_on: []
related: [HAIFA-TODO-T26, HAIFA-REFINEMENT-T76]
writes: [AGENTS.md]
---

## Zadání
Zapiš do `AGENTS.md` pravidlo z lekce `L143c4f84`, kterou factory našla ve výtkách opakovaných v bězích:

> When a change adds or alters a protection or limit (write guards, timeouts, process kills), add a regression test for its failure path, such as an implicit default or a blocked send, not only the happy path.

Pravidlo formuluj stručně, zařaď ho tam, kam v souboru patří, a nenech ho odporovat tomu, co tam už je. Jiné soubory neměň.

Hotovo znamená:
- Pravidlo je v `AGENTS.md`.

### Důkazy

Výtky z 2 běhů, ze kterých lekce vznikla:

- běh `421cf301`, task `HAIFA-TODO-T26` (review): Do aifactory/tests/run/test_guard_protected_writes.py přidat test tasku bez writes na všech úrovních backlogu: agent s writes: null vytvoří chráněný prompt, hlídač musí vrátit writes_violation, uvést cestu a soubor odstranit. Zahrnout test do aktualizovaného testovacího plánu.
- běh `421cf301`, task `HAIFA-TODO-T26` (review): test plan fits the change: Dodaný log potvrzuje exit 0 pro just lint, just typecheck a 19 cílených testů. Rozsah není zbytečně široký, ale chybí regresní test ochrany při implicitních writes. aifactory/tests/run/test_task_run.py:384 testuje default pouze zápisem do nechráněného docs/endpoint.md.
- běh `c16622d8`, task `HAIFA-REFINEMENT-T76` (review): Do aifactory/tests/web/test_web_terminal.py přidejte regresi s krátkým timeoutem a ASGI send zablokovaným na timeout hlášce. Před odblokováním nebo odpojením ověřte, že příkaz i jeho dlouho běžící potomek skončily.
- běh `c16622d8`, task `HAIFA-REFINEMENT-T76` (review): test plan fits the change: Rozsah kontrol je přiměřený a všechny čtyři příkazy skončily kódem 0. Chybí však regrese timeoutu při blokovaném odesílání timeout hlášky; test_timeout na řádcích 134–148 odpověď ihned spotřebuje a nalezenou chybu nezachytí.

<!-- factory: lesson=L143c4f84 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-01 · workflow build-review · PR https://github.com/janbkrejci/HAIFA/pull/187 · náklady $0.00
