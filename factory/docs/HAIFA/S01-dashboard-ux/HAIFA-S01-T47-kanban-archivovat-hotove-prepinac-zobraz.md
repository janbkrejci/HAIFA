# HAIFA-S01-T47 — Archivace karet kanbanu

Kanban ve sloupcích Hotovo a Zrušeno standardně skrývá tasky s příznakem `archived`. Zrušené tasky tento příznak dostávají automaticky na serveru. Hotové tasky člověk archivuje tlačítkem Archivovat; zobrazenou archivovanou hotovou kartu vrátí tlačítkem Obnovit. Archivované karty jsou ztlumené, odkaz na detail zůstává dostupný.

Každý z obou sloupců má vlastní ikonový přepínač Zobrazit archivované (N), dostupný i v prázdném sloupci. N počítá archivované tasky po použití filtrů projektu a stepu; hlavní počet udává viditelné karty. Preference jsou ve výchozím stavu vypnuté a ukládají se odděleně pod `haifa.backlog.showArchived.done` a `haifa.backlog.showArchived.cancelled` jako `1` nebo `0`. Při nedostupném localStorage fungují v paměti pro aktuální návštěvu.

Archivace volá `POST /api/repos/<repo>/backlog/tasks/<id>/archive` s tělem `{archived: boolean}` a následně znovu načte backlog. Během zápisu jsou nástroje karet deaktivované. Při chybě se obnoví předchozí data a zobrazí společná chyba zápisu fronty. Archivace se necommituje. Přepínač Skrýt hotové dále skryje celé sloupce Hotovo a Zrušeno, aniž by měnil archivní preference; strom, graf a detail se nemění.

Příručka obsahuje jednu větu o archivaci. Existující popis stromu a kanbanu byl zkrácen při zachování významu, aby celková příručka dodržela testovaný limit 4100 slov.

## Ověření

- `bun run test src/lib/backlog.test.ts src/components/backlog/KanbanBoard.test.ts src/views/BacklogView.test.ts`: 93 testů prošlo, včetně API, reloadu, rollbacku, busy, přepínačů a localStorage.
- `just pytest tests/test_guide.py tests/test_guide_consistency.py tests/web/test_web_guide.py`: všech 14 testů prošlo beze změn Python testů.
- `just web-build`: úspěšný TypeScript check a Vite build, distribuovaný static adresář přegenerován; THIRD_PARTY_NOTICES zachováno.
- Kontrola testů přes `rg` pro selektory karet, nástrojů, hlaviček a dotčené texty: původní selektory zachované, připravená karta stále má čtyři původní nástroje.
- `just pytest tests/e2e/test_f3_browser.py -n0`: všechny 4 browserové testy prošly proti novému buildu (78,51 s).
- `git diff --check`: bez chyb.

Builder spouští pouze konkrétní soubory testů přímo pokrývající změnu; celkové kontroly lint, typecheck a web-test náleží následnému tester kroku.
