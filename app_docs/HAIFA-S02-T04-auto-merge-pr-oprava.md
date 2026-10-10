# HAIFA-S02-T04: Auto merge při pomalé odpovědi GitHubu

Automatické mergování při neznámé mergeovatelnosti otevřeného GitHub PR opakuje
kontrolu, dokud GitHub nepotvrdí výsledek. Předchozí limit pěti dotazů mohl úspěšný
a schválený běh zastavit dříve, než GitHub dokončil výpočet. Ani vyčerpání nového
bloku třiceti dotazů již auto merge nezastaví: po dvousekundové pauze začne další.

Jakmile GitHub potvrdí mergeovatelnost, pokračují běžné kontroly a schválení.
Potvrzený konflikt čekání ukončí a použije se stávající postup řešení konfliktu.
Zavřený či již mergovaný PR rovněž ukončí dotazování.

Pokud stav zůstává neznámý, automatické čekání pokračuje bez celkového časového
limitu a bez nutnosti ručně opakovat schválení. Mezi dotazy jsou dvousekundové
pauzy. Neznámý stav neznamená konflikt; během čekání se PR nemerguje. Při chybě
komunikace s poskytovatelem čekání skončí a detail běhu uvede `status_unavailable`.

Není potřeba měnit konfiguraci. Auto merge používá tento postup také po automatickém
řešení konfliktu. Běžná kontrola stavu při dalších operacích zůstává omezená na
jeden blok dotazů. Při známém stavu se žádná pauza nepřidává. Stávající ochrany
review, checks a shody head commitu platí i po dlouhém čekání.
