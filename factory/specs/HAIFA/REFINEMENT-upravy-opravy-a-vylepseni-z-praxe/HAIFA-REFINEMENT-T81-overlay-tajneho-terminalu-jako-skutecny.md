# HAIFA-REFINEMENT-T81 — Interaktivní tajný terminál

Overlay používá xterm.js nad existujícím PTY API. Stav `/api/terminal` určuje dostupnost: vypnutý terminál vysvětluje omezení na loopback, chybějící PTY zobrazí zprávu o nedostupnosti interaktivního terminálu.

FitAddon určí rozměry při vytvoření sezení; ResizeObserver je průběžně synchronizuje. Výstupní stream předává původní Uint8Array do emulátoru, vstup xterm onData posílá do PTY. Vstup a resize se odesílají postupně, aby se zachovalo pořadí.

Klávesy aplikací včetně Esc zpracovává terminál. Tajná sekvence se detekuje ve window capture posluchači, takže funguje i při zastavení propagace v textarea. Overlay zavírá sekvence nebo křížek. Unmount a pagehide zruší stream, odstraní sezení a uvolní emulátor. Pozdě dokončené vytvoření sezení po zavření je také odstraněno.

Konec streamu nabídne nové sezení tlačítkem nebo Enterem. Nové sezení začíná ve výchozím adresáři API. Funkce nemá veřejný navigační vstup.
