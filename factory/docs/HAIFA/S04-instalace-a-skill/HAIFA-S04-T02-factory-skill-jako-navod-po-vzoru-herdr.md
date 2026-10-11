# HAIFA-S04-T02: použití generovaného skillu

`factory --skill` nyní začíná YAML front matter a lze jeho Markdown uložit jako
`SKILL.md` agenta. Po změně verze z `factory --version` vygenerujte obsah znovu.
`factory --skill --json` vrací stejný text v `data.skill`; struktura příkazů,
chybových kódů a envelope zůstává zachována.

Na začátku agent spustí `factory check --json`: nové repo inicializuje, sssf nebo
starou konfiguraci bez manifestu onboarduje jednou, onboardované repo adoptuje.
Instalace vysvětluje výběr agentů, vazby, kontrolu souborů a digestu, potvrzení
stejných voleb s `--expect` a ověření factory a backlogu po commitu či sloučení PR.

Tabulka `.factory/config.yaml` se generuje z popisů a defaultů modelů
ProjectSettings, AzureSettings a GeneratedOutput. Nový klíč musí mít popis;
regresní testy ověřují i změnu metadat modelu. Dokumentovány jsou agents.yaml,
povinné system.md a user.md, proměnné, testovací krok a původ položek v manifestu.
Postup plán → backlog ukazuje založení projektu, stepu a tasku s děděním nastavení.

Ověření: cílený pytest pro test_skill.py, config/test_config_settings.py a
config/test_config_loader.py; `just typecheck` a `just lint`. Celou sadu spouští
navazující testovací fáze.
