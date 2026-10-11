---
id: HAIFA-REFINEMENT-T05
title: Opravit synchronizaci zruseni onboardingu v browser testu
status: done
workflow: build-test-review
depends_on: []
related: [HAIFA-S90-T06]
writes: [aifactory/tests/e2e/test_onboarding_browser.py, aifactory/tests/e2e/test_factory_install_browser.py]
---

## Zadání
Posledni beh HAIFA-S90-T06 (5c7fd537) selhal v tests/e2e/test_onboarding_browser.py:77: po kliknuti cancel-install se ihned cte /api/repos a test vidi docasnou registraci, protoze cancelPendingInstall ceka asynchronne na removeRepo. Log je .factory/data/sessions/5c7fd537/context_handoff/quality/02_measurement/command.log. Opravte browser test tak, aby pred kontrolou prazdneho registru cekal na skutecne dokonceni zruseni (napr. znovu viditelnou kartu inspect-onboard, ktera se vraci az po vymazani pendingInstall). Zachovejte aserci prazdneho registru a pokryti realneho odstraneni, zadne sleep, retry celeho testu ani oslabeni aserci. Prověřte analogicky cancellation v test_factory_install_browser.py. Produktove chovani nemente, pokud se potvrdi race pouze v testu. Overte oba browser testy a opakovane relevantni scenar bez site a zivych modelu; nasledne just check-scoped a review. Pricina musi byt odstranena pred novym merenim delky testu.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/103 · náklady $0.00
