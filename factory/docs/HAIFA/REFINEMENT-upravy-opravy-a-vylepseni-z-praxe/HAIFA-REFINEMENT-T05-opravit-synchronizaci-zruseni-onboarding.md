# HAIFA-REFINEMENT-T05 — Zrušení onboardingu v browser testu

Pád běhu `5c7fd537` způsobilo čtení `/api/repos` ihned po kliknutí na Zrušit.
Kliknutí spustí asynchronní `cancelPendingInstall()`, které čeká na odstranění
dočasné registrace. Test mohl číst registr dříve, než odstranění skončilo.

Onboarding test nyní před asercí prázdného registru čeká na viditelné
`inspect-onboard`. Karta se vrací až po vymazání `pendingInstall`, které následuje
po dokončení `removeRepo()`. Instalační test už čekal na návrat `add-path` ve
stejné větvi UI; nově také explicitně ověřuje návrat `inspect-init`.

Aserce prázdného registru, odstranění dočasného ID, nezměněného repozitáře při
zrušení a následného skutečného onboardingu/instalace zůstávají zachované.
Produktový kód se nemění. Testy nepoužívají nové prodlevy ani retry při selhání.

Ověření se spouští sériově, dvakrát samostatně:

```sh
cd aifactory
uv run --offline pytest tests/e2e/test_onboarding_browser.py tests/e2e/test_factory_install_browser.py -n0
```

Testy používají lokální bare remotes a dočasné `HAIFA_HOME`. Browser blokuje
externí požadavky a závěrečné aserce kontrolují jejich absenci i neaktivovaný
tripwire pro živé harnessy. `--offline` také zakazuje síťové stahování závislostí.

Oba sériové běhy prošly: každý 2 passed (22,11 s a 18,38 s), bez opakování při
selhání. `just typecheck` prošel pro 406 souborů, `just lint` i
`git diff --check` skončily s kódem 0. Kontrola diffu ověřila, že čekání předchází
čtení registru a původní aserce zůstaly beze změny.

Následující fáze workflow musí provést `just check-scoped` a finální review před
novým měřením délky celé sady; builder podle svých pravidel celou sadu nespouští.
