---
id: HAIFA-S05-T13
title: Obrazovky Tento počítač a Knihovna
status: done
depends_on: [HAIFA-S05-T11, HAIFA-S05-T12, HAIFA-S01-T22]
---

## Zadání
Doplň do dashboardu obrazovku Tento počítač s kontrolou stroje a nastavením knihovny a obrazovku Knihovna s položkami, historií, použitím a operacemi ve více repech. Dashboard bez repozitářů s chybou kontroly nebo bez knihovny začne na Tento počítač (první spuštění kolegy).

Where: `aifactory/web/src/` (`App.vue`, `lib/router.ts`, `lib/api.ts`, `views/`, `components/`, `components/review/DiffView.vue` a testy), `aifactory/tests/e2e/`, build v `aifactory/src/aifactory/web/static/`.

Done means:
- `#/setup` (Tento počítač) ukáže nálezy kontroly ve skupinách HAIFA, Nástroje, Harnessy (s počtem rep, která harness používají), Hosting, Knihovna a Prostředí. Každý nález má opravu s tlačítkem Kopírovat a stránka má Znovu zkontrolovat. Nic neinstaluje a nikam nepřihlašuje.
- Sekce Knihovna: cesta, remote, náskok a zpoždění, Pull a Push, bez knihovny Naklonovat týmovou knihovnu… (URL) a Založit ze semínka. Obojí jde přes náhled plánu a potvrzení ve vlastním modálu.
- Při prázdném registru otevře dashboard `#/setup`, když kontrola hlásí chybu nebo chybí knihovna, jinak prázdný přehled. Navigace má Tento počítač a Knihovnu. Akceptační test z M15 se upraví na nový první start a projde.
- `#/library` má záložky Agenti, Workflow, Skilly a Rozšíření pi. Řádek: jméno, purpose nebo description, verze `vN · hash`, datum, autor a čipy rep, která položku používají, barvené podle stavu.
- Detail položky: soubory (jen čtení), historie verzí a tabulka použití se stavem, Diff a zaškrtnutím. Přidat do repozitářů… a Aktualizovat vybraná repa… ukážou plán každého repa, po potvrzení je provedou po jednom a ukážou výsledek repa (commit, PR, blokátor).
- Import… vezme složku pod domovem a typ, ukáže náhled a po potvrzení zapíše.
- Unit testy (vitest): skupiny nálezů, kopírování opravy, první start, knihovna bez remote, záložky, detail, operace ve více repech s jedním zablokovaným repem, import. Prohlížečový test s dočasným `HAIFA_HOME` založí knihovnu ze semínka a ukáže její položky.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: editory položek (F4), správa položek repa (L14), onboarding (O5), instalace nástrojů.

Pevná omezení:
- UI posílá jen volby plánu a digest, nikdy obsah souborů.
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/91 · náklady $0.00
