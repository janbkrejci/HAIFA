# Sloučení follow-upů v rámci běhu

Triáž porovnává každý follow-up také s ostatními follow-upy stejného běhu.
Rozhodnutí `covered` má právě jeden cíl: existující todo task (`task_id`),
nebo jiný follow-up vstupního seznamu (`target_follow_up_id`, například `f1`).
Follow-up, který pokrývá celé zadání, zůstává nositelem práce; podmnožiny
nevytvářejí samostatné tasky. Jejich původy se sjednotí a `blocks_task` se
přenáší logickým OR. Titulek, zadání, writes a workflow cíle se zachovají.

Řetězy odkazů se vyhodnocují až ke koncovému follow-upu, nezávisle na pořadí
rozhodnutí. Odkaz na sebe, cyklus nebo neexistující id odmítá validační brána
a triager dostane stejně jako u ostatních neplatných rozhodnutí jednu opravu.
Při zápisu se graf znovu kontroluje; pokud již neplatí, kryté reporty se zachovají
jako samostatné follow-upy a výsledek obsahuje varování.

Lidské follow-upy se slučují stejně jako agentní, ale pouze v rámci stejného
typu přiřazení. Kontrola zohledňuje i lidskou práci odvozenou z writes do
chráněných cest nebo backlogu. Ani prázdný todo backlog nevypíná triáž více
follow-upů. Porovnávání s tasky jiných běhů zůstává součástí triáže backlogu.

Regresní scénáře v `test_followups_triage.py` ověřují širší zadání a jeho
podmnožinu od buildera a documentera, tři lidské reporty stejné otázky,
přenos původů a blokování, obrácené pořadí, řetězy, opakovaný zápis a zachování
reportů při neplatném grafu. `test_triage.py` pokrývá validační pravidla,
jednu opravu neplatného grafu a triáž bez todo tasků. Spuštění kontrol
zajišťuje samostatný testovací krok workflow.
