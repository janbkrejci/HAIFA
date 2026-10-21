# HAIFA-REFINEMENT-T68: Prázdný první build

První build tasku s `success`, prázdnými `changed_files` a bez skutečné změny
mimo spec plánovače musí dodat `already_done` s evidencí. Jinak běh skončí
`failed` s `failure_kind: invalid_output` ještě ve fázi buildu, bez PR.
Operátor může po opravě instrukcí spustit retry; builder se zavolá znovu.

Továrna tuto instrukci přidává do promptu všech rolí vracejících `BuildOutput`,
nezávisle na repo skillu. Důkazem jsou ověřené commity nebo soubory repozitáře,
nikoli volně interpretovaný text summary.

Explicitní `already_done` ukončí task jako hotový bez změn i tehdy, když
plánovač již commitnul spec. Pozdější fix/revise bez dalších změn i resolve
nad existující implementací zůstávají povolené. Prázdné `changed_files` se
neodmítají, pokud skutečný diff obsahuje implementaci, včetně nových souborů.

U staršího PR, které obsahuje jen spec a nemá review, auto-merge zachová kód
`no_review`, ale vysvětlí chybějící `already_done` a doporučí retry buildu
s evidencí. PR se tím automaticky neschválí.

Regresní testy jsou v `tests/run/test_unchanged.py` a
`tests/run/test_auto_merge.py`; používají lokální Git a falešné harnessy.
