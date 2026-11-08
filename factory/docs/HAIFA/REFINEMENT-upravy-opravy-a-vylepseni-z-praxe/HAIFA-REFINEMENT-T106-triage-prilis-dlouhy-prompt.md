# Omezení kontextu triage follow-upů

Kontext triage má rozpočet `CONTEXT_LIMIT = 120_000` znaků JSON včetně odsazení,
escapování, hlášení follow-upů a výstupního schématu. Jde o rozpočet vstupu
sestaveného v `triage.py`; systémový prompt a režie harnessu jsou navíc.

Projekt se určuje ze zdrojového `task_id`, protože hlášení follow-upu projekt
neobsahuje. Kandidáti se řadí stabilně: todo tasky stejného projektu, jejich
tranzitivní závislosti (včetně závislostí na kontejnerech), ostatní todo tasky.
Bez zdrojového tasku zůstává původní pořadí backlogu.

Těla mají nadále nejvýše 6 000 znaků. Při překročení celkového rozpočtu se od
konce prioritního seznamu zkracují těla a následně kandidáti redukují na id a
titulek. Pokud ani tento seznam nestačí, kandidáti se od konce vynechávají.
`backlog_truncated` označuje zkrácení těla, metadat nebo seznamu. Původní backlog
ani hlášení se nemění. Pokud rozpočet překročí samotná hlášení a schéma,
triage selže před odesláním modelu; hlášení se nezkracují.

Při chybě se do log události zapisuje důvod a dostupná poslední neplatná odpověď
modelu uložená enginem (nejvýše posledních 2 000 znaků). Chyba fáze obsahuje
začátek této odpovědi i důvod, takže například „Prompt is too long“ je vidět
v trace i v detailu fáze dashboardu. Neúspěšný validní výstup rovněž označí fázi
jako neúspěšnou. Formát `TriageOutput` a rozhodovací pravidla zůstávají stejné.

Regresní testy v `tests/run/test_triage.py` pokrývají 600 kandidátů s těly po
6 000 znacích, prioritu projektu a závislostí, escapování JSON, vynechání
kandidátů, nadlimitní hlášení a zobrazení odpovědi modelu v chybě fáze.
