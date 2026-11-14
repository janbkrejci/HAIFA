---
id: HAIFA-S12-T02
title: GIRO — CLI, technické názvy a bezpečná migrace dat
status: todo
depends_on: [HAIFA-S12-T01, HAIFA-S12-T04]
writes: [aifactory/, giro/, justfile, .gitignore, .github/workflows/, docs/rebranding/, docs/decisions.md]
---

## Zadání

Implementuj technické mapování z `docs/rebranding/giro.md`. Výchozí relevantní
místa: `aifactory/pyproject.toml`, `src/aifactory/cli.py`, `home.py`, konfigurace,
registry repozitářů, knihovna, run store a spotřebitelé proměnných `HAIFA_*`.
Při změně zdrojových cest uprav i build a CI tak, aby každý merge zůstal funkční.
Tento task připravuje GIRO, nikoli poslední HAIFA s alertem. Zdroj přechodové
HAIFA z T04 musí zůstat dostupný; GIRO se bude publikovat jen z nového repo.

Hotovo znamená:
- `giro` nabízí stejné podporované operace jako dosavadní CLI; přechodný alias
  `factory` používá tutéž implementaci a datové úložiště. Help a verze uvádějí GIRO.
- Nové GIRO proměnné/cesty a staré aliasy dodržují kontrakt T01. Všechny jejich
  spotřebitele uprav konzistentně, včetně podprocesů, upgradu a uninstallu.
- Upgrade najde původní nastavení, knihovnu s místními změnami, registrovaná
  repa, běhy, přepisy a rozpracovanou práci. Opakované spuštění migraci neopakuje
  destruktivně ani nezakládá druhou prázdnou továrnu.
- Při kolizi starých a nových dat, nedostatečných oprávněních, přerušení nebo
  aktivním procesu nevznikne tiché přepsání. Původní data zůstanou obnovitelná;
  jasně popiš bezpečný návrat. Neměň uživatelovy živé adresáře při vývoji/testech.
- Změny distribučního názvu/importů/zdrojových cest proveď podle T01 včetně
  odkazů, build konfigurace a lock souborů. Přechod nesmí rozbít aktuální
  instalátory ani přechodový updater z T04. Bundle GIRO se sestaví se správnou
  verzí, kontrolními součty a instalátory pro macOS/Linux/Windows. Přímá
  kompatibilita se všemi historickými HAIFA updatery není součástí zadání.
- Po přechodu GIRO hledá další vydání v novém repo; aktualizační konfigurace
  převzatá ze staré HAIFA ho nesmí vrátit ke starému release zdroji.
- Při přejmenování repa/adresáře se nesmí ztratit vazby repo → historie běhů
  a worktree. Historické task ID, PR a Git commity zůstávají beze změny.

Ověření: společné kontroly stepu a cílené regresní testy pro čistou instalaci,
legacy-only, nové i staré proměnné současně, oba datové adresáře, opakování
migrace a její selhání. Pokrýt macOS/Linux/Windows pravidla cest. Fake nástroje
a izolované home; žádné volání modelů ani změna provozních dat.

## Běhy
<!-- doplňuje factory při schválení PR -->
