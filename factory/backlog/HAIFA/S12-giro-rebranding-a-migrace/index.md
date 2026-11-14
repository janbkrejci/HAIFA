---
id: HAIFA-S12
title: GIRO — rebranding a migrace repozitáře
auto_continue: false
---

## Záměr

Přejmenovat soukromý projekt HAIFA na **GIRO — Goal In. Release Out.**
Ve veřejné komunikaci lze použít slovní značku `giro` a slogan
`Goal in. Release out.` Italské giro znamená mimo jiné okruh nebo otočku;
příběhem produktu je opakovaný samostatný cyklus od cíle k vydání.
Odstranit současné spojení s Helios AI Factory a produktem zaměstnavatele.

Rebranding pokrývá dashboard, CLI, dokumentaci, instalaci, aktualizace,
konfiguraci, balíčky, GitHub a související knihovnu. Starší instalace musí
přejít bez ztráty dat, registrací repozitářů nebo historie běhů.
Historické identifikátory tasků a jejich odkazy zůstávají stabilní; proto
má i tento step zatím prefix HAIFA. Minulé releasy a převzaté licence se
nepřepisují jen kvůli novému názvu.

## Zvolený přechod a pořadí

- HAIFA repo zůstane na původní adrese. GIRO se bude vydávat z nového repo,
  předběžně `janbkrejci/GIRO`; dostupnost cílového názvu ověří T01.
- Poslední vydání z HAIFA repo zůstane HAIFA a v dashboardu zobrazí alert
  **„HAIFA se přejmenovává na GIRO“** s akcí **„Klikněte zde pro přechod“**.
  Kliknutí spustí upgrade přímo z nového GIRO repo, včetně následného restartu.
  Po úspěchu se další aktualizace hledají pouze v GIRO repo a alert zmizí.
- Starší HAIFA dostane poslední HAIFA vydání dosavadní aktualizační cestou.
  Není potřeba, aby všechny historické updatery znaly nové názvy balíčků.
- Pořadí přípravy: T01 → T04 (přechodová HAIFA) → T02 (technický GIRO přechod)
  → T03 (GIRO UI a návody) → T05 (postup publikace) → T06 (vydání) → T07 (ověření).
  Přesný zdroj poslední HAIFA se uchová před rebrandingem; další přípravy GIRO
  nesmějí automaticky vydávat GIRO ani další HAIFA z původního repo.
- T06 nejdříve připraví nové repo s historií a zveřejní funkční GIRO release,
  potom vydá poslední HAIFA s alertem z uchovaného zdroje T04. Původní repo
  zachová historii, stará PR, issues a releasy a odkáže na nové místo vývoje.
  Není požadován hromadný převod historických PR/issues ani přejmenování starého repo.
- Vytvoření tohoto backlogu neprovádí změnu hostingu ani publikaci.

## Společná kritéria

- Nová instalace GIRO a práce po přechodu představují produkt jako GIRO. HAIFA/Helios
  zůstává jen v doložených historických záznamech a migrační kompatibilitě.
- Primární CLI má být `giro`; dosavadní `factory` zůstane po určené přechodné
  období kompatibilní. Technické názvy `aifactory`, `.factory/` a `factory/`
  se posoudí zvlášť v T01, včetně nákladů a dopadů jejich změny.
- Neprovádět slepé globální nahrazení: zachovat licence, historii, existující
  ID, odkazy na stará PR a uživatelské konfigurace.
- Každý task má vlastní úplné `writes`. Pokud T01 navrhne nové cesty, před
  spuštěním dotčených tasků je doplnit do jejich front matter a commitnout.
- Kontroly implementace: vždy `just lint` a `just typecheck`, cílené testy
  změněného chování a přímých volajících vyhledaných v celém `aifactory/tests/`.
  Spustit každý upravený testový soubor. Při změně frontendu `just web-test`
  a `just web-build`; browserové testy pouze dotčených obrazovek.
  Testy migrace i selhání musí používat izolovaná data bez živých modelů/služeb.
  Mimo factory run je úplnou závěrečnou kontrolou `just check` a `just e2e`.
  Nepředpokládat rozsah CI: před migrací ověřit aktuální workflow a pravidla hostingu.
