---
id: HAIFA-REFINEMENT-T88
title: "Oprava po rebase nesmí měnit soubory ze writes bez konfliktu, retry se zablokuje"
status: todo
depends_on: []
writes: [aifactory/src/aifactory/run/, aifactory/tests/]
---

## Zadání
Retry po rebase se zablokuje, když rebase rozbije chování v souboru, který nemá textový konflikt. Fáze `resolve` i oprava po testech (`fix_N`) smí měnit jen soubory s konfliktem, ne celé `writes` úlohy. Jediná cesta ven je nový běh, který zahodí historii běhu.

## Současný stav (naměřeno v NEO_HEF 2026-10-26, factory 0.1.537)

- Běh `7f9d9512` úlohy `ROB-TODO-T46`: rebase na develop dal konflikt jen v `using` hlavičce `RobStartupSteps.cs`. Testy `RobStartupSequenceTests` (přibyly v develop) se pak 3× zasekly na 60s STA timeoutu, protože T46 nově čte geometrii okna při startu shellu.
- `fix_1` správně určil opravu v `src/modules/ROB/Fenix.ROB.Tests/Startup/RobStartupSequenceTests.cs` a skončil `needs writes`.
- Soubor jsem přidal do `writes` (`factory task edit --writes`, commit do base). Další `task retry` znovu rebasoval, builder v `resolve` soubor upravil a fáze padla na `permission_breach`: „task ROB-TODO-T46 may only change ['…/RobStartupSteps.cs'] inside its worktree“.
- `--allow-writes` nepomůže, soubor už ve `writes` je. Zpráva `needs writes` tedy vede na cestu, která nefunguje.

## Co udělat

1. Po rebase povolit opravě po testech (`fix_N`) celé `writes` úlohy, nejen soubory s konfliktem. `resolve` může zůstat jen na souborech s konfliktem.
2. Když oprava po rebase nahlásí cestu, která už ve `writes` je, nehlásit `needs writes`, ale povolit ji (nebo říct přesně, co má operátor udělat).
3. Pokud se zúžení má zachovat, ukázat v dashboardu a v chybě, že další krok je nový běh (`factory task run`), ne retry.

## Hotovo znamená

- Retry po rebase dokáže opravit test v souboru ze `writes` bez textového konfliktu.
- Test pokrývá rebase bez konfliktu v souboru, který oprava potřebuje změnit.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
