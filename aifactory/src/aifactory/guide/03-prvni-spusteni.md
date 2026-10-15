# První spuštění

Postup od nainstalovaného nástroje k prvnímu hotovému tasku. Předpokládá, že máš HAIFA nainstalovanou podle kapitoly [Instalace](#/guide/instalace).

## Spusť dashboard

```bash
factory obs
```

Prohlížeč otevře `http://127.0.0.1:4700`. Terminál nech otevřený, `Ctrl+C` server zastaví. Běhy spuštěné z dashboardu jsou samostatné procesy a zastavení serveru přežijí.

## Projdi „Začínáme“

Dokud něco chybí, ukazuje horní lišta chip **Nalezeny problémy**. Otevře stránku **Problémy a řešení** se zbývajícími kroky prvního spuštění. Každý krok má tlačítko, které tě dovede k nápravě:

| Krok | Tlačítko | Co udělat |
| --- | --- | --- |
| Počítač | Zkontrolovat počítač | Vyřeš chyby kontroly: git, identita, uv, CLI hostingu. |
| Knihovna | Připravit knihovnu | Naklonuj týmovou knihovnu (výchozí HAIFA-LIBRARY je předvyplněná), nebo ji založ ze semínka. Instalátor ji obvykle naklonoval už sám. |
| Harnessy | Zkontrolovat harnessy | Povol harness, vyber model a thinking a spusť **Test**. |
| Repozitář | Přidat repozitář | Přidej lokální Git repo. |
| Factory v repu | Nainstalovat factory / Commitnout konfiguraci | Nainstaluj `.factory/` a commitni ji do base. |
| Harnessy a modely repa | Zkontrolovat agenty | Ověř, že agenti repa používají harnessy, které máš. |
| První projekt | Založit projekt | Založ první projekt backlogu. |

## Nastav harnessy

Klikni v horní liště na **Harnessy** (lišta limitů). V dialogu **Harnessy tohoto počítače** pro každý harness (claude, codex, pi):

1. Zapni ho přepínačem.
2. Vyber **Výchozí model** a **Výchozí thinking level**.
3. Klikni na **Test**. Výsledek „Vše OK — harness odpověděl OK.“ znamená, že harness je přihlášený a model funguje.
4. Jeden harness označ jako **Výchozí harness** a dej **Uložit nastavení**.

Harness, jehož test selhal, nejde použít jako výchozí. Podrobnosti v kapitole [Počítač a harnessy](#/guide/pocitac).

## Přidej repozitář

Na **Přehledu** klikni na **Přidat repozitář** (pod seznamem rep):

1. Zadej cestu ke složce repa, nebo ji najdi přes **Procházet…**, a klikni na **Zkontrolovat**.
2. Karta repa ukáže kořen, větev, remote a stav factory (Bez factory, Nainstalováno, necommitnutá konfigurace, Nepodporováno).
3. **Přidat** zapíše `.factory/config.yaml` (existující ponechá), doplní `.gitignore` a commitne to do base.
4. Když base přijímá změny jen přes pull request (chráněná větev), zaškrtni před přidáním **Změny base přes pull request**. Repo si to zapamatuje (`base_changes: pr`) a pull requestem pak jde každá změna base, počínaje instalací z větve `factory-init/<n>`. Volba **Pull requesty factory hned schválit a mergnout** (`base_pr_merge: auto`) je factory mergne sama. Bez ní je mergne člověk a ty pak v záložce Factory použiješ **Stáhnout konfiguraci z base**. Podrobnosti jsou v kapitole [Konfigurace repa](#/guide/konfigurace-repa).

Totéž z příkazové řádky: `factory obs --repo ~/cesta/k/repu` zaregistruje repo a otevře ho. Repo bez HAIFA nainstaluješ i přes `factory init` (kapitola [Práce v týmu](#/guide/tym)).

## Zkontroluj repo

V repu otevři záložku **Factory**. Verdikt „Factory je v pořádku“ znamená, že můžeš pracovat. Jinak záložka ukáže nálezy rozdělené na **Repozitář: opravit a commitnout** a **Počítač: potřebné pro toto repo** a tlačítka **Nainstalovat factory** nebo **Stáhnout konfiguraci z base**. Necommitnutou konfiguraci commitneš červeným čipem **Necommitnutá konfigurace** v horní liště. Ostatní nálezy počítače a knihovny jsou jen na stránce **Knihovna**; Factory na ně odkáže jedním řádkem.

## Založ projekt, step a task

Na záložce **Backlog**:

1. **Nový projekt:** kód (například `WEB`), název a popis, **Založit**.
2. **Nový step** v projektu: kód (například `S01`), název, **Založit**.
3. **Nový task** ve stepu: titulek, zadání (co má agent udělat), **Workflow** (například `plan-build-test`) a případně **Writes**, tedy cesty, které smí agent měnit.
4. **Commitnout backlog:** červený čip **Necommitnutý backlog** v horní liště ukáže necommitnuté soubory backlogu. Běhy čtou backlog z base, takže ho commitni.

Workflow nemusíš nastavovat u každého tasku: nastav ho jednou v projektu nebo stepu a tasky ho zdědí. Pomoc s výběrem nabídne tlačítko **Navrhnout workflow** ve formuláři tasku.

## Spusť běh

V detailu tasku klikni na **Spustit**. Dialog **Spustit task** shrne workflow, povolené cesty a commit base a upozorní na problémy (necommitnutý backlog nebo konfigurace, nesplněné závislosti). Potvrď **Spustit** a otevři běh odkazem **Otevřít běh**.

Na záložce **Běhy** sleduješ fáze běhu živě. Po úspěchu HAIFA otevře pull request a task se na Backlogu přesune do **V review**.

## Schval výsledek

Na záložce **Review** otevři pull request, projdi popis, výsledky testů, verdikt revieweru a diff, a klikni na **Schválit** (merge do base), nebo **Vrátit s poznámkou** (agenti task přepracují). Po schválení je task **Hotovo**.

Co dál: [Backlog a tasky](#/guide/backlog), [Běhy](#/guide/behy), [Review a merge](#/guide/review).
