# T99: Pokračování po sloučení PR mimo factory

Dashboard po refreshi stavů PR předá každý stav `merged` funkci `continue_after_merge`.
Pokračování smí spotřebovat pouze poslední řetěz tasku zastavený na `not_merged`;
atomický claim z T98 zabrání opakovanému spuštění. Vybraný task spustí launcher
v samostatném procesu `factory task run`, se zachováním příznaku `--auto`.

Společný výběr fronty kontroluje nejnovější PR kandidáta. Pokud je `merged`,
kandidáta přeskočí s důvodem `merged_outside` a výzvou k `factory backlog sync`.
Kontrola platí pro sekvenční i paralelní auto-continue, obnovení řetězu a start_factory.
Novější PR v jiném stavu tuto ochranu starého sloučeného PR ruší.

Závislosti se nadále vyhodnocují podle backlogu v base. Sloučený PR sám nenahrazuje
`status: done`, ani při zapnutých stacked PR. Automatické vytváření sync PR a změny UI
nejsou součástí změny.
