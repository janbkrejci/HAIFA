---
id: HAIFA-TODO-T05
title: Aktualizovat docs/decisions.md pro approve a auto-merge čekající na CI (s povolenou cestou docs/)
status: todo
depends_on: [HAIFA-TODO-T06]
related: [HAIFA-TODO-T01]
writes: [docs/decisions.md]
---

## Zadání
Task musí mít v allowed paths docs/decisions.md. Do docs/decisions.md přidat nové rozhodnutí v češtině ve stylu ostatních odrážek, například '**Approve a auto-merge čekají na CI:**', nebo jím nahradit starší rozhodnutí, že auto-merge CI jen zkontroluje a červený PR nechá otevřený. Obsah: approve i auto-merge čekají na checky merge headu, tedy commitu po pushi 'status: done'. Když jsou checky červené, factory spustí na větvi PR nejvýš CI_FIX_ROUNDS=2 interních běhů ci-fix a po každém znovu čeká. Když CI zůstane červené nebo nedoběhne, PR zůstane otevřený a nastaví se auto_merge_error. Na GitHubu dashboard schvaluje na pozadí. Fakta ověřit v kódu z T28: help v aifactory/src/aifactory/cli.py kolem ř. 1891 a v aifactory/src/aifactory/review/.

### Původ

Vznikl při běhu `00e32286` tasku `HAIFA-TODO-T01` (Update docs/decisions.md for CI-gated approve and auto-merge), v kroku `build` (agent builder).
Důvod: HAIFA-TODO-T01 má jako jediný výstup úpravu docs/decisions.md. Jeho allowed paths jsou ale jen aifactory/, justfile a soubory spec/doc tasku. docs/ na kořeni repa mezi nimi chybí, takže by se úprava vrátila a fáze by selhala. Stejný problém měl už původní task HAIFA-REFINEMENT-T28, ze kterého tento follow-up vznikl.
Task `HAIFA-TODO-T01` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-TODO-T01 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
