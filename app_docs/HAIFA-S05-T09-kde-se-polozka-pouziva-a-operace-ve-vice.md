# HAIFA-S05-T09 — Kde se položka používá a operace ve více repech

`factory library where TYP JMÉNO --json` čte registrovaná repa z
`$HAIFA_HOME/dashboard.yaml`. Vrací `data.repos[]` s identitou repa, slotem,
stavem a verzemi kopie, manifestu a knihovny. Zahrnuje přejmenované sloty,
lokální položky stejného jména a chybějící položky manifestu. Chybějící složku
vrací jako `repo_missing`; při vadném repu pokračuje s jeho chybovým kódem.

```sh
factory config add skill lint --agent builder --repos all --dry-run --commit --json
factory config add skill lint --agent builder --repos all --commit \
  --expect first=DIGEST --expect second=DIGEST --json
factory update --repos first,second --item agent/builder --dry-run --commit --json
factory update --repos first,second --item agent/builder --commit \
  --expect first=DIGEST --expect second=DIGEST --json
```

`--repos all` používá celý registr, seznam ID pouze zvolená repa. Operace
probíhají po jednom v pořadí registru, duplicitní ID se provedou jednou.
`--repo` a `--repos` nelze kombinovat. Bez registru je chyba `registry_missing`;
neznámé ID je `unknown_repo`, vadný registr `registry_invalid`.

Každý záznam `data.repos[]` má `repo`, `plan`, `result` a `status`. Plán
obsahuje vlastní digest, změněné cesty, validaci a blokátory. Výsledek obsahuje
commit, push a případné PR. `--dry-run --commit` připraví plán pro commit bez
zápisu; `--pr` zvolí PR a `-m` jeho commit message. Bez `--commit` se zapisuje
do pracovního stromu. Opakovaný `--item TYP/JMÉNO` omezuje aktualizované
položky; runtime gitignore, metadata manifestu a explicitní migrace zachovávají
obvyklé chování update.

Pokud použijete `--expect`, dodejte `ID=DIGEST` pro každé vybrané repo a použijte
`--commit` bez `--dry-run`. Neshodný digest přeskočí konkrétní repo s
`plan_changed`. Blokátory (`run_in_progress`, `dirty_paths`, …) a chyby
(`push_failed`, `repo_missing`, …) nezastaví zbývající repa. `data.partial`
upozorňuje na neprovedená repa; JSON obálka potvrzuje zpracování dávky, proto
vždy kontrolujte jednotlivé výsledky. Neexistuje transakce ani hromadný rollback.
Stejná operace se dá zopakovat; již hotová repa nevyrobí další commit.

Testy používají tři repa a lokální bare remotes, bez modelů a síťových služeb.

V režimu PR určuje větev digest plánu. Opakované `config add` nebo `update`
vrátí stejný commit, větev a otevřené PR, i při opakování částečně úspěšné
dávky. Změna zprávy commitu nevytvoří další PR pro stejný plán. Existující
větev se ověřuje podle základního commitu a celého výsledného stromu; pokud
byla upravena, repo se přeskočí s `plan_changed`. Větev dostupná pouze na
remote se načte a znovu použije. Pokud zápis větve uspěl, ale založení PR
selhalo, další pokus použije tuto větev a dokončí založení PR.
