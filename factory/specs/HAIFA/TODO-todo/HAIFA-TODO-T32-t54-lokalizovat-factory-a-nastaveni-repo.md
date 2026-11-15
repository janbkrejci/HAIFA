# Lokalizace Factory a nastavení repozitáře

Obrazovka Factory používá existující klientské locale EN/CS. Překlad zahrnuje kontrolu, instalaci, stažení konfigurace, commit preview a potvrzení, správu rosteru a dědičnosti, sdílená i lokální nastavení a lekce. Jména, cesty, API enumy, uložená konfigurace, diffy, pravidla a výtky lekcí a generované zadání opravného tasku zůstávají původní.

Přepnutí locale mění popisky za běhu bez remountu, obnovení dat nebo zápisu nastavení. Zachová rozepsaná pole, instalační volby, zprávu commitu, vybrané nálezy, rozbalené sekce, rozpracovanou změnu rosteru, otevřené potvrzení a volbu projektu u lekce. Uložení nadále odesílá původní API hodnoty a pouze změněná pole.

Backendové nálezy, blokátory a chyby se pojmenovávají podle explicitních kódů. Původní diagnostika a doporučené příkazy jsou dostupné v technických podrobnostech. Validace nastavení doplňuje `message_code` a případný parametr `limit`; existující `code`, `message`, `path` a `id` se nemění. Odpověď serveru nezávisí na globálním locale ani na předchozím klientovi.

Regrese pokrývají EN/CS popisky a plurály, neznámé kódy, zachování rozepsaných hodnot a kontrolu payloadů, odmítnuté uložení s lokalizovanou validací, otevřený náhled a potvrzení a zachování autorského obsahu. Browser scénář lekcí používá výchozí EN a explicitní CS.
