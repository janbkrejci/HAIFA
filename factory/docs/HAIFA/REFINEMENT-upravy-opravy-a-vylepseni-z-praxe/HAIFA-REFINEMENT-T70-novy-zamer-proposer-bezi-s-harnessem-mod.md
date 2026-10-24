# Nastavení proposeru podle cíle Nového záměru

Proposer používá při zadání projektu nebo stepu zděděné hodnoty `harness`, `model` a `thinking` cílového kontejneru. Výběr využívá helpery T69: změna harnessu ve stepu zahodí model zděděný z jiného harnessu a chybějící hodnoty doplní nastavení počítače. Override se aplikuje na RunConfig před přípravou rosteru a výběrem proposeru.

Automatické umístění používá výchozí nastavení počítače z topbaru. Později navržené umístění nastavení agenta nemění. Bez nastaveného výchozího harnessu počítače a bez explicitního harnessu kontejneru zůstává výběr na rosteru. CLI `factory backlog propose` i dashboard používají stejný postup.

Skutečně vybraný harness, model a thinking se ukládají do ignorovaného runtime souboru `.factory/data/backlog-propose/<job_id>/agent.json`. Upřesnění načte tuto vazbu a pokračuje ve stejné session a pracovním adresáři i po změně nastavení počítače nebo kontejneru. První kolo vždy počítá nový výběr. Upřesnění starší session bez uložené vazby ji dopočítá. Gate correction zůstává ve stejném běhu agenta.

Povolení a dostupnost výsledného harnessu se kontrolují v každém kole. Zakázaný nebo nedostupný harness vrací `agent_unavailable`; chyby override zachovávají svůj kód, například `invalid_override`. Nedochází k přepnutí na jiný harness.

Stav intent jobu obsahuje `agent: {harness, model, thinking}`. Před výběrem je hodnota `null`. Callback ji nastaví před voláním agenta, takže je dostupná už během práce, a zůstává při upřesnění, jeho chybě i po použití návrhu. Hodnoty odpovídají výslednému rosteru a požadavku předanému harnessu. Frontend se v této změně neupravuje.

## Ověření

- Workflow a API: `just pytest tests/workflow/test_backlog_propose.py tests/web/test_web_intent.py -n0` — 58 testů prošlo (závěrečný běh 73,92 s). Pokrytí zahrnuje skutečná volání fake Codex rozhraní přes CLI i API, dědění a změnu harnessu, auto s jiným harnessem cíle, roster fallback, korekci a upřesnění se stabilní session, strukturované chyby a metadata za běhu i po neúspěšném upřesnění.
- Browser: `just pytest tests/e2e/test_intent_browser.py -n0` — 1 test prošel, včetně původního toku návrhu, upřesnění a použití.
- Ruff lint, kontrola formátu a mypy prošlo pro všech pět změněných Python souborů.

První běh 58 testů prošel. Následné ověřování rozšířených testů zaznamenalo souběžné změny uživatelského HAIFA adresáře v kontrole teardownu; funkční aserce prošly. Závěrečný úspěšný běh používá oddělený `HAIFA_HOME` v ignorovaném runtime adresáři pracovního stromu. Testy si nadále vytvářejí vlastní dočasná nastavení a žádný model ani službu nevolají.
