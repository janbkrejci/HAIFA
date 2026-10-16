# AI průvodce: backend

Dashboard má API pro konverzaci s průvodcem, agentem, který odpovídá na otázky o všech
registrovaných repech z jejich dat. Panel v dashboardu zatím chybí (GUIDE-S02-T02).

## Jak to funguje

- Vlákno založí `POST /api/assistant/threads`. Zpráva jde přes
  `POST /api/assistant/threads/{id}/messages` s `{text, screen?: {repo, task, run}}`.
  Odpověď se streamuje na `GET /api/assistant/threads/{id}/stream` (SSE).
  Seznam vláken vrací `GET /api/assistant/threads`.
- Průvodce běží s harnessem a modelem z nastavení počítače (Nastavení → Harnessy).
  Bez nastavení se použijí výchozí hodnoty agenta `guide` z knihovny.
  Další zprávy ve vlákně pokračují ve stejné session harnessu.
- Vlákna jsou v `$HAIFA_HOME/assistant/threads/`. Do rep se nic nezapisuje.

## Co průvodce smí

- Jen příkaz `./guide` ve svém pracovním adresáři mimo repa, tedy read-only příkazy
  `factory ... --json` (`task list/show/runs`, `backlog list/check`, `check`,
  `config show`, `library list/show`, `workflow show`) a dotazy `SELECT` na trace DB.
  Cokoli jiného se odmítne.
- claude to vynucuje režim oprávnění `dontAsk` s povoleným příkazem `./guide`,
  codex sandbox `read-only`. Pi tohle omezení nemá, chrání ho jen kontrola zápisu.
- Po každé odpovědi se kontroluje hlavní checkout všech registrovaných rep. Zápis
  agenta se vrátí a odpověď skončí chybou. Stejně jako u běhu tasku platí, že se vrátí
  i ruční úprava provedená v repu během odpovědi. Záloha zůstane v `turns/NNN/`.
- Hodnoty z `.env` souborů a tajných proměnných prostředí se před odesláním agentovi
  nahradí `[redacted]`.

## Prompt

Prompt je knihovní agent `guide` (`seed/agents/guide/`). Upravit ho jde v knihovně
jako ostatní agenty. Protože knihovna se dědí do rosteru, `guide` se objeví
i v rosteru každého repa (`writes: []`, žádná role ho nevolá).
