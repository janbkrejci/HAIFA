---
id: HAIFA-S01-T19
title: Obrazovka Přehled a čísla v přepínači repozitářů
status: done
depends_on: [HAIFA-S01-T16, HAIFA-S01-T18, HAIFA-S01-T01, HAIFA-S01-T03]
---

## Zadání
Doplň obrazovku Přehled, kde je vidět, co se právě děje v každém repu (endpoint z M5), a čísla v přepínači repozitářů.

Where: `aifactory/web/src/` (`App.vue`, `lib/router.ts`, `lib/api.ts`, `lib/format.ts`, `views/`, `components/` a testy), build v `aifactory/src/aifactory/web/static/`.

Done means:
- Nahoře jsou součty Běží, Čeká na review, Selhalo a Problémy. Klik na součet filtruje karty.
- Karta pro každé repo, seřazené podle naléhavosti: problémy, selhání, čeká na review, běží, klid. Repa v klidu jsou sbalená na jeden řádek.
- Řádky karty jsou odkazy. Běží (task, název, workflow, fáze s pokusem, čas od začátku počítaný v prohlížeči, náklady) vede na běh, Čeká na review (task, PR, stáří, „podle trace“) na Review tasku, Selhalo (task, chyba, „proces skončil“) na běh a Konfigurace (nenainstalováno, neplatná, necommitnutá) na nastavení repa. Poslední aktivita ukazuje nejnovější změnu.
- Repo s chybějící složkou ukáže „Složka nenalezena“.
- Přehled se obnoví každé 2 s, když je záložka vidět, při návratu do okna a tlačítkem Obnovit. Nic na něm nezapisuje.
- Přepínač při otevření ukáže u repa počet běžících, čekajících na review a selhaných tasků z téhož endpointu.
- Unit testy (vitest): řazení, filtr součtů, sbalení, odkazy, chybějící složka, obnovování a jeho pauza ve skryté záložce a čísla v přepínači.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: akce z přehledu (spouštění, schvalování, odebrání repa), SSE pro přehled.

Pevná omezení:
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-06 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/69 · náklady $2.00
