---
id: HAIFA-S90-T04
title: OB4 Azure DevOps proti skutečnému repu
status: todo
assignee: human
workflow: simple-sdlc
depends_on: []
related: [HAIFA-S09-T01, HAIFA-S09-T02]
writes: [aifactory/src/aifactory/providers/azure.py, aifactory/tests/providers/, aifactory/validation/, aifactory/tests/validation/, justfile]
---

## Zadání
Ověř provider Azure DevOps (D8) proti skutečnému repu. Dnes je ověřený jen proti falešnému `az` (`aifactory/tests/providers/az_fake.py`).

Podmínka: spustit, až bude Azure DevOps k dispozici (sandbox repo na Azure DevOps, přihlášené `az` s rozšířením `azure-devops`).

Validace (`just validate`, `aifactory/validation/`) dnes umí jen `--remote local|github`. Pro tento úkol přidej režim `--remote azure` po vzoru `github`:
- sandbox repo se zadá proměnnou prostředí, stejně jako `HAIFA_SANDBOX_REPO` pro GitHub;
- preflight ověří přihlášené `az` a dostupnost sandboxu;
- base větev `haifa-validate/<stamp>` vznikne ze sandboxu a jeho výchozí větev se nezmění.

Scénáře R2 (dva paralelní běhy a konflikt), R3 (vazby, schválení, merge mimo factory, `backlog sync`, vrácený a zavřený PR) a F2 (akceptace přes CLI) mají na Azure DevOps stejné kontroly jako na GitHubu. Každý rozdíl ve chování skutečného `az` proti falešnému (výstup JSON, stavy PR, chybové kódy, schválení a merge) oprav v `providers/azure.py` a promítni ho do `az_fake.py` a do testů provideru, aby falešné `az` odpovídalo skutečnému.

Done means:
- `just validate --remote azure --only R2,RESOLVE,R3,F2` projde scénáři R2, R3 a F2 (RESOLVE jen jako předpoklad pro R2/R3, pokud ho vyžadují); výsledky jsou uložené v `aifactory/validation/results/`.
- Rozdíly proti falešnému `az` jsou opravené v provideru a jeho testech a `just test` projde.
- `aifactory/validation/README.md` popisuje režim azure: co potřebuje a jak po běhu uklidit PR a větve.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
