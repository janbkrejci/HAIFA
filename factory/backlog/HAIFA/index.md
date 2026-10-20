---
id: HAIFA
title: Helios AI Factory
workflow: build-test-review
writes: [aifactory/, justfile]
auto_continue: true
auto_merge: true
test_timeout: 900
quota_switch_back: true
quota_switch: [claude]
harness: codex
---

Vývoj HAIFA řízený samotnou HAIFA. Rozhodnutí jsou v `docs/decisions.md`, návrh dashboardu pro více repozitářů v `docs/design/multi-repo-dashboard.md`.
