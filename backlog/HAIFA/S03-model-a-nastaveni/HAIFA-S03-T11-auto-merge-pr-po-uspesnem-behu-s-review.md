---
id: HAIFA-S03-T11
title: Auto-merge PR po úspěšném běhu s review
status: done
depends_on: [HAIFA-S03-T08]
---

## Zadání
Přidej volbu `auto_merge`, aby běhy mohly pokračovat bez obsluhy: PR, který splní podmínky, factory po běhu sama schválí a sloučí stejně jako `factory task approve`. Dnes to po každém běhu dělá ručně orchestrátor podle pevných pravidel.

Where: `aifactory/src/aifactory/backlog/` (dědičný klíč a jeho zápis), `aifactory/src/aifactory/run/queue.py` (auto-continue), `aifactory/src/aifactory/review/` (schválení), CLI, API a dashboard (`aifactory/web/src/components/backlog/`, `aifactory/web/src/views/ReviewView.vue`), testy v `aifactory/tests/` a vitest.

Done means:
- Klíč `auto_merge` (true nebo false) se dědí jako `auto_continue`: projekt, step, task. Task ho může vypnout, třeba když mění hlídač nebo oprávnění. `factory backlog auto-merge ID --on|--off|--inherit` ho zapíše u projektu a stepu, u tasku `factory task edit`.
- Po běhu se zapnutým `auto_merge` factory PR schválí a sloučí stejnou cestou jako `factory task approve` (včetně commitu `status: done`), jen když platí všechno: běh skončil `succeeded`, workflow má fázi review a poslední review schválilo bez blokujících a nesplněných bodů, PR jde sloučit bez konfliktu a jeho checky v hostingu nejsou červené.
- Workflow bez fáze review se automaticky nemerguje nikdy.
- Když podmínka neplatí nebo merge selže, PR zůstane otevřený na ruční schválení a CLI, trace i dashboard ukážou důvod.
- Se zapnutým `auto_merge` předá auto-continue další task až po merge, takže další běh vychází z base s předchozí změnou.
- Dashboard: přepínač auto-merge vedle auto-continue u projektu a stepu, volba u tasku. Review a detail běhu ukáže, že PR sloučil auto-merge.
- Trace zaznamená, kdo PR sloučil: auto-merge, nebo operátor.
- Testy: každá podmínka zvlášť merge zablokuje, workflow bez review, konflikt, řetěz auto-continue po merge, falešný `gh`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: approve review v hostingu (OB3), provider Azure DevOps.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/25 · náklady $10.20
