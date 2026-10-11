---
id: HAIFA-S03-T22
title: sdílená remote databáze
status: done
depends_on: []
---

## Zadání
v konfiguraci celé factory by bylo dobré mít možnost místo lokální SQLite napojit factory/dashboard na externí databázi, mapř. MSSQL express v docker kontejneru nebo na vzdáleném stroji, a díky tomu v reálném čase sdílet info o běhách a backlogu mezi členy týmu na různých počítačích. pro tohle bude nutné mít projekty identifikované tak, aby se to různým lidem správně spojilo, vazba přes remote repo mi přijde nejlogičtější a bez konfigurace. databázi zatím uděláme public read/write.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/86 · náklady $0.00
