---
id: HEAL
title: Samoopravná selhání
workflow: build-test-review
writes: [aifactory/, justfile]
auto_continue: true
auto_merge: true
test_timeout: 900
---

Každé selhání běhu má srozumitelný druh, vysvětlení a akci na jeden klik. Kde je akce bezpečná, provede ji factory sama. Výchozí data (HAIFA, 10/2026): 33 ze 132 běhů selhalo, nejčastěji accept not met (10), builder bez práce (6), vyčerpaná kvóta (4), zápis mimo writes (3).
