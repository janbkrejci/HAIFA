# Místní auto merge

Nastavení se mění příkazem `factory config local set --auto-merge on|off` a nevyžaduje commit. `factory config local show` vrací účinnou hodnotu a `auto_merge_policy` s hodnotou, zdrojem (`repository` nebo výchozí `default`) a cestou záznamu v HAIFA_HOME. Přehled a detail backlogového tasku poskytují stejnou politiku. Worker čte stejnou službu bez cache, i pro Git worktree. Staré backlogové příkazy nadále editují frontmatter, ale automatický merge neřídí.

`auto_continue` řídí přijímání dalších běhů; off nebrání dokončení současného PR, je-li auto merge on. Změna auto merge tento přepínač nepřepisuje. `base_pr_merge` řídí vlastní cestu změn base, nikoli PR tasku. Ruční approve je samostatný explicitní souhlas a prochází původními kontrolami CI a konfliktů.

Off zastaví neodeslané automatické merge v queue, publish/retry a při dokončování stacku. Kontrola se opakuje během čekání na CI a těsně před merge pod zámkem místního nastavení. PR zůstane otevřené; již odeslaný commit `status: done` kvůli CI zůstane na větvi PR. Zastavený pokus uvádí `auto_merge_disabled`; PR pak čeká na ruční approve nebo nový explicitní pokus po zapnutí. Samotné zapnutí nevytváří práci. Před zahájením pokusu off přepne webové odvození PR do čekání na review; dřívější chyba auto merge nadále vyžaduje explicitní opakování.

Požadavek merge již odeslaný hostingu nelze odvolat. Zámek nastavení se drží po dobu konečné kontroly a volání hostingu, takže off dokončené před touto hranicí další odeslání zastaví; off souběžné s již probíhajícím voláním čeká na jeho návrat. Dlouhé čekání na CI tento zámek nedrží. Chybějící místní soubor znamená off, poškozený či nepřístupný soubor je viditelná chyba a nikdy nepoužije backlog ani starou hodnotu.

Background refresh pouze zaznamenává skutečný stav hostingu a může pokračovat po externím merge podle auto continue. Auto merge off nebrání zaznamenání již provedeného merge a samo nemění pravidla pokračování. Webové zařazení otevřených PR používá čerstvou místní hodnotu i při cachovaném backlogu.

Implementace doplňuje regresní testy služby, CI brány, queue, stacku a webových odvození. Spuštění kontrol přísluší samostatnému testovacímu kroku workflow.
