# Opravy po rebase v rámci writes úlohy

Fáze `resolve` mění pouze soubory s textovým konfliktem. Následující opravy
`fix_N` a `test_fix_N` používají běžný rozsah úlohy: aktuální `writes` a její
pojmenované výstupy. Soubor nemusí mít textový konflikt. Nadále platí vlastní
omezení agenta a zákaz ručních změn generovaných výstupů.

Obě výchozí workflow `resolve` a `resolve-reviewed` dovolují opravu selhavších
kontrol také po čistém rebase. Dokončení běhu uloží i opravy mimo konfliktní
soubory. Staging vybírá konkrétní konfliktní cesty, změny v rozsahu úlohy
a příslušné regenerované výstupy. Zachovává také nekonfliktní generované
změny původní větve, včetně přidaných a smazaných assetů. Nové výstupy kontrol
ve stejné generované složce se tím nepovolují. Commit obsahuje jen vybrané cesty;
neignorované reporty a jiné změny mimo rozsah se do něj nedostanou ani tehdy,
když je kontrola sama přidala do indexu. Varianta s review kontroluje také
opravy po čistém rebase; neúspěšný běh nadále obnoví původní větev.

Prompt uvádí rozsah oprav odděleně od rozsahu řešení konfliktů. Pokud agent
přesto požádá přes `needs_writes` jen o již povolené cesty, chyba vysvětlí,
že nemá rozšiřovat `writes`, že oprava patří do `fix_N`, a uvede příkaz pro
opakování. Připomene také případné vlastní omezení buildera v `agents.yaml`.
Požadavky obsahující nepovolené cesty zůstávají `writes_needed`.

## Ověření

Regresní test retry používá skutečný Git a skriptované agenty bez živých služeb.
Base přidá test a rozšíří `writes` po původním pokusu; rebase má konflikt jen
v implementaci. Oprava následně změní nový test, kontroly projdou a stejný běh
pokračuje se zachovaným identifikátorem.

Test plán pro zachování nekonfliktního bundle zahrnuje:

- celý `tests/run/test_task_resolve_generated.py`, včetně nové regrese
  `test_nonconflicting_bundle_from_rebase_is_committed`;
- regrese `test_check_output_outside_writes_is_not_committed` a
  `test_repair_without_text_conflict_is_committed` v `test_task_resolve.py`;
- `test_retry_repairs_a_test_without_a_text_conflict` v `test_task_retry.py`;
- přímé volající: `test_conflict_is_resolved_reviewed_and_merged`,
  `test_member_resolves_a_conflict_and_merges` v `test_auto_merge.py`
  a `test_dependent_stacks_on_the_open_pr_and_lands_after_it`
  v `test_stacked_prs.py`;
- cílený Ruff, formátování a mypy dvou upravených Python souborů.

Všech 23 vybraných případů prošlo; cílený Ruff, formátování i mypy prošly.

Pro samostatný mypy testovacích souborů je z adresáře `aifactory` potřeba
`MYPYPATH=tests:tests/workflow`, aby našel sdílené testovací helpery při
kontrole samostatného souboru `test_task_resolve.py`.

Regrese stagingu pokrývá čistý i konfliktní rebase, s opravou i bez ní,
a výstupy kontrol mimo `writes` s přidáním do indexu i bez něj. Kontrola
vytváří nový `report.xml` a mění existující `README.md`; ani jedna změna
se nesmí dostat do commitu. Po čistém rebase bez opravy nevzniká další commit.
Stávající test generovaného bundle ověřuje i odstranění assetu, který byl
při rebase nově přidaný do indexu a rebuild jej smazal.

Nová regrese nechá base změnit pouze MODEL a původní větev změnit MODEL,
INDEX i asset. Konflikt je jen v MODEL. Test ověřuje INDEX a asset přímo
ve výsledném commitu, odstranění starého assetu a čistý worktree. Druhá
varianta vytvoří a přidá do indexu report i další asset kontrolou; ověřuje,
že ani jeden z těchto dodatečných výstupů nevstoupí do commitu.
