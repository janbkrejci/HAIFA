# Jednotná místní politika auto merge

Automatické dokončení PR používá výhradně `RepositorySettings` v HAIFA_HOME pro společný Git adresář repozitáře. Výchozí hodnota je false; backlogový frontmatter nemá přednost ani neposkytuje fallback při chybě. `auto_continue` a `base_pr_merge` jsou nezávislé volby. Ruční approve zůstává explicitní akcí.

Politika se čte při vstupu z queue, publish/retry a při dokončení stacked PR, znovu během čekání na hosting a CI, před opravou CI a před schválením hostingem. Konečná kontrola a odeslání merge běží pod zámkem aktualizací místního nastavení; stávající merge lock, review, CI, konflikty a write guards zůstávají zachovány.

Při off se dosud neodeslaný automatický merge neprovede. PR zůstane otevřené; případný commit `status: done` již odeslaný kvůli CI zůstane na větvi PR. Vypnutí nevrací hostingový požadavek již odeslaný: aktualizace nastavení počká na návrat právě probíhajícího volání hostingu. Aktivní čekání na CI zámek nastavení nedrží a nové off zjistí při dalším pollu. Neznámý stav nastavení je chyba, nikoli souhlas.

Regrese zahrnují obě nezávislé volby, přednost místního false před frontmatterem true, chybějící a poškozené nastavení, off během CI a před merge, ruční approve při off a stacked PR. Existující testy nadále ověřují zamítnuté review, červené CI a konflikty.
