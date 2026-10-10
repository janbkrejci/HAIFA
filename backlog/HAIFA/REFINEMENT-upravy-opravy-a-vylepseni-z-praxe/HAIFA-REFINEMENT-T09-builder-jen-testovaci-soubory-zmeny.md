---
id: HAIFA-REFINEMENT-T09
title: "Builder pouští jen testovací soubory ke své změně, žádné adresáře"
status: todo
workflow: build-test-review
depends_on: []
writes: [aifactory/]
---

## Zadání
Builder si podle promptu smí pustit testy, které pokrývají jeho změnu („by explicit test file or project“). Formulace připouští celé adresáře, takže builder v běhu ce9338e8 (HAIFA-REFINEMENT-T08) pouštěl `pytest tests/library tests/config tests/workflow …`. Kontroly, kterým se věří, vybírá tester a spouští krok test. Builder má jen rychle ověřit vlastní změnu.

Where: prompt builderu v seedu `aifactory/src/aifactory/seed/agents/builder/system.md` (případně `user.md`), testy seedu v `aifactory/tests/`, pokud kontrolují text nebo verzi položky.

Done means:
- Prompt builderu povoluje jen explicitní testovací soubory (případně jednotlivé testy), které builder změnil nebo které přímo pokrývají změněný modul. Celé adresáře, spuštění bez cesty a příkazy celé sady (`just check`, `just check-scoped`, `just test`, `just e2e`, `just web-test`, `pytest` nebo `bun run test` bez souboru) jsou zakázané.
- Typecheck a lint jen nad změněnými soubory.
- Věta o kroku test odpovídá chování po HAIFA-REFINEMENT-T08 (test step pustí všechny kontroly testera a vrátí každou selhanou).
- Testy seedu a knihovny projdou s novou verzí položky builder.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: `.factory/prompts/builder/` repa HAIFA (chráněné, srovná operátor přes knihovnu), prompty ostatních agentů, technické vynucení zákazu v harnessu.

Pevná omezení:
- `.factory/`, `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
