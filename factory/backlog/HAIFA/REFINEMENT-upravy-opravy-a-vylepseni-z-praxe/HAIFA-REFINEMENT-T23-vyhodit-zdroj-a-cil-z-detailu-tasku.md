---
id: HAIFA-REFINEMENT-T23
title: Vyhodit zdroj a cíl z detailu tasku
status: done
workflow: build-test-review
depends_on: []
related: [HAIFA-REFINEMENT-T11, HAIFA-REFINEMENT-T21, HAIFA-REFINEMENT-T07, HAIFA-S01-T38]
writes: [aifactory/]
---

## Zadání
Odstranit parametry tasku `source` (Zdroj) a `target` (Cíl) z detailu tasku a odstranit vše s nimi související.

Co dnes jsou: volné texty dědičné po úrovních (task, step, projekt). Agent je dostane v hlavičce zadání (`- source: …` / `- target: …`) a HAIFA je nijak nekontroluje.

Rozsah (vše s tím související):
- Web UI: pole a nápovědy v `TaskForm.vue` (`parameterFields`, tooltipy), popisky `source`/`target` v `SETTING_LABELS` (`web/src/lib/backlog.ts`), nastavení kontejneru (ContainerSettings), BacklogView a fixtures a testy frontendu.
- Backend backlogu: `INHERITED_KEYS` v `backlog/model.py`, `backlog/taskfile.py`, `backlog/edit.py` a `web/backlog.py`.
- Hlavička zadání agenta v `run/task.py` (`task_prompt`): řádky `source`/`target` zmizí.
- Návrh parametrů tasku agentem (`workflow/adaptive.py`): `source`/`target` už nejsou mezi navrhovanými parametry.
- CLI: volby `--source`/`--target` při úpravě kontejneru (`cli.py`).
- Dokumentace: `guide/05-backlog.md` a `skill/skill.md` (příklad `source:`/`target:`, popis promptu).
- Testy backendu, které na tyto klíče spoléhají.
- Sestavený frontend ve `web/static`, pokud se v repu commituje.

Nesouvisí, nesahat: `config.source` (ConfigSource/CommitSource), cíl `base`/`pr` u operací factory (FactoryOperation, web/factory.py, config_edit, install_commit, publish), vlastnost `source` komponenty MarkdownView a `origin.source` v `derived.py`.

Akceptační kritéria:
- Detail ani formulář tasku a nastavení kontejneru už nezobrazují Zdroj ani Cíl.
- API backlogu ani CLI už `source`/`target` jako parametr tasku nebo kontejneru nenabízí.
- Hlavička zadání agenta neobsahuje řádky `source`/`target`.
- Návrh parametrů tasku agentem už `source`/`target` neobsahuje.
- Dokumentace už `source`/`target` jako parametr tasku nezmiňuje.
- Testy frontendu i backendu jsou zelené.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-15 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/36 · náklady $2.75
