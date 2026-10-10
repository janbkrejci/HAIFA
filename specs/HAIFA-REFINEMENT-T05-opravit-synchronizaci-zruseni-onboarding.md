# HAIFA-REFINEMENT-T05 — Synchronizace zrušení onboardingu

Měření běhu `5c7fd537` selhalo na aserci prázdného registru v
`test_onboarding_and_adoption_browser`: kliknutí na `cancel-install` nečeká na
dokončení asynchronního odstranění dočasně registrovaného repozitáře.

`cancelPendingInstall()` nejprve čeká na `removeRepo()` a potom nastaví
`pendingInstall` na `null`. `ReposAddView` zobrazí původní formulář a kartu
inspekce až po této změně. Produktové chování je správné.

Test onboardingu musí před čtením `/api/repos` čekat pomocí Playwright `expect`
na viditelné `inspect-onboard`. Analogický instalační test musí výslovně ověřit
návrat `inspect-init`; jeho stávající čekání na `add-path` už používá stejnou
podmíněně vykreslenou větev UI.

Akceptace:

- Zachovat aserci prázdného registru při onboardingu i odstranění dočasného ID
  při instalaci a všechny následné kontroly skutečné instalace/onboardingu.
- Nepřidávat pevné prodlevy, opakování celého testu při selhání ani produktové změny.
- Spustit oba browser testy dvakrát sériově s lokálními remotes, blokováním
  externích browser požadavků a tripwire pro živé harnessy.
- Builder provede typecheck, lint a kontrolu diffu; následná testovací a review
  fáze workflow provede `just check-scoped` a review před novým měřením délky.
