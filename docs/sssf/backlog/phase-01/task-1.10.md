Napiš zprávu z prototypu `docs/prototype-report.md` z výsledků v `prototype/validation/results/` a z trace DB. Zpráva je podklad pro bránu G1.

Where: `docs/prototype-report.md`. Zdroje: `prototype/validation/results/` (nejnovější běh s `--remote github`), `adws/adw_data/sssf.db`, `docs/product-brief.md`.

Done means:
- Pro každé riziko R1, R2, R3, R4, R5 a R10: výsledek (potvrzeno, vyvráceno, částečně), důkaz (odkaz na soubor výsledku, run-id, PR) a číslo, kde se měřilo (čas, disk, náklady, počet opravných kol).
- Pro každé rozhodnutí D1 až D13: platí beze změny, nebo navržená úprava s důvodem z výsledků.
- Seznam rozdílů mezi briefem a tím, jak prototyp nakonec funguje.
- Doporučení pro F2: co z prototypu převzít, co přepsat, co zahodit.
- Zpráva uvádí jen to, co je ve výsledcích nebo v trace. Chybějící výsledek je výslovně označený jako chybějící.

Out of scope: změny kódu prototypu, úpravy briefu.

Pevná omezení:
- `docs/product-brief.md` se neupravuje. Změny rozhodnutí jsou jen návrhy ve zprávě.
