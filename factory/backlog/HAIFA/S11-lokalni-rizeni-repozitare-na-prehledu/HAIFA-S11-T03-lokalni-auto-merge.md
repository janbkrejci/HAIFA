---
id: HAIFA-S11-T03
title: Jednotná místní politika auto merge
status: done
archived: true
depends_on: [HAIFA-S11-T02]
writes: [aifactory/]
test_timeout: 3600
---

## Zadání

### Ověření na Windows po běhu 38777bbd

Pro tento task je rozpočet ověření 3600 s. Původních 1200 s nebylo podloženo měřením: vybraný blok 441 testů skončil po 900 s kolem 19 %, kontrolní průchod po opravě testu dosáhl přibližně 38 % až po více než 15 minutách. Jde o lokální rozpočet tohoto rozsáhlého tasku, nikoli změnu globálních limitů. Zachovat kontroly všech upravených testových souborů a relevantních přímých volajících; rozdělit je do samostatných příkazů po souborech či menších logických skupinách, aby worker nežil celý blok. Pro nynější Windows stroj použít nejvýše dva pytest workery. Limit každého příkazu nastavit s rezervou podle měření, součet v rámci rozpočtu; nepovažovat timeout ani pád workeru za úspěch.

Git Bash je nainstalovaný v C:/Program Files/Git/bin; prostředí spouštějící Factory musí mít tento adresář na PATH. just lint a just typecheck s touto cestou prošly. Test test_failed_run_is_not_merged měl zastaralé očekávání důvodu zastavení při lokálním auto_continue=false; v rozpracovaném worktree je rozšířen na on/off a vždy vyžaduje neúspěšný běh bez PR/merge.

Při diagnostice byl zachycen i nativní pád Windows fatal exception: access violation během časovaného výpisu zásobníků faulthandler_timeout=90, ještě před ukončováním diagnostického procesu. Pro retry tento diagnostický časovač nepoužívat (faulthandler_timeout=0); pevný timeout runneru i hlášení skutečných pádů zůstávají. Příčina nativního pádu není prokázaná; související opravu sleduje T07. Lokální důkazy jsou v .factory/data/sessions/38777bbd/context_handoff/operator-backend-check.log a operator-publish-check.log, necommitovat je. Bez nových změn neopakovat již průkazně úspěšné kontroly; předchozí pokrytí zachovat a případné převzetí výsledků přesně doložit v testovacím plánu.

Nahradit backlogovou auto_merge politiku lokální službou ve všech automatických cestách: run/queue.py, review/automerge.py, review/stack.py, publish/retry, background PR refresh a webové odvození stavu PR. Oddělit tuto volbu od base_pr_merge a ručního approve. Neoslabit review, CI, write guards, konflikty ani merge lock.

Změnu auto_merge znovu vyhodnotit před automatickou operací merge, včetně čekání na CI a stacked PR. Off zastaví dosud neodeslané automatické merge; již odeslaný požadavek hostingu nelze vzít zpět. Přesně popsat hranici a stav čekajícího PR. Auto_continue off nebrání dokončení současného PR, pokud auto_merge zůstává on; auto_merge off samo nesmí zapnout ani vypnout auto_continue. Manuální approve je dál explicitní akce.

Hotovo: CLI, worker i Přehled uvádějí stejnou účinnou hodnotu a zdroj; změna nepotřebuje commit. Regrese pro true ve frontmatteru + lokální false, off při CI čekání a před merge, chybějící/poškozené lokální nastavení, on se splněným i nesplněným review/CI. Testovat kombinace obou přepínačů. Kandidáti: run/test_auto_merge.py, run/test_task_publish.py, review/test_ci_gate.py, review/test_approve_continue.py, web/test_web_pr_refresh.py, test_web_review.py a test_web_backlog.py; výběr dle dotčeného chování.

## Běhy

<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-09 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/207 · náklady $0.00

