# Retry po rozšíření writes

Retry načítá aktuální task z base a jeho Write scope sestavuje přes
`TaskWriteGuard.scope_prompt`, stejně jako nový běh. Samotné nové zadání ale
nestačí: obnovená konverzace harnessu může obsahovat původní systémové instrukce.

Před pokračováním workflow se proto nový scope každého agenta porovná s posledním
uloženým systémovým promptem v `<session>/<agent>/prompts/system.md`. Při změně
scope se odstraní pouze vazba daného agenta v `agent_map.json`; engine mu založí
novou konverzaci s aktuálním systémovým promptem. Stejný postup platí, pokud
uložený prompt nebo jeho sekce Write scope chybí. Při shodném scope se konverzace
obnoví jako dosud.

Kontrola se provádí ve společné cestě retry, takže platí pro CLI i dashboard
a nezávisí na textu poznámky `--allow-writes`. Zůstává stejné ID běhu, worktree,
branch, journal i kontextové předávky. Dokončené fáze se přehrávají podle
dosavadních pravidel retry.

Regresní testy ověřují nové ID konverzace a rozšířený systémový scope po
`--allow-writes` pro falešné harnessy Codex, Claude a Pi, také po porušení writes.
Dále ověřují zachování konverzace při shodném scope a její nahrazení při
chybějícím nebo starém auditu. Testy nevolají živé modely.
