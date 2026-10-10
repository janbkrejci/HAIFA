# Nastavení harnessů na počítači

Celá oblast usage limitů v topbaru otevírá nastavení Claude, Codex a pi. U každého
harnessu lze nastavit zapnutí a výchozí model ze seznamu; jeden zapnutý harness
je výchozí pro všechny factory na počítači. Dostupnost znamená přítomnost CLI.
Zapnutí používá přepínač. Výběr modelu otevírá samostatný modál s filtrem,
ovládáním klávesnicí a potvrzením vybraného modelu.
Vedle modelu lze vybrat výchozí thinking level z podporovaných možností. Codex
čte schopnosti z lokálního katalogu CLI, Claude používá tabulku
[podporovaných effort úrovní](https://platform.claude.com/docs/en/build-with-claude/effort)
a pi schopnosti instalovaného SDK. U vlastních pi modelů bez SDK metadata se
nabízí základní úrovně podle příznaku thinking v katalogu CLI. Neznámé modely
nenabízejí neověřené úrovně. Počítač je základ dědění: nabízí konkrétní úrovně,
předvybere default modelu a „Vypnuto“ nabízí pouze u modelů podporujících `off`.
Na této úrovni není volba zdědit nastavení agenta. „Zdědit“ patří na projekt,
task a další nižší úrovně. Starší uložené `null` se při použití vyhodnotí jako
default modelu, nikoli jako nastavení agenta. Opus 5.5 má default `medium`,
Sonnet 5.5 `high`; Opus 5.5 nelze vypnout.
Změna modelu nahradí nepodporovanou zvolenou úroveň defaultem nového modelu.
Projekt a task mohou tuto volbu přepsat; pro jejich odlišný model se při
nekompatibilní úrovni použije default tohoto modelu.

Nastavení se ukládá do `$HAIFA_HOME/harnesses.json` (standardně do konfiguračního
adresáře HAIFA), mimo repository. Samotné otevření modálu nic neukládá. Dokud
nastavení není uloženo, běhy zachovávají dosavadní definice agentů.

Při běhu mají přednost volby tasku před projektem a projektu před počítačem.
Jednorázové volby při spuštění mají přednost před taskem. Výslovné přepisy kroku
workflow se nadále použijí podle D13. Změna harnessu dědí model nového harnessu;
nepřenáší model z předchozího harnessu. Repo UI zobrazuje definice agentů, volby
harnessu/modelu se upravují v modálu počítače, projektu a tasku.

Tlačítko **Test** spustí konkrétní harness/model v dočasné složce s triviální
úlohou a očekává přesně `OK`. Výsledek, včetně času, se ukládá pro danou dvojici
do `$HAIFA_HOME/harness-tests.json`. Test má limit 60 sekund a neukládá session.
Claude a pi mají vypnuté nástroje; Codex používá sandbox pro čtení a vypnuté MCP.
Test je skutečný modelový dotaz a využívá přihlášení daného CLI.
Používá i právě vybraný thinking level.

Neúspěšně otestovanou dvojici nelze uložit jako výchozí a už uložená nefunkční
výchozí dvojice blokuje její dědění v běhu. Harness s nefunkčním nastaveným
modelem se nezobrazuje ani nedotazuje v topbaru. Úspěšný opakovaný test blokaci
odstraní. Změna modelu používá výsledek testu nové dvojice; neotestované modely
nejsou automaticky označené jako nefunkční. Vypnutí harnessu zakazuje jeho použití
v bězích i dotazy na jeho limity.

Claude usage HTTP 429 respektuje `Retry-After` a používá alespoň pětiminutovou
pauzu, která při opakování roste do hodiny. Úspěšný dotaz pauzu resetuje.
Současné požadavky různých přehledů sdílejí cache. Zastaralé hodnoty Claude mají
informaci o stáří v tooltipu.

Kontrola systému běží nezávisle na přehledu. V topbaru ji ukazuje modrý chip
se spinnerem, zelený **Systém v pořádku** nebo varovný **Nalezeny problémy**.
Zelený chip spustí čerstvou kontrolu, varovný otevře `#/problems` s nálezy,
návody a tlačítky k řešení. Přehled zůstává dostupný během kontroly i při nálezech.
