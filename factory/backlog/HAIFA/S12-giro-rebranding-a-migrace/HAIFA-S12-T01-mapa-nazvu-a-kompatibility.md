---
id: HAIFA-S12-T01
title: GIRO — mapa názvů, kompatibility a cílového repozitáře
status: todo
depends_on: []
writes: [docs/rebranding/, docs/decisions.md]
---

## Zadání

Připrav implementovatelný kontrakt rebrandingu HAIFA → GIRO. Vycházej ze
záměru stepu. Výstup ulož do `docs/rebranding/giro.md`, trvalá rozhodnutí
zapiš do `docs/decisions.md`.

Hotovo znamená:
- Inventura aktuálních výskytů HAIFA/haifa/Helios, `aifactory`, CLI `factory`,
  `HAIFA_*`, datových cest, názvů balíčků a archivů, GitHub URL, knihovny,
  frontendových storage klíčů, seedů, skillů a CI. U každé skupiny uveď cestu,
  cílový název, vlastnící task a případnou zdůvodněnou výjimku.
- Značka je GIRO, slogan `Goal in. Release out.`, primární příkaz `giro`.
  Urči dobu a pravidla kompatibility `factory`, `HAIFA_*`, starých adresářů
  a balíčků. Rozhodni výslovně o distribučním jménu, Python namespace,
  zdrojovém adresáři, `.factory/` a `factory/`; neutrální technické názvy
  se nemění bez důvodu. Povinný přechod je stará HAIFA → poslední HAIFA
  s alertem → GIRO z nového repo; neřeš přímý upgrade každé staré verze na GIRO.
- Popiš prioritu GIRO/HAIFA proměnných, chování při existenci obou datových
  adresářů, zálohu, návrat a přístup staré verze po migraci.
- Ověř aktuální dostupnost cílového GitHub jména a relevantní použití GIRO
  v softwaru; nález není tvrzením o právní dostupnosti značky. Zapiš navržené
  přesné nové `owner/repo` a vazbu na HAIFA-LIBRARY. Původní HAIFA repo
  zůstává dostupné pro poslední přechodové vydání a historické odkazy.
  Nejasného vlastníka nebo obsazené jméno zaznamenej jako rozhodnutí pro T06.
- Zaznamenej aktuální skutečný obsah CI a hranici mezi PR/merge a release:
  slogan nesmí v dokumentaci slibovat již implementované automatické vydávání,
  pokud ho produkt ve skutečnosti neumí.
- Popiš uchování zdroje poslední HAIFA před rebrandingem a omezení publikace
  z původního repo. GIRO release musí být dostupný dříve než HAIFA alert.
- Každá změna má akceptační scénář a cílový task T02–T07; případné potřebné
  rozšíření `writes` uveď pro úpravu backlogu před spuštěním dalších tasků.

Ověření: inventura proti aktuálním zdrojům, kontrola úplnosti mapování a odkazů.
Žádné změny produktu, přejmenování na hostingu, registrace domén ani publikace.

## Běhy
<!-- doplňuje factory při schválení PR -->
