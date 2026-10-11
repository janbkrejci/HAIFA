---
id: HAIFA-S01-T35
title: "Dashboard a běhy poznají, že se pod nimi změnil kód HAIFA"
status: done
depends_on: []
---

## Zadání
HAIFA staví sama sebe, takže se její kód mění pod běžícími procesy. Dashboard (`factory obs`) běží s kódem z doby spuštění: po merge HAIFA-S03-T08 schvaloval bez deníku posunů a shodil tím souběžný běh HAIFA-S03-T09, po merge HAIFA-S03-T13 hrozil pád na novém `roles.yaml`. Běh HAIFA-S03-T14, který začal před merge HAIFA-S03-T13, na konci spadl s `invalid_config: … code_steps.rebuild: unknown code step 'rebuild'`: kód v paměti byl starý, datové soubory balíčku na disku už nové.

Where: `aifactory/src/aifactory/web/` (server, API, otisk kódu), banner v `aifactory/web/src/`, načítání dat balíčku (`aifactory/src/aifactory/engine/role_registry.py`, výchozí workflow a role v `aifactory/src/aifactory/defaults/` a `engine/defaults/`), testy (pytest, vitest), build v `aifactory/src/aifactory/web/static/`.

Done means:
- Dashboard si při startu zapamatuje otisk svého kódu (zdroje a datové soubory balíčku `aifactory`) a průběžně ho porovnává s diskem. Když se liší, ukáže banner „Kód HAIFA se změnil, restartuj dashboard“ s tlačítkem, které server restartuje na stejném portu.
- Dokud dashboard běží se starým kódem, zápisové akce (schválení, vrácení, resolve, zápisy backlogu, spuštění běhu) odmítne se srozumitelnou hláškou a odkazem na restart. Čtení funguje dál.
- Běh (`factory task run`, `resolve`, `--auto`) použije datové soubory balíčku (výchozí role, workflow a code steps) načtené při svém startu. Změna balíčku během běhu ho neshodí.
- Testy: změna otisku zapne banner a zablokuje zápisové akce, restart obnoví provoz, běh po změně datového souboru balíčku doběhne se staršími daty.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: automatický restart bez potvrzení, aktualizace HAIFA z knihovny nebo bundlu.

Pevná omezení:
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · implementováno přímo orchestrátorem, bez běhu factory
