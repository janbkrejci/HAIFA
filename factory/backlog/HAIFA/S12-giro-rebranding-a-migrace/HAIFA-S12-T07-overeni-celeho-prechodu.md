---
id: HAIFA-S12-T07
title: GIRO — ověřit celý přechod a uzavřít rebranding
status: todo
depends_on: [HAIFA-S12-T06]
writes: [aifactory/, giro/, .github/workflows/, README.md, AGENTS.md, CLAUDE.md, docs/, justfile]
---

## Zadání

Ověř výsledný produkt a skutečný cílový repozitář podle kontraktu T01 a záznamu
T06. Oprav pouze nalezené chyby rebrandingu. Výsledek ulož do
`docs/rebranding/verification.md`.

Hotovo znamená:
- Matice obsahuje macOS/Linux/Windows, čistou instalaci GIRO a celou cestu
  starší HAIFA → poslední HAIFA → kliknutí na alert → GIRO z nového repo.
  Ověř legacy proměnné a CLI, zachování dat a opakované spuštění. U každého
  scénáře je konkrétní verze, výsledek a evidence; chybějící důkaz není úspěch.
- Dolož, že alert je v poslední HAIFA, kliknutí skutečně stahuje GIRO z nového
  repo a po restartu zmizí. Další aktualizace už používá GIRO repo. Ověř chybu
  sítě/releasu, nesprávný hash, selhání instalace a opakování bez ztráty dat.
- Poslední HAIFA je stále dostupná na původní adrese; její běžný update zdroj
  funguje pro starší instalace. Z HAIFA repo se již nevydávají nové verze.
- Izolované demo projde cyklem cíl/backlog → plán → implementace → test/review
  → PR/merge → release podle skutečně podporovaného workflow. Automatické
  testy používají fake agenty a hosting. Externí smoke běží pouze ve vyhrazeném
  testovacím repu podle postupu T06, bez zásahu do uživatelských projektů.
- Historie běhů, přepisy, registrace repozitářů, knihovna a odkazy na staré PR
  zůstanou dostupné; přesun nevytvoří duplicitní prázdnou identitu repozitáře.
- Dashboard, `giro --help`, návody, skilly, release assety a update endpointy
  používají stejnou značku a cílové URL. Každý zbylý HAIFA/Helios výskyt má
  důvod v historii, kompatibilitě nebo zachování licence.
- Ověřena funkčnost rollbacku v izolaci a zachování původních dat při selhání.
  Dokumentace jasně uvádí dobu podpory starých názvů a případné omezení migrace.
- Dolož cílené kontroly podle pravidel stepu a skutečný stav CI na novém repu.
  Úplné `just check` a `just e2e` proveď mimo factory run; chybějící platformní
  nebo plné kontroly výslovně předej vlastníkovi a neznač rebranding za uzavřený.

Mimo rozsah: nové funkce produktu, odstranění kompatibility před termínem,
přepis Git historie nebo mazání původního repozitáře a provozních dat.

## Běhy
<!-- doplňuje factory při schválení PR -->
