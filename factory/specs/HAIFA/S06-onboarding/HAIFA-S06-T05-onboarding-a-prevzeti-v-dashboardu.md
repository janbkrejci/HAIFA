# HAIFA-S06-T05 — Onboarding a převzetí v dashboardu

Dashboard využívá existující serverové plány `onboard` a `adopt`. V průvodci přidáním
nabízí onboarding pro sssf a HAIFA před knihovnou. Registrace je dočasná stejně jako
při instalaci; Zrušit ji odebere, úspěšný zápis ji zachová.

Factory zobrazuje původ onboardingu a knihovnu. Náhled onboardingu má Knihovnu
(položky a verze), Repozitář (obsah souborů) a Zprávu (skupiny kódů). Blokátory
zakazují provedení. Remote onboarding nabízí dorovnání base; čekající PR odkazuje
na hosting, pokud jeho poskytovatel vrátí identifikaci, jinak do Review.

Převzetí spouští náhled adopt bez vytěžení. Chybějící knihovna nabízí klonování
remote z manifestu přes serverový plán a vlastní potvrzení. Chybějící položky
nabízí doplnění; jiná identita knihovny má varování. Požadavky operací obsahují
jen akci, výchozí volby, cíl, digest a případnou zprávu. Žádný soubor náhledu se
neodesílá zpět. Nevzniká frontendová závislost; adws/ se zachovává.

Ověření: cílené Vitest testy komponenty a obou pohledů, API testy a Playwright
scénář s sssf fixturou, dvěma HAIFA_HOME a dvěma lokálními bare remotes.
