---
id: HAIFA-S01-T54
title: Dokončit anglické a české UI dashboardu a zapnout výchozí EN
status: todo
depends_on: [HAIFA-S01-T53, HAIFA-S01-T50, HAIFA-S01-T51, HAIFA-S01-T52]
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/src/aifactory/guide/, aifactory/tests/]
---

## Zadání
Na společném i18n základu převést celé rozhraní dashboardu do EN a CS a zpřístupnit volbu „English“ / „Čeština“ na globálním místě dostupném i bez repozitáře. Default je EN bez automatického výběru CS podle prohlížeče. Zahrnout nově přidané indikace a ovládání z navázaných UX tasků.

Akceptace:
- Převést navigaci/topbar, Přehled, Backlog a jeho dialogy včetně Intentu, běhy, Review, Factory/nastavení, přidání repozitáře/onboarding, knihovnu, problémy, průvodce i sdílené komponenty. Zahrnout stavové texty, validace, potvrzení, prázdné/loading/chybové stavy, tooltipy, aria-label, titulek stránky a html lang.
- Integrovaná uživatelská nápověda/příručka má EN a CS variantu volenou podle UI; současné odkazy na kapitoly zůstávají funkční. Obsah udržovat jako statické překlady, bez AI překladu za běhu.
- Pro hlášky dodané backendem používat stabilní kódy a parametry, případně explicitní locale požadavku. Nepřekládat parsováním českých vět a neměnit procesově globální jazyk serveru: dva prohlížeče mohou současně používat různé jazyky. Zachovat kompatibilitu API a technické detaily chyb jako detaily.
- Anglický ani český režim nemíchá pevné texty druhého jazyka. Názvy a zadání uživatelů, soubory, ID, logy, zdrojový kód a již uložené odpovědi agentů se nemění. Jazyk generovaných zadání/odpovědí a lokalizace samostatného CLI nejsou součástí této UI změny.
- Přepnutí bez reloadu zachová rozepsaný Intent, formuláře, otevřený panel i sledovaný běh. Volba se pamatuje a funguje napříč repozitáři. Ověřit délku překladů na úzkém okně bez ořezání hlavních akcí.
- Aktualizovat testy na nový default: češtinu testovat explicitním cs, ne vrácením globálního českého defaultu. Upravit distribuovaný frontend.

Ověření: kontrola úplnosti EN/CS katalogů a nepřeložených UI literálů, browser scénáře výchozí EN / přepnutí CS / persistence / návrat EN, reprezentativní formulář s rozepsaným textem a chyba API v obou jazycích. Spustit všechny upravené testovací soubory. Pokud migrace překročí proveditelný rozsah tasku, rozdělit ji po obrazovkách do navazujících tasků s writes; nepovažovat částečně české UI za hotovou anglickou lokalizaci.

Ověření: vyhledat přímé volající v celém aifactory/tests/ a zvolit jen testy dotčeného chování. Spustit každý změněný testovací soubor, just lint, just typecheck, just web-test, just web-build a příslušné browser testy změněných obrazovek podle AGENTS.md. Testy bez živých modelů a služeb, s izolovaným HAIFA_HOME; nespouštět celou sadu v tasku.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
