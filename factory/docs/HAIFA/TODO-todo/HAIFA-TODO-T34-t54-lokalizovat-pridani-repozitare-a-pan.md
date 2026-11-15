# Lokalizace přidání repozitáře a pomocných panelů

Přidání repozitáře, kontrola složky, volby instalace, výsledná karta, procházení složek a odebrání repozitáře používají katalog EN/CS. Texty navazují na existující lokalizovaný onboarding přehledu a záložky Factory. Výchozí jazyk nadále určuje společná lokalizační vrstva.

AI průvodce překládá ovládání, návrhy otázek, popisky kontextu, seznam vláken, potvrzení smazání a ovládání navržených akcí. Terminál překládá ovládání a stavové informace. Počty souborů a zpráv používají plurály EN/CS.

Změna jazyka nevyvolává remount, nový požadavek ani restart terminálu. Otevřené potvrzovací dialogy a známé chyby výběru/kontroly složky odvozují text při vykreslení. Rozepsané cesty, zaškrtnuté volby instalace, vybraná složka, zpráva průvodci, konverzace a stream zůstávají zachované.

Uživatelské zprávy, odpovědi modelu, důvody navržených akcí, obsah zadání, generované názvy navazujících úkolů, zaznamenané výsledky akcí, identifikátory, cesty a terminálové bajty se nepřekládají. Neznámá diagnostika API se zobrazuje v původním znění.

## Regresní pokrytí

- Přepnutí EN → CS → EN při rozepsané cestě, otevřeném prohlížeči složek a vybraných volbách instalace.
- Překlad již zobrazených chyb a výsledné karty instalace bez ztráty dat.
- Přepnutí při rozepsané zprávě, načtené konverzaci, návrhu akce a aktivním streamu; zachování původních textů a počtu požadavků.
- Překlad návrhů otázek, počtů zpráv a otevřeného potvrzení smazání vlákna.
- Překlad otevřeného potvrzení odebrání repozitáře při zachování operace `uninstall: false`.
- Přepnutí terminálového ovládání při zachování stejného PTY, odeslaného vstupu a nezměněných výstupních bajtů.
- Existující browser scénáře průvodce mají explicitní CS; browser scénáře terminálu očekávají výchozí EN.

Globální zpřístupnění přepínače a aktualizace distribuovaných assetů patří do HAIFA-TODO-T35. Tento díl distribuovaný frontend nemění.
