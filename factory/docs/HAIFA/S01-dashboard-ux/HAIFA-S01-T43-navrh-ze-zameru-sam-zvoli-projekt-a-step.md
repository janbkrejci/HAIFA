# Návrh ze záměru sám zvolí projekt a step

`factory backlog propose "ZÁMĚR"` už nevyžaduje `--project` ani `--step`. Když chybí
oba přepínače, agent `proposer` sám rozhodne, kam tasky patří:

- do existujícího stepu, jehož cíl záměr pokrývá,
- do nového stepu projektu, kam záměr věcně patří,
- do nového projektu s novým stepem, pokud záměr nepatří do žádného projektu.

Agent k tomu dostane celý strom backlogu včetně těl projektů a stepů. Když by byl
kontext příliš velký, těla vynechá a čte soubory `index.md` sám. Ke každému umístění
napíše jednou větou důvod (`placement_reason`).

Náhled ukáže nad stepem řádek projektu (nový nebo existující) a řádek
`placement: …` s důvodem. Výstup `--json` obsahuje:

- `data.project` (`id`, `title`, `body`, `path`, `new`),
- `data.step`,
- `data.target` s vyřešeným umístěním `{project, step}`,
- `data.placement_reason`.

Neplatné umístění se agentovi vrátí k jedné opravě stejně jako jiné chyby návrhu.
Neplatné umístění je například:

- vyplněný `existing_step` i nový `step`, nebo ani jeden z nich,
- neznámé id nebo id špatné úrovně,
- nový projekt v backlogu bez úrovně projektu.

`--apply` zapíše i nový projekt a nic necommituje.

`--project` a `--step` fungují jako dřív a nelze je zadat současně. V těchto režimech
musí agent nechat pole `project`, `existing_project` a `existing_step` prázdná.
V navazující připomínce (dashboard) smí agent v automatickém režimu umístění změnit,
pokud o to připomínka žádá, například „dej to do HAIFA-S03“.
