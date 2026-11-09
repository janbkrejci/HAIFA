---
id: HAIFA-S11-T03
title: Jednotná místní politika auto merge
status: todo
depends_on: [HAIFA-S11-T02]
writes: [aifactory/]
test_timeout: 1200
---

## Zadání

Nahradit backlogovou auto_merge politiku lokální službou ve všech automatických cestách: run/queue.py, review/automerge.py, review/stack.py, publish/retry, background PR refresh a webové odvození stavu PR. Oddělit tuto volbu od base_pr_merge a ručního approve. Neoslabit review, CI, write guards, konflikty ani merge lock.

Změnu auto_merge znovu vyhodnotit před automatickou operací merge, včetně čekání na CI a stacked PR. Off zastaví dosud neodeslané automatické merge; již odeslaný požadavek hostingu nelze vzít zpět. Přesně popsat hranici a stav čekajícího PR. Auto_continue off nebrání dokončení současného PR, pokud auto_merge zůstává on; auto_merge off samo nesmí zapnout ani vypnout auto_continue. Manuální approve je dál explicitní akce.

Hotovo: CLI, worker i Přehled uvádějí stejnou účinnou hodnotu a zdroj; změna nepotřebuje commit. Regrese pro true ve frontmatteru + lokální false, off při CI čekání a před merge, chybějící/poškozené lokální nastavení, on se splněným i nesplněným review/CI. Testovat kombinace obou přepínačů. Kandidáti: run/test_auto_merge.py, run/test_task_publish.py, review/test_ci_gate.py, review/test_approve_continue.py, web/test_web_pr_refresh.py, test_web_review.py a test_web_backlog.py; výběr dle dotčeného chování.

## Běhy

<!-- doplňuje HAIFA při schválení PR -->

