---
id: HAIFA-REFINEMENT-T08
title: "Test step: všechny kontroly bez zastavení na první chybě, řazení od nejrychlejší"
status: todo
workflow: build-test-review
depends_on: []
writes: [aifactory/]
---

## Zadání
Test step dnes pouští kontroly z plánu testera postupně a u první selhané skončí (`testing/executor.py`, `break` po selhání). Builder tak dostane jen první chybu a nezávislé chyby (lint, typecheck, testy) opravuje v několika kolech smyčky `fix` s `max: 3`. Prompt testera navíc tvrdí, že test step vrací všechny chyby, a pořadí kontrol nepředepisuje.

Where: `aifactory/src/aifactory/testing/` (`model.py`, `executor.py`), prompt testera v `aifactory/src/aifactory/seed/agents/tester/` (`system.md`, `user.md`), schéma envelope testera, zobrazení kontrol v dashboardu a těle PR, pokud ukazují nespuštěné kontroly, testy v `aifactory/tests/`.

Done means:
- Test step spustí všechny kontroly plánu i po selhání některé z nich a builderovi vrátí výstup každé selhané kontroly.
- `Check` má volitelné `stop_on_fail` (výchozí `false`). Selhání takové kontroly zastaví zbylé kontroly (předpoklad: build, instalace, sběr testů). Nespuštěné kontroly jsou ve výsledku uvedené jako nespuštěné s důvodem.
- Sdílený časový limit kroku platí dál. Kontrola, na kterou nezbyl čas, je ve výsledku nespuštěná s důvodem jako dnes.
- Prompt testera: kontroly seřadit od nejkratší očekávané doby po nejdelší (lint a typecheck, cílené testy, širší sady), `stop_on_fail` jen u kontroly, bez které ostatní nemají smysl. Věta o vracení všech chyb odpovídá novému chování.
- Triage testera (`failed_test`) dostane všechny selhané kontroly.
- Starší plány bez `stop_on_fail` se načtou a běží.
- Testy (pytest): dvě nezávisle selhané kontroly vrátí obě chyby, `stop_on_fail` zastaví zbylé a označí je nespuštěné, vyčerpaný limit, starý plán bez pole.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: paralelní běh kontrol, měření a ukládání dob kontrol, změny workflow.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
