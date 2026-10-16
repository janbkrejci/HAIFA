# AI průvodce: návrh akce a potvrzení

Průvodce v panelu dashboardu sám nic nemění. Když po něm chceš změnu, navrhne ji jako
kartu a provede se až po tvém potvrzení.

## Co umí navrhnout

- založit task (krok, název, zadání, writes, workflow, závislosti),
- upravit task: název, zadání, writes nebo workflow,
- spustit task nebo zopakovat běh (s poznámkou pro agenty),
- schválit PR tasku,
- zrušit task.

## Použití

- Karta návrhu ukáže, co se stane: repo, task nebo běh a změněná pole. U úpravy a zrušení
  tasku vidíš i současnou hodnotu (přeškrtnutou) a novou.
- **Provést** zavolá stejné API jako ruční tlačítko v dashboardu, se stejnými kontrolami.
  Co nejde ručně (třeba spustit task s nesplněnou závislostí), nejde ani tady.
- **Zahodit** návrh odmítne bez zápisu.
- Výsledek (provedeno, selhalo s důvodem, zahozeno) se objeví na kartě i jako řádek ve
  vlákně. Průvodce se ho dozví s tvou další zprávou.

## Omezení

- Každý návrh jde provést jen jednou.
- Návrh, který dashboard neumí nabídnout (neznámá akce, neregistrované repo, chybějící
  údaj), se v odpovědi ukáže jako citace s důvodem místo karty.
- Upravené zadání a writes nahrazují původní hodnotu celou.
- Provedená úprava backlogu je stejná jako ruční úprava v dashboardu, i co do commitu
  změn backlogu.
