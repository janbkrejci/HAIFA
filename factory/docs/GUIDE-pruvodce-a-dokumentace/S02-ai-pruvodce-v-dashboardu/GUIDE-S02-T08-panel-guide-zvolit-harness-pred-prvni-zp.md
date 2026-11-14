# Harness nového vlákna průvodce

Před první zprávou panel načte `GET /api/assistant/harnesses` a nabídne sdíleným
UI dropdownem „Podle nastavení“ a použitelné podporované harnessy. Konkrétní volba
ukáže model a thinking počítače; samostatné editory těchto hodnot nejsou součástí panelu.
Nepoužitelné konfigurace se zobrazují s důvodem. Načítání, chyba s opakováním a stav
bez dostupné podporované volby mají vlastní hlášku a přístup k dialogu
„Harnessy tohoto počítače“.

Vlákno vzniká až při prvním odeslání. Explicitní volba se předá jako `harness`
do `createThread`; „Podle nastavení“ parametr vynechá. Potom panel ukazuje uložený
harness, model a thinking. Existující vlákno nemá výběr; historie, obnovení panelu
a další zprávy zachovávají uloženou volbu. Nové prázdné vlákno obnoví „Podle nastavení“.
Volba nemění výchozí harness repozitáře.

Guide vyžaduje podporovaný harness s omezenými nástroji; pi nelze vybrat.
Pokud výchozí pi skončí chybou `harness_unavailable`, původní zpráva zůstane
v editoru a člověk může vybrat Claude nebo Codex a odeslat ji znovu.

Regresní testy pokrývají API katalogu, vynechání i předání parametru, načítání,
chybu a opakování, nepoužitelné konfigurace, uloženou volbu a reset nového vlákna.
Browser scénář používá repo s pi a falešný Claude adaptér bez živého modelu.
Distribuovaný dashboard vzniká přes `just web-build`.
