# API System info

`GET /api/machine/system` vrací ve standardním envelope informace o unikátních
svazcích domova HAIFA, systémového tempu a registrovaných rep, dostupnou fyzickou
paměť a stav `ok` nebo `warning`. `free` a `total` jsou bajty; neznámé hodnoty
jsou `null`. Každý svazek uvádí všechny sledované `paths`, které na něm leží.
Prahy jsou 10 GiB / 10 % pro disk a 1 GiB / 10 % pro paměť.

Pro úklid pošlete `POST /api/machine/cleanup` s JSON `{}` a hlavičkou Origin shodnou
s adresou serveru (například `Origin: http://127.0.0.1:4700`), také při volání z CLI.
Chybějící nebo neplatný Origin vrací HTTP 403 `cross_origin` bez spuštění úklidu.
Odpověď obsahuje odstraněné `advice_directories`, výsledky úklidu jednotlivých
`repos` (`removed`, `deleted_branches`, `branch_reasons`, `warnings`) a `freed_bytes`.
Varování jsou také v horním envelope. Nedostupné repo nezastaví úklid ostatních.
Další souběžný úklid končí HTTP 409 `busy`.

Úklid používá stejné bezpečnostní podmínky jako `factory task clean` a existující
odstraňování osiřelých advice adresářů. Zachovává běžící běhy a otevřené PR;
nepřidává mazání archivů, logů, databází ani obecných dočasných souborů.

`freed_bytes` je součet rozdílů volného místa před a po úklidu, každý svazek jednou.
Jestliže některé měření chybí, je `null`. Jiné souběžné zápisy a mazání mohou výsledek
ovlivnit i způsobit záporný rozdíl; nejde o součet velikostí odstraněných souborů.
Sběr údajů nevyžaduje psutil. UI čipu se doplňuje samostatně.
