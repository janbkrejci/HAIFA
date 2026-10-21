# Read-only triager follow-upů

`aifactory.run.triage.ask_triager(repo, reported, backlog)` přijímá sekvenci `Reported`
a načtený `Backlog`. Vrací `list[Decision]` v pořadí vstupu, se stabilními identifikátory
`f1`, `f2`, … i pro hlášení se stejným titulkem. Backlog ani hlášení nemění.

Rozhodnutí mají `action` a jednovětý `reason`:

- `covered`: existující TODO task plně pokrývá práci; obsahuje `task_id`.
- `extend`: související rozšíření zachovávající všechny původní požadavky; obsahuje
  `task_id`, text `addition` a seznam potřebných cest `addition_writes`.
- `decide`: pokrytí vyžaduje zúžení či zásadní změnu zadání; obsahuje `task_id`
  a `proposal` pro rozhodnutí člověka.
- `new`: práci má pokrýt nový task; bez cílového ID.

Čistá funkce `context(reported, backlog)` předává jen tasky s uloženým `status: todo`,
včetně blokovaných a lidských. Obsahuje zděděné writes a assignee, příslušný step,
cestu úplného zadání a schéma `TriageOutput`. Každé tělo je omezeno konstantou
`BODY_LIMIT` na 6 000 znaků; `body_truncated` upozorňuje na zkrácení. Počet hlášení
ani kandidátů není omezen. Agent má podle potřeby přečíst celé zadání.

Brána kontroluje přesně jedno rozhodnutí na hlášení a existující TODO cíle. Rozšíření
lidského tasku nebo přesměrování lidského follow-upu do agentího rozšíření odmítá.
Požadované cesty z původního hlášení i `addition_writes` musí prokazatelně patřit do
zděděných writes cíle; potenciální překryv globů nestačí. Cesty pojmenované v doplnění
slouží jako další syntaktická kontrola. Prázdné důkazy rozsahu jsou přípustné jen pro
výslovně read-only hlášení (`writes=()`). Sémantickou souvislost a úplné pokrytí posuzuje
agent; brána nevykládá přirozený jazyk jako důkaz zachování záměru.

Bez hlášení funkce vrátí `[]`; bez TODO kandidátů vrátí pro všechna hlášení `new`,
bez konfigurace či spuštění harnessu. Jinak spustí seed agenta `triager` v izolovaném
checkoutu na konfiguračním commitu, vynutí `writes=[]` a hlídá oba checkouty přes
`TaskWriteGuard`. Prompty a trace ukládá do `.factory/data/triage/<job>/`.

Neplatná rozhodnutí dostanou jednu opravu branou. Nedostupná konfigurace či harness,
selhání agenta, vyčerpaná oprava a porušení read-only režimu vyvolají zachytitelnou
`TriageUnavailable` s příčinou. Funkce vždy uklidí izolovaný checkout a uzavře vytvořený
tracer. Nevrací náhradní `new` při selhání spuštění.

`factory library seed` nabízí agenta z balíčkového seedu. Zápis doporučení do backlogu
a napojení na zakládání follow-upů jsou samostatná integrace T66.
