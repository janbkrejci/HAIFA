"""Stock sssf as ``factory onboard`` knows it (``onboard/sssf_stock/``, copied from
``vendor/sssf/templates``), so a machine without ``vendor/`` can convert an sssf repo.

``stock.yaml`` holds the roster purpose and the prompt blob ids of every stock agent, the
blob ids of the stock chains with their library workflow, the other stock scripts and the
stock ``adw_modules/`` files. ``prompts/`` holds the stock prompt texts and
``quality.py.txt`` the stock ``adws/adw_modules/quality.py``.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import yaml

STOCK_DIR = Path(__file__).parent / "sssf_stock"
SSSF_ROSTER = "adws/adw_sssf_config/sssf.config.yaml"


@dataclass(frozen=True)
class StockAgent:
    """A stock sssf agent: its roster purpose and prompt texts with their blob ids."""

    purpose: str
    system: bytes
    user: bytes
    system_blob: str
    user_blob: str


@dataclass(frozen=True)
class Stock:
    agents: dict[str, StockAgent]
    chains: dict[str, str]
    chain_files: dict[str, str]
    scripts: dict[str, str]
    modules: dict[str, str]
    quality_source: str


def _strs(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


@functools.cache
def stock() -> Stock:
    """The packaged stock sssf data, read once per process."""
    raw = yaml.safe_load((STOCK_DIR / "stock.yaml").read_text(encoding="utf-8")) or {}
    agents: dict[str, StockAgent] = {}
    for name, meta in (raw.get("agents") or {}).items():
        folder = STOCK_DIR / "prompts" / str(name)
        agents[str(name)] = StockAgent(
            purpose=str(meta["purpose"]),
            system=(folder / "system.md").read_bytes(),
            user=(folder / "user.md").read_bytes(),
            system_blob=str(meta["system"]),
            user_blob=str(meta["user"]),
        )
    return Stock(
        agents=agents,
        chains=_strs(raw.get("chains")),
        chain_files=_strs(raw.get("chain_files")),
        scripts=_strs(raw.get("scripts")),
        modules=_strs(raw.get("modules")),
        quality_source=(STOCK_DIR / "quality.py.txt").read_text(encoding="utf-8"),
    )


__all__ = ["SSSF_ROSTER", "STOCK_DIR", "Stock", "StockAgent", "stock"]
