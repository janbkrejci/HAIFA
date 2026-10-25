---
id: HAIFA-TODO-T26
title: Hlídač zápisů hlásí writes_violation u nového souboru ve writes pod .factory/
status: done
depends_on: []
---

## Zadání
Běh `5b840040` tasku `HAIFA-LEARN-T07` (workflow `build-review`, fáze `build`, harness codex) selhal s `writes_violation`, ačkoli builder psal jen do writes tasku.

Postup: task má `writes: [".factory/prompts/reviewer/"]`, adresář v base neexistuje (reviewer se dědí z knihovny), `protected_files` obsahuje `.factory/`. Builder vytvořil nové soubory `.factory/prompts/reviewer/system.md` a `user.md` (`git status`: `?? .factory/prompts/`).

Skutečně: gate `diff_matches_claims` prošel (soubory existují), pak `permission_breach`: obě cesty hlášené jako `deleted`, `failure_detail.paths` leží ve writes, payload má `writes: null`. `task retry --allow-writes` nepomůže (cesty už ve writes jsou).

Očekávané: výslovné writes tasku mají přednost před `protected_files`; nový soubor se nehlásí jako `deleted`.

Hotovo znamená:
- Nový soubor pod `protected_files`, který writes tasku výslovně povolují (i v neexistujícím adresáři), projde hlídačem.
- Hlídač nehlásí vytvořený soubor jako `deleted`.
- Regresní test pro tento případ; ochrana `.factory/` mimo writes tasku zůstává (test).

Mimo rozsah: pravidlo lekce `L328f600c` (HAIFA-LEARN-T07).

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-25 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/163 · náklady $0.00
