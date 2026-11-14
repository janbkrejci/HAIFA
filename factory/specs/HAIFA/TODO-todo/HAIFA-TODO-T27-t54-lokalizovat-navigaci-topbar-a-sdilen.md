# T27: Lokalizace navigace a sdíleného UI

Rozsah zahrnuje shell aplikace, navigaci repozitáře, menu repozitářů, topbarové čipy, bannery změn a restartu a obecné ovládací komponenty. Texty, tooltipy a přístupné názvy mají shodné klíče v EN/CS katalogu. Titulek dokumentu a `html lang` sledují aktuální locale.

Přepnutí locale nesmí měnit identitu obrazovky ani znovu načítat její data. Otevřená menu, potvrzení a panely, vyhledávací dotazy, výběr modelu, markdownová záložka a rozepsané vstupy zůstávají zachované. Překlad uloženého výsledku úklidu nebo chyby restartu se odvozuje z dat, nikoli z hotové věty uložené při požadavku. Počty souborů, změn a odstraněných položek používají katalogové plurály.

Názvy, cesty, obsah dokumentů, API enumy a původní detaily chyb či varování zůstávají daty. Neznámé stavové kódy se zobrazí beze změny. Sdílená potvrzení podporují jak dosavadní objekt voleb, tak funkci vracející reaktivně překládané volby.

Obsah jednotlivých obrazovek a jejich specifické dialogy patří úlohám T28–T34. Tato migrace nezpřístupňuje globální přepínač ani neoznačuje celkovou lokalizaci za dokončenou. Aktivace a distribuovaný frontend náleží T35.

Akceptace: testy obou jazyků ověří popisky, tooltipy, aria-label, titulek, lang a zachování rozpracovaného stavu při přepnutí tam i zpět; testy chyb restartu ověří překlad po selhání. Dosavadní české UI scénáře používají explicitní `cs`.
