---
id: INTENT
title: Ze záměru backlog
workflow: build-test-review
writes: [aifactory/, justfile]
auto_continue: true
auto_merge: true
test_timeout: 900
---

Člověk napíše záměr jednou větou a factory z něj navrhne step s tasky, závislostmi, writes a workflow podle skutečného kódu. Návrh se schvaluje jako diff backlogu.
