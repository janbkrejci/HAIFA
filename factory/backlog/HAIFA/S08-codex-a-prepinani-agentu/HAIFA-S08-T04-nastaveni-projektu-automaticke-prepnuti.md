---
id: HAIFA-S08-T04
title: "Nastavení projektu: automatické přepnutí harnessu při vyčerpání kvóty (řetěz a návrat)"
status: todo
workflow: simple-sdlc
depends_on: []
related: [HEAL-S02-T03, HAIFA-S08-T01, HAIFA-REFINEMENT-T03]
---

## Zadání
## Záměr

V nastavení projektu, tam kde se volí, jestli harness zdědit nebo nastavit vlastní, přidat prvek „Automaticky přepnout harness při vyčerpání limitu tokenů“. Uživatel v něm zvolí, na který harness, případně na které harnessy (v pořadí), se má přepnout.

Tamtéž přidat volbu „Vrátit zpět při obnovení limitu“, aby změna harnessu mohla být jen dočasná.

Když existují víc než dva harnessy, určí se řetěz, v jakém pořadí se přepíná. Při obnovení limitu se vrací stejnou cestou zpět.

## Současný stav (kontext)

- HEAL-S02-T03 už umí po selhání `quota` jednou přepnout na **jednu** zálohu. Záloha je `fallback` v `.factory/agents.yaml` (defaults nebo agent) nebo v `.factory/local.yaml` a implementuje ji `run/fallback.py`. Retry, který už harness přepnul, znovu nepřepíná.
- Harness a model projektu se nastavují v `ContainerSettings.vue` (zdědit nebo vlastní). Klíče kontejneru jsou v `CONTAINER_KEYS` (frontend `lib/backlog.ts`, backend `aifactory/backlog`).

## Požadavky

1. V nastavení projektu, u volby harnessu, je přepínač „Automaticky přepnout harness při vyčerpání limitu tokenů“.
2. Po zapnutí jde vybrat jeden nebo více záložních harnessů v pořadí, tedy řetěz. Pořadí jde měnit. Nabízejí se jen harnessy dostupné na tomto počítači (stejný zdroj jako u výběru harnessu projektu) a žádný se v řetězu neopakuje.
3. Volba „Vrátit zpět při obnovení limitu“ (zapnuto / vypnuto).
4. Při vyčerpání kvóty se běh přepne na další harness v řetězu, který má kvótu. Když dojde kvóta i jemu, pokračuje se na další v pořadí. Když dojde celý řetěz, běh skončí selháním `quota` jako dnes.
5. Když je návrat zapnutý a harnessu výš v řetězu se obnoví limit, další běhy (nebo fáze, podle toho, co jde bezpečně udělat) se vrátí o krok zpět stejnou cestou, až k původnímu harnessu projektu.
6. Nastavení se ukládá do nastavení projektu (index.md kontejneru) stejně jako ostatní klíče. Musí jít nastavit i přes CLI nebo API jako ostatní klíče kontejneru. Lze ho zdědit od rodiče, stejně jako harness.
7. Stávající zálohu z `agents.yaml` / `local.yaml` neporušit. Pořadí přednosti oproti novému nastavení projektu musí být jasně dané a zdokumentované.
8. Přepnutí a návrat jsou vidět tam, kde je dnes vidět přepnutí (detail běhu, `retries[].harness_switch`, popis PR).

## Akceptační kritéria

- V UI nastavení projektu jde zapnout automatické přepnutí, sestavit řetěz záložních harnessů v pořadí a zapnout návrat. Po uložení a znovunačtení se hodnoty zobrazí správně, včetně zděděných.
- Test (fake harnessy): harness A vrátí kvótu, pak B vrátí kvótu, pak doběhne C. Přepnutí jsou zaznamenaná v tomto pořadí.
- Test: vyčerpá se celý řetěz a běh skončí selháním `quota`.
- Test: se zapnutým návratem a obnoveným limitem se použije harness o krok výš v řetězu. Bez návratu zůstane aktuální.
- Stávající testy záložního harnessu (`test_quota_fallback.py`, `test_harness_quota.py`) dál procházejí.
- Frontend testy pro nový prvek v `ContainerSettings`. Statický build dashboardu je přegenerovaný.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
