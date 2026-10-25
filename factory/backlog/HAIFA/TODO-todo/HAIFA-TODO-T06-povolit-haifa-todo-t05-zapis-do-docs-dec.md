---
id: HAIFA-TODO-T06
title: Povolit HAIFA-TODO-T05 zápis do docs/decisions.md (writes v front matter)
status: done
archived: true
depends_on: []
related: [HAIFA-TODO-T05]
---

## Zadání
Člověk (nebo `factory backlog` mimo běh) musí do front matter HAIFA-TODO-T05 přidat `writes: [docs/decisions.md]` (případně spolu s aifactory/ a justfile, pokud se `writes` nesčítá s děděnou hodnotou) a task pustit znovu. Fakta pro rozhodnutí jsem ověřil v kódu: help `factory task approve` v aifactory/src/aifactory/cli.py ř. 1884–1893, review/flow.py ř. 270–302 a review/automerge.py ř. 19–33. Approve i auto-merge přidají commit `status: done` a čekají na CI checky tohoto merge headu. Červené checky spustí na větvi PR nejvýš `ci.CI_FIX_ROUNDS` (= 2) běhů ci-fix (`started_by auto-ci-fix`) a po každém se znovu čeká. Když checky zůstanou červené nebo neskončí, PR zůstane otevřený a důvod se uloží do `task_prs.auto_merge_error`. Azure pošle schvalovací hlas po posledním pushi a před merge, local a GitHub self-approval review neposílají. To, že dashboard na GitHubu schvaluje na pozadí, je ještě potřeba ověřit ve web/. Novou odrážku `**Approve a auto-merge čekají na CI:**` je třeba napsat česky ve stylu ostatních. Pokud v docs/decisions.md existuje starší rozhodnutí, že auto-merge CI jen zkontroluje, nahradí ho. V aktuálním souboru jsem ho nenašel.

### Původ

Vznikl při běhu `b92b4e20` tasku `HAIFA-TODO-T05` (Aktualizovat docs/decisions.md pro approve a auto-merge čekající na CI (s povolenou cestou docs/)), v kroku `build` (agent builder).
Důvod: HAIFA-TODO-T05 má stejný problém jako HAIFA-TODO-T01 a HAIFA-REFINEMENT-T28. Jeho efektivní allowed paths dědí z factory/backlog/HAIFA/index.md (`writes: [aifactory/, justfile]`) a front matter tasku žádné vlastní `writes` nemá. docs/decisions.md tak mimo povolené cesty zůstává, i když to název tasku slibuje. Front matter tasku v factory/backlog/ nemůže agent běhu změnit, protože factory/backlog/ mezi jeho povolenými cestami také není.
Task `HAIFA-TODO-T05` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-TODO-T05 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
