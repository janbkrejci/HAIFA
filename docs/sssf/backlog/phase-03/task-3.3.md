Implementuj obrazovku Backlog: strom modul → step → task a kanban, filtr stavu a vlastníka, detail tasku, založení a editace tasku, vazby a přiřazení workflow (tabulka „Dashboard“ v `docs/product-brief.md`).

Where: `aifactory/src/aifactory/web/`, `aifactory/web/src/`, `aifactory/tests/web/`.

Done means:
- Strom podle `levels` z konfigurace a kanban podle stavu (todo, ready, blocked, running, in review, done, cancelled). Filtr stavu a vlastníka modulu.
- Detail tasku: hlavička, zadání, vazby oběma směry (`depends_on` a dopočítané „blokuje“), běhy a PR.
- Založení a editace tasku, přidání a odebrání vazby a přiřazení workflow volají tytéž funkce core jako `factory task add|edit|link`. Zápis, který by backlog rozbil, se neprovede a UI ukáže chybu z validace.
- Testy API nad dočasným repem s backlogem a unit testy komponent.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: graf závislostí a spuštění (3.4), editor workflow (F4).

Pevná omezení:
- UI zapisuje jen soubory backlogu v hlavním checkoutu a nic necommituje.
- `vendor/` a `prototype/` se nemění.
