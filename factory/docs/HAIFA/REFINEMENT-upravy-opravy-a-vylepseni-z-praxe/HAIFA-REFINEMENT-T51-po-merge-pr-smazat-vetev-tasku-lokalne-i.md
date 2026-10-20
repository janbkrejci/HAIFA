# Automatické mazání větví po merge

`factory task approve ID` i auto-merge po úspěšném sloučení a restacku závislých PR
odstraní lokální a remote větev tasku. Lokální mazání používá `-D`, takže funguje
i po squash merge. Remote je nastavením `remote`, standardně `origin`.

Otevřený stacked PR bez úspěšného restacku, běžící běh nebo checkout ve kterémkoliv
worktree mazání větve odloží. Hlavní base větev se nemaže. Větve zavřených PR
a opuštěných běhů se zachovávají.

Pro historické merge nebo opakování neúspěšného mazání spusťte:

```sh
factory task clean --json
```

Příkaz kromě dosavadního úklidu worktree smaže i dosud existující větve evidovaných
sloučených PR, včetně těch, jejichž worktree už neexistuje. Uplatní stejné ochrany.
Úspěšný restack uvolní větev rodiče pro smazání, i když PR potomka zůstává otevřený.
Chybějící remote větev, například odstraněná Azure při merge, není chyba.

Approve i clean vracejí `data.deleted_branches`, například:

```json
["factory/T01-1", "origin/factory/T01-1"]
```

Položka představuje skutečně smazanou lokální nebo remote větev. Při částečném
úspěchu obsahuje jen úspěšná mazání. Chyby sítě či odmítnutí push se objeví ve
`warnings`, úspěšný merge nezmění na neúspěch a lze je řešit opakováním clean.
Textový výstup také uvádí smazané větve. Nové chování popisuje `factory --skill`.
