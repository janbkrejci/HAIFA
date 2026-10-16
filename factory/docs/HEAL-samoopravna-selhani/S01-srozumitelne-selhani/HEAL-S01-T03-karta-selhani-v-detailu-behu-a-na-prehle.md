# HEAL-S01-T03: Karta selhání v detailu běhu a na Přehledu

## Co se změnilo

Detail běhu, který neuspěl (selhal, byl zastaven nebo přerušen), začíná hned pod nadpisem
kartou selhání. Karta čte `failure_kind` a `failure_detail` běhu (HEAL-S01-T01, T02) a
ukazuje:

- druh selhání česky (např. „Nesplněná podmínka accept“, „Zápis mimo writes“,
  „Vyčerpaná kvóta“),
- jednu větu z dat běhu,
- podrobnosti podle druhu,
- tlačítka akcí, které pro druh existují.

Když chyba běhu říká víc než věta karty, je celá pod „Celá chybová zpráva“.

| Druh | Věta | Podrobnosti | Akce |
| --- | --- | --- | --- |
| `accept_not_met` | chyba z T02 („Review neschválilo ani po 2 kolech: …“), u staršího běhu výraz `accept` | výtky review, neprošlé kontroly testu, `accept`, hodnoty v podmínce, kola smyček | Pokračovat, Zrušit task |
| `nothing_to_do` | agent a jeho shrnutí | — | Zrušit task |
| `quota` | harness, model a agent | harness, model, hláška harnessu | Pokračovat, Zrušit task |
| `writes_violation` | agent a počet cest | cesty mimo writes, povolené writes | Pokračovat, Zrušit task |
| `invalid_output` | neplatný JSON, nebo kontroly výstupu (gates) neprošly ani po opravách | chyba JSON / neprošlé kontroly | Pokračovat, Zrušit task |
| `process_gone` | PID procesu | — | Pokračovat, Zrušit task |
| `stopped` | poznámka operátora, Ctrl+C nebo signál | — | Pokračovat, Zrušit task |
| `other` | první řádek chyby | celá chyba | Pokračovat, Zrušit task |

„Pokračovat“ je `factory task retry` s volitelnou poznámkou (dříve tlačítko „Navázat“
v hlavičce detailu běhu; v detailu tasku zůstává „Navázat“). „Zrušit task“ se nejdřív
zeptá a pak nastaví tasku `status: cancelled`. Běh i jeho větev zůstanou. Další akce
přidá HEAL-S02.

Model u kvóty: engine teď do `failure_detail` kvóty přidá `agent` a `model`
(`engine/agents.py`). U staršího běhu bez modelu ho karta vezme z fáze, která neuspěla.

## Přehled a Běhy

- Přehled (sekce Selhalo) ukazuje u selhaného tasku druh selhání místo začátku chyby.
  `GET /api/overview` vrací u položek `failed` pole `failure_kind`. Starší trace DB bez
  sloupce i běh zapsaný bez druhu čte jako `other`.
- Seznam běhů ukazuje druh pod stavem. Panel řetězů ukazuje druh místo prvního řádku chyby.
  Celá chyba je v tooltipu.

## Testy

- `web/src/components/runs/FailureCard.test.ts`: karta každého druhu a obě akce.
- `RunDetail`, `RunsList`, `ChainPanel`, `OverviewView`, `lib/overview` (vitest).
- `tests/web/test_web_overview.py`: `failure_kind` v Přehledu, i bez sloupce.
- `tests/harness/test_harness_quota.py`: agent a model v detailu kvóty.
- `tests/e2e/test_failure_card_browser.py`: skutečný běh, který selže na `accept`. Kontroluje
  kartu, druh na Přehledu a v Bězích a zrušení tasku z karty.
