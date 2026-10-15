---
id: HAIFA-TODO-T04
title: Ukládat merged_at podle času merge od providera
status: done
depends_on: []
related: [HAIFA-REFINEMENT-T33]
---

## Zadání
Přidat do PrStatus pole merged_at: str | None = None. GitHub: přidat mergedAt do _STATUS_FIELDS a předat ho u stavu MERGED. Azure: closedDate u status completed. Local: None. Hodnotu normalizovat na UTC ISO s milisekundami (formát engine.utils.now_iso). V _record_state a _refresh_sync_prs použít status.merged_at or _now(). Upravit testy providerů (tests/providers/test_providers_github.py, az_fake.py) a doplnit test, že se merged_at bere od providera.

### Původ

Vznikl při běhu `4ee8a4c3` tasku `HAIFA-REFINEMENT-T33` (Přehled ukazuje v review PR sloučené mimo factory), v kroku `plan` (agent planner).
Důvod: Bod 4 tasku HAIFA-REFINEMENT-T33 vyžaduje změnu v aifactory/src/aifactory/providers/, která není mezi povolenými cestami běhu. PrStatus (providers/base.py) nemá čas merge; GitHub _STATUS_FIELDS ani Azure _parse ho nečtou. review/flow.py::_record_state a review/sync.py::_refresh_sync_prs proto dál zapisují merged_at=_now().

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T33 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-15 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/47 · náklady $1.19
