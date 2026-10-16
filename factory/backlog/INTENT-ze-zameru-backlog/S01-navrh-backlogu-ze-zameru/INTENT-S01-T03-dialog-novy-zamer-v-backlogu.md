---
id: INTENT-S01-T03
title: Dialog Nový záměr v Backlogu
status: todo
depends_on: [INTENT-S01-T01, INTENT-S01-T02]
---

## Zadání
Zadání:
1. Backlog má tlačítko „Nový záměr“: textové pole, výběr projektu nebo stepu, Navrhnout.
2. Průběh návrhu je vidět. Výsledek je strom nových tasků s rozbalitelným zadáním, nálezy kontroly a možností task odebrat nebo upravit text.
3. Pole „Upřesni“ pošle připomínku a agent vrátí upravený návrh ve stejné session.
4. Použít zapíše návrh a commitne backlog stejně jako ruční založení tasků.

Hotovo znamená:
- Vitest dialogu, browser test celého toku s fake harnessem.
- `just web-test`, `just web-build`, dotčené testy podle AGENTS.md.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
