# Místní výchozí harness repozitáře

Nové běhy vyhodnocují volbu v pořadí: explicitní jednorázový přepis, místní volba repozitáře, uložený default počítače, roster. Není-li default určen ani na počítači, rozhoduje roster. Repo volba je uložena v HAIFA_HOME pod identitou společného Git adresáře; platí také ve worktree, nepotřebuje commit a neovlivňuje jiné klony.

Model a thinking se berou z místních nastavení vybraného harnessu. Explicitní model nebo thinking mohou tuto hodnotu přepsat. Přepnutí harnessu zahodí model i thinking zděděné z jiného harnessu. Chybějící místní model u nakonfigurovaného harnessu, neplatný repo záznam, zakázaná volba nebo neúspěšný test modelu vrací chybu. Nedostupnost adaptéru či modelu odhaluje stávající validace před spuštěním agenta. Bez uložených počítačových nastavení zůstávají dostupné dosavadní výchozí modely rosteru a přepisu.

Backlog hodnoty harness/model/thinking zůstávají čitelné pro legacy import. Nové task run, resolve a další nové běhy, proposer, poradci, triager, learner a nové konverzace průvodce z nich nevybírají runtime harness. Explicitní workflow step override platí nad výsledným rosterem a jeho efektivní harness/model/thinking zůstávají v záznamu fáze. Pokud krok přepíná pouze harness, převezme místní model a thinking cílového harnessu. Model a thinking výslovně uvedené v kroku mají před těmito výchozími hodnotami přednost; krok se stejným harnessem zachovává nezadané hodnoty session. Průvodce odmítne místní repo volbu, pokud na ní neumí vynutit své omezení příkazů.

Běh s přepisem zaznamenává efektivní volbu ve značce „přepis rosteru“ a původ ve značce „zdroj harnessu“ (explicit, repository, machine nebo quota). Primární harness je zaznamenán zvlášť, aby změna místní volby během session nepřestavěla její kvótový řetěz.

Session ukládá efektivní roster do roster.json. Retry obnoví tento roster a zachová identitu běhu, worktree i agentích session; aktuální repo nebo počítačová volba jej nepřepíše. Starší session bez snapshotu obnoví roster z původního base_sha a přepis ze záznamu běhu. Explicitní změna přes existující retry override a kvótový fallback nadále zaznamenávají přepnutí.

Kvótový fallback neupravuje uloženou repo volbu. Nový běh sestaví primární harness z aktuálních místních nastavení a případný switch-back postupuje k němu. Neplatná či zakázaná uložená pozice kvótového řetězu vrátí chybu bez tichého spuštění na primárním harnessu.

Regresní testy používají falešné harnessy. Pokrývají precedence, legacy metadata, nové ruční i automatické běhy bez commitu, izolaci repozitářů, explicitní workflow override, retry se snapshotem i bez něj, kvótové přepínání a chyby místní volby.
