# HAIFA-REFINEMENT-T21: redesign stránky Task

## Co se změnilo

Stránka tasku má méně inputů a žádné duplicitní ovládání. Úpravy se dělají na jednom místě, ve formuláři. Návrh agenta je jedno velké tlačítko.

### Tlačítko „Vylepšit agentem“

- Velké zelené tlačítko s ikonou kouzelné hůlky. V detailu je vpravo nahoře, jako poslední v řadě tlačítek. Ve formuláři je vpravo od nadpisu.
- Harness, model a thinking level se nevybírají. Návrh udělá agent, se kterým by task běžel: hodnoty se dědí z tasku, stepu, projektu, `config.yaml` a nakonec z nastavení harnessů počítače. Když nic z toho harness neurčí, použije se plan agent z rosteru, stejně jako dřív.
- Když ve formuláři ručně nastavíš harness, model nebo thinking v „Další nastavení“, vylepšení je použije taky.
- V read-only detailu tlačítko otevře editační formulář a návrh v něm hned spustí. Tlačítko „Upravit“ formulář otevře bez agenta.
- Dokud agent pracuje, tlačítko ukazuje spinner a pole formuláře jsou zamčená. Návrh se zapíše rovnou do formuláře (titulek, zadání, workflow, writes, vazby, parametry), už se nepotvrzuje zvlášť. Pod tlačítkem zůstane krátká poznámka: proč agent změny navrhl, který agent to byl (`harness · model · thinking`) a cena nebo tokeny. Poznámka jde zavřít.
- Uložení je pořád ruční (Uložit). Neuložený návrh se dá zahodit tlačítkem Zrušit.
- Pro task, který je hotový, zrušený, běží nebo je v review, je tlačítko vypnuté. Tooltip říká, že task už nejde měnit. Ve formuláři nového tasku vysvětlí tooltip, co chybí (step nebo titulek).

### Formulář (nový task i úprava)

Shora dolů:

1. Nadpis a vpravo „Vylepšit agentem“.
2. U nového tasku Step a Kód vedle sebe.
3. Titulek.
4. Zadání, větší pole (14 řádků) přes celou šířku.
5. Workflow a pod ním „Navrhnout workflow“. Ten zůstává, protože umí navrhnout i nové workflow.
6. Sbalené „Další nastavení“: status a auto-merge (jen u úpravy), writes, Závisí na a Související, parametry (harness, model, thinking, source, target, limit testů, auto continue a u nového tasku auto-merge). Prázdný parametr znamená zděděnou hodnotu. Sekce je rozbalená, když ji task používá (vlastní writes, vazby, auto-merge, parametry nebo status jiný než „K řešení“) nebo když agent některé z těchto polí změnil.
7. Uložit a Zrušit.

Nově jde ve formuláři nastavit i parametr `thinking`, výběrem z úrovní přemýšlení.

### Detail (read-only)

- V hlavičce jsou Spustit, Upravit, Zrušit (jen u tasku, který ještě neběžel) a „Vylepšit agentem“.
- Karta „Spuštění“ se jmenuje „Nastavení“. Workflow v ní je jen jako text („(zděděno)“, když ho task nemá vlastní). Výběr workflow s tlačítkem „Přiřadit“ a tlačítko „Upravit a navrhnout workflow“ zmizely. Workflow se mění ve formuláři.
- Ve Vazbách zmizela pole a tlačítka „Přidat“. Vazby se přidávají ve formuláři v „Další nastavení“. Křížkem se vazba dál odebere rovnou z detailu.
- Přepínač auto continue zůstal v detailu, protože patří k frontě, ne k souboru tasku.

## API

- `POST /api/backlog/task-advice` bez `harness` a `model` použije zděděné nastavení tasku. Explicitní `harness` a `model` dál fungují.
- Job (`GET /api/backlog/task-advice/{id}`) nově vrací `advisor` (`harness`, `model`, `thinking`), tedy kdo návrh dělá.
- `GET /api/backlog/task-advice/options` zůstal, UI ho už nevolá.
