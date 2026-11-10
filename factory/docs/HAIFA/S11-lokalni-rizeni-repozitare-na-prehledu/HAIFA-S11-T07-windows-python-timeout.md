# HAIFA-S11-T07: timeouty testů a chybová okna Pythonu na Windows

## Příčina

Při timeoutu checku ukončoval `engine/quality.py::_run` příkaz přes
`oscompat.kill_group`, tedy `taskkill /PID <root> /T /F`. Taskkill prochází strom
podle rodičovských PID a ukončuje procesy postupně. Ověřeno na Windows izolovaným
reproduktorem (kontroler, který jako pytest-xdist okamžitě nahrazuje ukončené
workery):

- Worker spuštěný během taskkillu do stromu nepatří a přežije. V 3 z 5 běhů
  zůstaly 2 až 14 osiřelé python.exe. To odpovídá `[gw0] node down` v `command.log`:
  xdist uvidí ukončeného workera a spustí náhradu.
- Skrytá konzole stromu (`conhost.exe`) je potomek kořene a taskkill ji ukončí
  samostatně. Python spuštěný po jejím zániku skončí kódem `0xc0000142`
  (STATUS_DLL_INIT_FAILED). Bez potlačení chyb to Windows zobrazí jako modální okno
  „Aplikaci se nepodařilo správně spustit“ (System, Application Popup, ID 26). Totéž
  okno je v logu u běhu c612e428.
- Potomek, jehož rodič už skončil, taskkill nenajde vůbec.

Příčinu samotných historických timeoutů tento úkol neprokazuje. Naměřeno je jen,
že `tests/review/test_approve_continue.py` s
`test_task_retry.py::test_retry_after_stop_continues_at_the_stopped_phase` trvají se
dvěma workery 178 s (jednotlivé testy 8 až 28 s) a nevisí. Dávky v c612e428 byly jiné,
běžely se čtyřmi workery a jejich výpis před timeoutem nezachycuje stav vláken, takže
deadlock v nich nelze vyloučit ani potvrdit. Pomalost těchto testů je pravděpodobné, ne
ověřené vysvětlení. Doložené je jen to, že každý z timeoutů spustil popsané ukončení
stromu a okna vznikla v jeho čase.

## Oprava

`oscompat.ProcessTree` drží příkaz checku a všechny jeho potomky. Na Windows je to
job object: příkaz startuje s `CREATE_SUSPENDED`, vloží se do nového jobu a teprve
potom se spustí. Proto do jobu patří každý potomek od první instrukce.
Při timeoutu `TerminateJobObject` ukončí všechny členy najednou a
opakuje to, dokud job není prázdný (nejvýše `KILL_WAIT` = 10 s). Pokud job nelze
vytvořit nebo `QueryInformationJobObject` či `TerminateJobObject` selže, použije se
taskkill a `command.log` uvede selhání i možnost zbylých procesů mimo strom kořene.
Ani výjimka při úklidu nebrání ukončení kořene, takže timeout zůstává ohraničený. Job nemá `KILL_ON_JOB_CLOSE`, takže po běžném
dokončení příkazu pomocné procesy na pozadí doběhnou jako dřív. Na POSIX zůstává
ukončení skupiny procesů přes `killpg`.

`command.log` zachovává exit 124, výstup do timeoutu, důvod a nový řádek s počtem
ukončených procesů (`stopped N process(es) of the command's job object`). Systémový
dialog se nepotlačuje a registry ani uživatelský Python se nemění: dialog vznikal
při postupném ukončení stromu, které job object nahrazuje.

## Ověření

Reproduktor se stejným stromem (`uv run` → python kontroler → 8 respawnovaných
workerů): s taskkillem zůstaly osiřelé procesy ve 3 z 5 běhů, s job objectem
v 5 z 5 běhů nezůstal žádný (vždy bylo ukončeno 20 procesů). Za dobu reprodukce a
testů nepřibyla žádná událost Application Popup ID 26. Mechanismus `0xc0000142` byl
ověřen se zapnutým `SEM_FAILCRITICALERRORS`, aby se okno při pokusu neukázalo.

`aifactory/tests/engine/test_quality_process_tree.py` spouští skutečné procesy:
timeout se zachovaným výstupem a nedotčeným nesouvisejícím procesem, potomka
vznikajícího při ukončování, potomka rodiče ukončeného dříve, běžné dokončení
s pomocným procesem, ukončení již skončeného příkazu a na Windows náhradní taskkill
bez jobu, selhání `QueryInformationJobObject` a `TerminateJobObject`, výjimku při úklidu
a start pozastaveného příkazu.

## Pád faulthandleru (38777bbd)

`faulthandler_timeout` vypisuje zásobníky všech vláken z hlídacího vlákna bez GIL.
Když jiné vlákno právě v `CreateProcess` vytváří proces, může výpis skončit access
violation (podobné hlášení pytest-dev/pytest#7022). Repozitář tuto volbu nenastavuje,
přidal ji diagnostický příkaz. Při ověřování proto zůstává `-o faulthandler_timeout=0`
a pevný limit drží Factory. Fatální diagnostika faulthandleru při pádu zůstává zapnutá.
