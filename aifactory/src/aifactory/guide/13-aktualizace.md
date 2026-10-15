# Aktualizace a vydání

## Aktualizace z dashboardu

Dashboard se jednou za půl hodiny podívá na poslední stabilní vydání HAIFA. Chip v horní liště ukazuje stav: **Systém je aktuální**, **Je k dispozici aktualizace** (tooltip uvede novou verzi), **Aktualizace čeká na tasky**, **Instaluji aktualizaci…**, nebo **Nepodařilo se zkontrolovat aktualizace**. Kliknutí na chip v jiném stavu než dostupná aktualizace zopakuje kontrolu.

Kliknutím na **Je k dispozici aktualizace** dashboard balíček stáhne, ověří součty, nainstaluje, restartuje se a spustí kontrolu systému. Dokud běží nějaký task, aktualizaci neinstaluje: chip ukáže **Aktualizace čeká na tasky** a tooltip, kolik tasků běží. Každý běh je samostatný proces `factory` ze stejné instalace, kterou aktualizace nahrazuje; na Windows by instalace na zamčených souborech selhala a nechala HAIFA rozbitou, jinde by běžící task načítal moduly nové verze do staré. Až tasky doběhnou, klikni na chip znovu.

Zdroj vydání je GitHub repo `janbkrejci/HAIFA`; firemní instalace může nastavit jiné repo proměnnou `HAIFA_UPDATE_REPO` (ve tvaru `vlastník/repo`) v prostředí nebo v `$HAIFA_HOME/env`.

## Aktualizace z příkazové řádky

```bash
factory upgrade --dry-run haifa-<verze>.zip
factory upgrade haifa-<verze>.zip
```

`factory upgrade` přijme cestu k souboru i `https` URL. Balíček rozbalí do dočasného adresáře, ověří `SHA256SUMS`, porovná verzi s nainstalovanou (starší nebo stejnou neinstaluje) a spustí `uv tool install --force` s připnutými závislostmi. Po instalaci nový `factory` obnoví knihovnu (viz [Knihovna po aktualizaci](#/guide/aktualizace/knihovna-po-aktualizaci)). `--dry-run` jen ukáže verze a příkaz. Běžící dashboard (`factory obs`) pak restartuj.

Instalaci ze zdrojů (editable, vývoj HAIFA) `factory upgrade` odmítne; tu aktualizuješ přes `git pull`.

## Aktualizace na Windows

Windows nedovolí běžícímu programu přepsat vlastní soubory. Dashboard i `factory upgrade` proto balíček jen stáhnou a ověří a instalaci předají skriptu na pozadí. Skript počká, až se proces ukončí, nainstaluje novou verzi a dashboard spustí znovu v novém okně konzole. Prohlížeč se po restartu sám načte. `factory upgrade` odmítne pokračovat, dokud dashboard běží (`dashboard_running`): zavři ho, nebo aktualizuj chipem v dashboardu. Průběh instalace se zapisuje do `%TEMP%\haifa-upgrade.log`.

## Knihovna po aktualizaci

Nová verze může přinést nové verze agentů, workflow a skillu `factory` v semínku. Instalace (`install.sh`, `install.bat`) i aktualizace (`factory upgrade`, chip v dashboardu, na Windows i skript na pozadí) proto knihovnu hned obnoví novým `factory`: chybějící knihovnu naklonují (`factory library clone --seed-fallback`) a pak spustí `factory library seed --all`. Ten každou položku semínka v knihovně nahradí verzí z instalované HAIFA, včetně skillu `factory`, i když ji tým v knihovně upravil. Položky, které semínko nemá (týmové importy), zůstanou a repa se nemění; vlastní úpravy patří do `.factory/` repa. Selhané obnovení je jen varování (`library_refreshed` je `false`); zopakuješ ho přes `factory library seed --all`.

Bez `--all` pracuje `factory library seed` jako dřív a `factory check` hlásí nepřevzaté verze jako `seed_update_available`:

```bash
factory library seed --dry-run
factory library seed
```

`factory library seed` převezme nové verze do knihovny: položky, které tým neupravil, nahradí; upravené ponechá (`kept`) a ukáže rozdíl. Semínkovou verzi upravené položky si vezmeš přes `factory library seed --take agent/<jméno>`. Má-li knihovna remote, každý zápis do ní (i seed) nový commit rovnou odešle, takže ho ostatní dostanou přes `factory library pull`. Repa nové verze položek zdědí při dalším běhu; vlastní kopie v `.factory/` repa zůstávají beze změny.

## Agentní skill

Pokud HAIFA ovládá i agent (Claude Code, Codex, pi), dej mu po každé aktualizaci nový návod:

```bash
factory --skill > SKILL.md
```

## Vydání nové verze (správce HAIFA)

Oficiální vydání vzniká automaticky: GitHub Actions na každém commitu do `main` spustí testy, typovou kontrolu a lint, ověří instalaci na Windows a vydá release `haifa-<major>.<minor>.<číslo běhu>.zip`. Commity, které mění jen backlog (`factory/backlog/`) nebo `.factory/`, CI ani vydání nespouštějí.

Ruční vydání pro tým, který nepoužívá GitHub releases:

1. Zvyš verzi v `aifactory/src/aifactory/__init__.py` (`__version__`).
2. `just check` musí projít (a `just e2e` při změně dashboardu).
3. `just bundle` vytvoří `aifactory/dist/haifa-<verze>.zip`. Balíček obsahuje i `INSTALL.md`, který je kapitolou Instalace této příručky.
4. Rozešli zip týmu; každý ho nainstaluje přes `factory upgrade`.
5. Když nová verze knihovny vyžaduje novější HAIFA, nastav v knihovně `min_factory_version` v `library.yaml`, commitni a odešli (`factory library push`). Kolegové se starší verzí pak uvidí v `factory check` chybu `factory_outdated`.
