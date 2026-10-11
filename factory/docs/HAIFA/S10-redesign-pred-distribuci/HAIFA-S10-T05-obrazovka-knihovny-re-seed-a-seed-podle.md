# Obrazovka Knihovna, obnovení výchozích položek a seed podle sssf

Obrazovka **Knihovna** (`#/library`) má taby Agenti, Workflow, Skilly a Rozšíření pi.
Vlevo je seznam položek knihovny, ve sloupci „Kopie v repech“ je počet registrovaných rep,
která položku přepisují vlastní kopií. Vpravo je vybraná položka: repa s vlastní kopií,
soubory jen pro čtení a historie verzí.

- **Diff** ukáže, co by se v knihovně změnilo, kdyby se kopie repa přesunula do knihovny,
  a co se smaže z repa. Je to plán přesunu (`factory config move`), nic se nezapíše.
- **Přesunout kopii repa do knihovny** po potvrzení zapíše kopii do knihovny, smaže ji
  z repa a commitne obojí. Ostatní repa pak zdědí tuto verzi.

## Obnovit výchozí agenty a workflows

Tlačítko vezme do knihovny výchozí verze z balíčku (`factory library seed`). Položky, které
tým nezměnil, se aktualizují a chybějící přidají. Položku, kterou tým změnil, dialog ukáže
s diffem a přepíše ji jen, když ji zaškrtneš (`--take TYP/JMÉNO`).

## Synchronizace s remote

Panel Synchronizace ukazuje složku, remote, větev, kolik commitů je knihovna napřed
a pozadu a kdy proběhl poslední fetch. Stav říká slovy, co dělat (synchronizováno, stáhni,
odešli, rozcházejí se, necommitnuté změny). „Zkontrolovat remote“ udělá fetch, „Stáhnout“
a „Odeslat“ jsou `factory library pull` a `push`. Knihovnu bez remote jde propojit
s prázdným git repem: knihovna se tam odešle a remote se uloží jako `origin`
(API `POST /api/library/remote`).

## Seed podle sssf

- Agenti: planner, builder, reviewer, documenter, scout ze sssf a navíc tester a test-reviewer.
- Workflow navíc ze sssf: `build`, `build-review`, `build-test`, `plan-build-test-quality`
  a `quality`. Testují přes `test_plan` (tester naplánuje kontroly, kód je spustí);
  `plan-build-test-quality` a `quality` plánují všechny kontroly repa (`coverage: full`).
  `quality` nic nemění ani necommitne.
- Rozšíření pi `subagents` (`subagents.ts` a `themeMap.ts` ze sssf).
