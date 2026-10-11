# HAIFA-S01-T38 — Návrh parametrů tasku

Ve formuláři nového i existujícího tasku může uživatel opakovaně požádat agenta o lepší
formulaci zadání a návrh titulku, writes, závislostí, souvisejících tasků, workflow a
zděditelných parametrů: source, target, test, test_timeout, specs_dir, docs_dir,
auto_continue a auto_merge. Identitu, umístění, status a historii běhů agent nemění.

Volba providera/modelu vychází z nakonfigurovaného rosteru (claude, codex, pi).
Poslední použitá volba se ukládá v prohlížeči pro dané repo; při změně rosteru se
použije první dostupná volba. Agent běží stejným izolovaným mechanismem jako návrh
workflow, s prázdnými writes, hlídačem zápisů a omezenou frontou.

Výsledek je náhled s vysvětlením. Teprve „Použít návrh do formuláře“ přenese hodnoty;
uložení proběhne obvyklým tlačítkem. Změna rozepsaného tasku zneplatní možnost použít
starší návrh. API kontroluje schema, workflow, existenci vazeb, cykly a relativní
writes. Uložení všech změn proběhne atomicky přes kontrolu backlogu a zachová Běhy.

Každý návrh zobrazí vykázané tokeny a cenu v USD. Pokud provider cenu nevrací
(například Codex), výsledek výslovně uvádí nedostupnou cenu místo falešné nuly.
Při chybě lze návrh opakovat; pokud existuje trace, API zpřístupní vykázanou spotřebu.

Ověření: cílené pytest testy API, izolovaného agenta a editace backlogu; Vitest
formuláře a návrhu; strict mypy, Ruff, vue-tsc a Vite build. Žádné živé modely ani síť.
