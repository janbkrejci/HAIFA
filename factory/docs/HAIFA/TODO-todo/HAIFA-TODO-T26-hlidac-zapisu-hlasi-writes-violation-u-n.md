# HAIFA-TODO-T26 — povolené zápisy pod chráněnou cestou

Hlídač taskového běhu nyní dává výslovným `writes` tasku přednost před
`protected_files` u agenta s `writes: null`. Pravidlo používá porovnání cest,
nikoli existenci adresáře, takže lze vytvořit například
`.factory/prompts/reviewer/system.md` a `user.md`, i když reviewer dosud pochází
jen z knihovny.

Příčinou selhání bylo následné posouzení cesty jako chráněné pro neomezeného
agenta. Označení `deleted` popisovalo odstranění vytvořeného souboru při
rollbacku. Povolené soubory nyní rollbacku nepodléhají.

Vlastní omezení agenta zůstávají účinná: `writes: []` zakazuje zápisy a neprázdný
seznam musí cestu povolovat. Taskové výstupy samy chráněné cesty neodemykají.
Ochrana `.factory/` mimo taskové `writes` a pravidla pro hlavní checkout zůstávají
zachována. Automatické rozšiřování `writes` ani lekce `L328f600c` se nemění.

Hlídač rozlišuje deklarované `writes` (v tasku nebo zděděné z kroku či projektu)
od implicitního `**`, které se použije, když žádná úroveň `writes` nenastavuje.
Implicitní default chráněné cesty neodemyká; běžné nechráněné zápisy nadále povoluje.

Regresní test `tests/run/test_guard_protected_writes.py` používá skutečný Git a
engine s falešným Codex harness bez volání modelu. Ověřuje vznik obou promptů
v novém adresáři, jejich zachování při odmítnutí sousední cesty a respektování
vlastních oprávnění agenta. Dále ověřuje odmítnutí chráněných promptů při
implicitních `writes` a povolení při deklarovaném `**` na každé úrovni backlogu.
Související ověření pokrývá výstupy tasků a odmítnutí
automatického povolení chráněných cest.
