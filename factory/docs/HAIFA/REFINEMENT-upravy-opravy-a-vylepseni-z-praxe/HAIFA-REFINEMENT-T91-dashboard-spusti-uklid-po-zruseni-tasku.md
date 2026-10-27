# Úklid worktree z dashboardu

Úspěšná změna stavu tasku na `cancelled` přes backlog API naplánuje úklid daného
repozitáře pomocí `aifactory.review.clean_worktrees`. Platí pro samostatné i
vícerepozitářové API. Odpověď nečeká na dokončení úklidu; výjimka úklidu se
zaloguje s cestou repozitáře a nevrací změnu stavu tasku zpět.

Vícerepozitářový dashboard se zapnutými `background_checks` uklízí všechna
registrovaná repa hned po startu a následně každou hodinu. Při každém průchodu
načte aktuální registr. Chyba jednoho repozitáře nezastaví ostatní.

Úklid běží ve vlákně. API i periodická úloha sdílejí v rámci aplikace evidenci
právě uklízených repozitářů: překrývající se úklid stejného repa se přeskočí.
Po chybě lze úklid zopakovat. Při ukončení aplikace se počká na úklidy spuštěné API.
Pravidla pro ochranu aktivních běhů, otevřených PR a mazání větví zůstávají
v `clean_worktrees`.

Regresní testy `tests/web/test_web_cleanup.py` ověřují odpověď API během
zablokovaného úklidu, vyloučení souběhu s periodickým průchodem, zachování
zrušení při výjimce, opakování po chybě, vynechání ostatních a odmítnutých editací
a opakované průchody všech registrovaných repozitářů bez HTTP požadavku.
