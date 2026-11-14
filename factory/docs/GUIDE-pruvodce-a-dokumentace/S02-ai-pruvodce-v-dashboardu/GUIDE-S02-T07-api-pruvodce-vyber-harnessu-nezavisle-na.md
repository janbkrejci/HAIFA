# Výběr harnessu průvodce přes API

Nové vlákno může použít jiný harness než jeho repozitář. Například repozitář s místním
`pi` může založit konverzaci na Claude:

```http
POST /api/assistant/threads
Content-Type: application/json

{"harness":"claude","screen":{"repo":"REPO_ID"}}
```

Volitelný `harness` má přednost před nastavením repozitáře i výchozím harnessem
počítače. Model a thinking se berou z nastavení počítače pro zvolený harness přes
`harness.settings.effective_override`. Model původního harnessu se nepřenáší.
Volba funguje i při vypnutém pi repozitáře nebo pi bez modelu. `screen` se stále
validuje a vlákno zůstává omezené na původní repozitář.

Bez parametru `harness` se zachovává dosavadní dědění a fallback. Explicitní neznámý,
vypnutý nebo nepodporovaný harness vrátí HTTP 409 `harness_unavailable` bez založení
vlákna a bez fallbacku. Totéž platí pro chybějící místní model v existujícím nastavení
počítače nebo model s uloženým neúspěšným testem. Prázdný parametr nebo jiný typ
vrací HTTP 400 `usage_error`.

`GET /api/assistant/harnesses` vrací v běžné obálce API:

```json
{"data":{"harnesses":[{"harness":"claude","model":"sonnet","thinking":"medium","usable":true,"reason":null}]}}
```

Seznam obsahuje pouze průvodcem podporované a na počítači zapnuté harnessy
(`claude`, `codex`). Zapnutá, ale nepoužitelná konfigurace má `usable: false`
a důvod v `reason`. Thinking se normalizuje podle stávajících místních pravidel.
Pokud soubor nastavení počítače neexistuje, oba harnessy jsou implicitně povolené
a prázdný model znamená výchozí model adaptéru. Nečitelná struktura nastavení
vrací HTTP 409 `harness_unavailable`.

Seznam nespouští model, neověřuje přihlášení a nezaručuje úspěšný běh ani dostupnost
transportu. Codex dále prochází izolovaným `assistant_codex`; Claude používá omezení
příkazů na `./guide`. Pi zůstává odmítnutý při explicitní volbě i při obnově dříve
uloženého vlákna.

Harness, model a thinking se ukládají do stávajícího `thread.json`. Další zprávy,
historie i obnovení session používají uloženou volbu. API pro zprávy nepřijímá změnu
harnessu existující konverzace; pro jiný harness je potřeba nové vlákno.
