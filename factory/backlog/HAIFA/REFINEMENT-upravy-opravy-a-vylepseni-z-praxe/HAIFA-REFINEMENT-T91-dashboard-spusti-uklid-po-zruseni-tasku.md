---
id: HAIFA-REFINEMENT-T91
title: Dashboard spustí úklid po zrušení tasku a pravidelně ve všech repech
status: done
archived: true
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T90]
writes: [aifactory/src/aifactory/web/app.py, aifactory/tests/web/test_web_cleanup.py]
---

## Zadání
## Problém

Task se ruší v dashboardu (status `cancelled` přes API backlogu v `aifactory/src/aifactory/web/app.py`). Jeho worktree a větve pak čekají až na další běh. Repo, ve kterém se dlouho nic nespouští, se neuklidí nikdy.

## Co udělat

- Po úspěšné změně stavu tasku na `cancelled` přes API dashboardu spustit na pozadí `clean_worktrees` z `aifactory.review` (z HAIFA-REFINEMENT-T90) pro dané repo. Požadavek nesmí čekat na úklid a jeho chyba nesmí změnu stavu shodit, jen se zaloguje.
- V `lifespan` v `web/app.py` přidat periodický úklid (např. každou hodinu a jednou po startu) pro všechna registrovaná repa vedle existujících `periodic(...)` úloh. Úklid poběží ve vlákně, ne v event loopu. Repo, kde zrovna běží úklid, se nespustí podruhé.
- Na nic jiného v dashboardu nesahat, UI se nemění.

Hotovo znamená:
- Test v `aifactory/tests/web/test_web_cleanup.py` ukazuje, že po zrušení tasku přes API se zavolá úklid daného repa a odpověď API přijde bez čekání na něj.
- Test ukazuje, že periodický úklid projde registrovaná repa a chyba v jednom repu nezastaví ostatní.
- Existující testy `test_web_app.py` procházejí.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-27 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/180 · náklady $0.00
