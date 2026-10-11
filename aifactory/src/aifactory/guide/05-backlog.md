# Backlog a tasky

Backlog je strom markdown souborů v repu pod `<docs_root>/backlog/` (výchozí `factory/backlog/`). Výchozí úrovně jsou **projekt**, **step** a **task**; jiné názvy úrovní nastaví správce v `levels` konfigurace repa a dashboard je pak používá v tlačítkách.

```
factory/backlog/
  WEB-web/
    index.md                  projekt WEB
    S01-prihlaseni/
      index.md                step WEB-S01
      WEB-S01-T01-formular.md task WEB-S01-T01
```

Každý projekt a step má `index.md` s kódem, názvem a výchozími hodnotami pro tasky. Id tasku je `<step>-<kód>`, například `WEB-S01-T01`.

## Obrazovka Backlog

Nahoře jsou tlačítka **Nový projekt**, **Nový step**, **Nový task** a **Obnovit**, filtry projektu a stepu a přepínač **Skrýt hotové**. Backlog zobrazíš jako **Strom**, nebo **Kanban**.

**Strom** ukazuje projekty a stepy s počty tasků podle stavu, odznaky **auto** (zapnuté auto-continue) a **merge** (zapnutý auto-merge) a přepínače **Auto-continue** a **Auto-merge** se třemi polohami: Zděděno, Zapnuto, Vypnuto. Odkaz u projektu či stepu otevře graf závislostí a jeho **Nastavení**.

**Kanban** má sloupce podle stavu tasku. Auto-continue bere tasky ze sloupce **Připraveno** shora dolů; pořadí změníš šipkami. Tlačítko **Vyloučit z auto continue** přesune task do sloupce **Odloženo**: řetěz ho nespustí, ručně ho spustit jde. Pořadí a vyloučení jsou uložené lokálně a necommitují se.

## Stavy tasku

| Stav | Význam |
| --- | --- |
| Hotovo | Pull request byl schválen a mergnut (`status: done`). |
| Zrušeno | Task je zrušený (`status: cancelled`). |
| Běží | Task má běžící běh. |
| V review | Task má otevřený pull request. |
| Blokováno | Některá závislost (`depends_on`) není hotová. |
| Připraveno | Task jde spustit. |
| Bez workflow | Task nemá workflow, a proto nejde spustit. |

V souboru tasku je uložen jen `status`: `todo`, `done` nebo `cancelled`. Ostatní stavy dashboard odvozuje. Hotový task nastavuje jen schválení pull requestu.

## Detail tasku

Kliknutím na task otevřeš jeho detail: **Zadání**, **Běhy** (všechny běhy s větví a stavem), **PR** (stav a odkaz do Review), kartu **Spuštění** (workflow, auto-merge, writes, pozice ve frontě auto-continue) a **Vazby** (**Závisí na**, **Blokuje**, **Související**). Tlačítka **Spustit**, **Upravit** a **Zrušit**.

Panel nahoře ukáže „Připraveno ke spuštění“, nebo co je před spuštěním potřeba (workflow, závislosti, commit backlogu).

## Formulář tasku

- **Titulek** a **Kód** (volitelný; jinak další volné číslo `T01`, `T02`…).
- **Zadání:** co má agent udělat. Piš ho jako zadání pro kolegu: cíl, kontext, kritéria hotového. Zadání je markdown.
- **Workflow:** posloupnost kroků běhu. Prázdné znamená zděděné z projektu či stepu.
- **Auto-merge:** po úspěšném review se pull request mergne sám.
- **Writes:** cesty (jedna na řádek, glob), které smí agenti měnit; nebo **dědit writes**. Bez nastavení na žádné úrovni platí celé repo.
- **Závisí na** a **Související:** vazby na jiné tasky nebo celé projekty a stepy.
- **Další parametry** (prázdné = zděděno): harness, model a thinking pro všechny agenty tasku a další.

Tlačítko **Navrhnout parametry tasku** nechá agenta navrhnout parametry podle zadání; návrh převezmeš tlačítkem **Použít návrh do formuláře**. **Navrhnout workflow** doporučí existující workflow, nebo navrhne nové včetně YAML. Oba pomocníci ukážou cenu dotazu.

## Dědění hodnot

Task dědí od nejbližší úrovně, která hodnotu nastavuje: task, step, projekt. Dědí se `workflow`, `writes`, `harness`, `model`, `thinking`, `source`, `target`, `test_timeout`, `auto_continue` a `auto_merge`. Explicitní prázdná hodnota (například `workflow: null`) dědění zastaví.

Nastavení projektu či stepu upravíš v jeho **Nastavení** (tabulka s platnou hodnotou, původem a vlastní hodnotou), nebo přes `factory backlog edit`. Změny se zapíší do `index.md` v pracovním stromu; běhy je použijí až po commitu backlogu.

## Závislosti

`depends_on` může odkazovat na task, nebo na celý step či projekt. Task je splněný, když je hotový; step či projekt, když jsou hotové všechny jeho nezrušené tasky. Task s nesplněnou závislostí je **Blokováno** a ručně ho spustíš jen volbou **Spustit přesto**. `related` je jen informativní. Graf závislostí stepu nebo projektu otevřeš z jeho řádku ve stromu.

## Commit backlogu

Úpravy z dashboardu i z `factory task add`/`edit` se zapisují do souborů v pracovním stromu. **Běhy čtou backlog z base**, proto změny commitni: tlačítkem **Commitnout backlog** v pruhu dole, nebo `factory backlog commit`. Commit obsahuje jen soubory backlogu, vyžaduje hlavní checkout na větvi base a má-li repo remote, odešle ho.

## Soubor tasku

Soubor tasku můžeš upravit i v editoru. Hlavička (front matter) a tělo:

```markdown
---
id: WEB-S01-T01
title: Přihlašovací formulář
status: todo
workflow: build-test-review
depends_on: [WEB-S01-T00]
writes: [web/src/login/]
---

## Zadání

Formulář s e-mailem a heslem, validace na klientovi, testy.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
```

Po ručních úpravách ověř backlog (`factory backlog check`) a commitni ho. Při schválení pull requestu HAIFA doplní do `## Běhy` řádek s datem, workflow, odkazem na PR a náklady.

## Zrušení tasku

**Zrušit** v detailu tasku nastaví `status: cancelled` (z CLI `factory task edit ID --status cancelled`). Zrušený task se nespouští a nepočítá se do závislostí stepu či projektu.
