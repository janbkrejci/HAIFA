---
id: HAIFA-S04-T02
title: "`factory --skill` jako návod po vzoru herdr"
status: done
depends_on: [HAIFA-S03-T04, HAIFA-S04-T01, HAIFA-S01-T10, HAIFA-S01-T12, HAIFA-S06-T02, HAIFA-S06-T03]
---

## Zadání
Přepiš `factory --skill` na návod pro agenty po vzoru `herdr --skill`: jak přidat celou factory do stávajícího repa, jak vytvořit konfiguraci a jak vytvořit backlog.

Where: `aifactory/src/aifactory/skill/` (`skill.md`, `render.py`), `aifactory/src/aifactory/config/settings.py` (popisy klíčů), `aifactory/tests/test_skill.py`.

Done means:
- Výstup začíná YAML front matter (`name: factory` a `description` s tím, kdy skill použít a kdy ne), takže jde uložit jako skill agenta. Uvádí verzi a říká, že po změně `factory --version` se má vygenerovat znovu.
- Na začátku je kontrola předpokladů `factory check --json`: podle akce nálezu agent pokračuje `factory init` (repo bez factory), `factory onboard` (sssf nebo `.factory/` bez manifestu, jednou na repo) nebo `factory adopt` (onboardované repo).
- Postup Přidat factory do stávajícího repa: `factory init --dry-run --json` s `--agents` a `--bind`, ukázat soubory a digest uživateli, `factory init --commit --expect <digest> --json`, při `push_failed` po souhlasu `--pr`, ověření `factory check` a `factory backlog check`.
- Reference `.factory/config.yaml`: každý klíč s významem a výchozí hodnotou, generovaná z kódu, aby nezastarala.
- Agenti a prompty: klíče `agents.yaml`, povinné soubory promptů, proměnné dostupné v promptech a co spouští krok test. Popisuje i `.factory/manifest.yaml` (původ položek, značka onboardingu, běh z něj čte jen `format`), sloty a vazby a to, že úprava promptu v repu udělá položku `modified` a `factory config export` ji vrátí do knihovny.
- Postup Plán → backlog zakládá projekty a stepy příkazem `factory backlog add`, nastavení zapisuje `factory backlog edit` a používá úrovně project → step → task.
- Reference příkazů a chybových kódů zůstává generovaná.
- Testy: front matter, sekce, popis každého klíče konfigurace, `factory check`, `factory init --dry-run` a `factory onboard` v postupech.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: příkaz, který skill sám uloží do repa nebo do adresáře skillů, změna `docs/product-brief.md`, postupy knihovny, aktualizace, operací ve více repech a upgradu HAIFA (HAIFA-S07-T04).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/87 · náklady $0.00
