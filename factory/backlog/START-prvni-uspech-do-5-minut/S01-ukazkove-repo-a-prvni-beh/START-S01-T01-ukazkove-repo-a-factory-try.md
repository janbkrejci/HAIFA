---
id: START-S01-T01
title: Ukázkové repo a factory try
status: todo
depends_on: []
---

## Zadání
Nový uživatel dnes musí projít instalaci, přihlášení `gh`, přidání vlastního repa a ruční psaní tasku, než uvidí první výsledek.

Zadání:
1. V balíčku je malé ukázkové repo (jednoduchá aplikace s testy a jasným testovacím příkazem) s backlogem tří tasků rostoucí velikosti, napsaných tak, aby je běžný model zvládl na první pokus.
2. `factory try [ADRESÁŘ]` ho vytvoří (výchozí adresář v domově HAIFA), udělá `git init`, nainstaluje `.factory/` s `git_provider: local`, takže nepotřebuje GitHub ani `gh`, a zaregistruje ho v dashboardu.
3. Opakované spuštění nad existujícím adresářem nic nepřepíše a vrátí jeho cestu.

Hotovo znamená:
- Test: `factory try` vytvoří repo, `factory check` v něm nehlásí chyby repa, backlog je platný.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
