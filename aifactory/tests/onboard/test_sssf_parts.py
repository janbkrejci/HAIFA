"""Parts of the sssf conversion: the stock data, the prompt merge, quality.py and TS imports."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from onboard_repo import (
    AMBER_BUILDER_RULE,
    JSST_BUILDER_RULES,
    JSST_REVIEWER_RULE,
    PLANNER_CHANGED_LINE,
    SSSF_TEMPLATES,
)

from aifactory.library.seed import SEED_DIR
from aifactory.onboard import merge_prompt, parse_quality
from aifactory.onboard.merge import quote_change
from aifactory.onboard.quality import same_as_stock
from aifactory.onboard.sssf import _ts_closure
from aifactory.onboard.stock import STOCK_DIR, stock

AGENTS = ("planner", "builder", "scout", "reviewer", "documenter")


def _hash(path: Path) -> str:
    return subprocess.run(
        ["git", "hash-object", str(path)], capture_output=True, text=True, check=True
    ).stdout.strip()


def _seed(agent: str, name: str) -> bytes:
    return (SEED_DIR / "agents" / agent / name).read_bytes()


def _stock_prompt(agent: str, name: str) -> bytes:
    return (SSSF_TEMPLATES / "prompt_engineering" / agent / name).read_bytes()


def _insert_after(text: bytes, line_start: str, added: str) -> bytes:
    lines = text.decode("utf-8").splitlines(keepends=True)
    index = next(i for i, line in enumerate(lines) if line.startswith(line_start))
    lines.insert(index + 1, added)
    return "".join(lines).encode("utf-8")


# ── the stock data equals vendor/sssf/templates ───────────────────────────────


def test_stock_equals_vendor() -> None:
    known = stock()
    roster = yaml.safe_load((SSSF_TEMPLATES / "sssf.config.yaml").read_text(encoding="utf-8"))
    purposes = {a["name"]: a["purpose"] for a in roster["agents"]}
    assert sorted(known.agents) == sorted(AGENTS)
    for name, agent in known.agents.items():
        assert agent.purpose == purposes[name]
        for kind, data, blob in (
            ("system.md", agent.system, agent.system_blob),
            ("user.md", agent.user, agent.user_blob),
        ):
            vendor = SSSF_TEMPLATES / "prompt_engineering" / name / kind
            assert data == vendor.read_bytes(), (name, kind)
            assert blob == _hash(vendor), (name, kind)
    quality = SSSF_TEMPLATES / "adws" / "adw_modules" / "quality.py"
    assert (STOCK_DIR / "quality.py.txt").read_bytes() == quality.read_bytes()
    assert known.quality_source == quality.read_text(encoding="utf-8")
    vendor_chains = {_hash(SSSF_TEMPLATES / "adws" / f): w for f, w in known.chain_files.items()}
    assert {b: w for b, w in known.chains.items() if b in vendor_chains} == vendor_chains
    assert known.chains["a6a5c4c1c4be7fb2bf3de4c80cdb798c8df23ffc"] == "simple-sdlc"
    assert known.chains["3f5d48378a8daefb7e9dfa79af8279454db42d34"] == "simple-sdlc"
    assert len(known.chains) == len(vendor_chains) + 1
    scripts = sorted(p.name for p in (SSSF_TEMPLATES / "adws").glob("adw_*.py"))
    assert sorted([*known.scripts, *known.chain_files]) == scripts
    for name, blob in known.scripts.items():
        assert blob == _hash(SSSF_TEMPLATES / "adws" / name), name
    modules = SSSF_TEMPLATES / "adws" / "adw_modules"
    assert sorted(known.modules) == sorted(p.name for p in modules.glob("*.py"))
    for name, blob in known.modules.items():
        assert blob == _hash(modules / name), name


# ── merge_prompt ──────────────────────────────────────────────────────────────


def test_merge_stock_and_same() -> None:
    base, theirs = _stock_prompt("builder", "system.md"), _seed("builder", "system.md")
    assert merge_prompt(base, base, theirs).kind == "stock"
    assert merge_prompt(base, base, theirs).text == theirs
    same = merge_prompt(base, theirs, theirs)
    assert (same.kind, same.text) == ("same", theirs)


def test_merge_union_jsst_builder() -> None:
    base, theirs = _stock_prompt("builder", "system.md"), _seed("builder", "system.md")
    ours = base + JSST_BUILDER_RULES.encode("utf-8")
    result = merge_prompt(base, ours, theirs)
    assert result.kind == "union"
    assert JSST_BUILDER_RULES.encode("utf-8") in result.text
    assert theirs.splitlines()[-1] in result.text.splitlines()
    assert b"<<<<<<<" not in result.text


def test_merge_clean_jsst_reviewer_and_amber() -> None:
    base, theirs = _stock_prompt("reviewer", "system.md"), _seed("reviewer", "system.md")
    ours = _insert_after(base, "- `approved` is true ONLY", JSST_REVIEWER_RULE)
    result = merge_prompt(base, ours, theirs)
    assert result.kind == "clean"
    assert JSST_REVIEWER_RULE.encode("utf-8") in result.text
    base, theirs = _stock_prompt("builder", "system.md"), _seed("builder", "system.md")
    ours = _insert_after(base, "## Instructions", AMBER_BUILDER_RULE)
    result = merge_prompt(base, ours, theirs)
    assert result.kind == "clean"
    assert AMBER_BUILDER_RULE.encode("utf-8") in result.text
    assert theirs.splitlines()[-1] in result.text.splitlines()


def test_merge_conflict_planner() -> None:
    base, theirs = _stock_prompt("planner", "system.md"), _seed("planner", "system.md")
    old = (
        "- List `specs/` before naming that copy and pick a name nothing else holds. Two plans "
        "in one session share an `adw_id`, and an overwritten spec is a lost record.\n"
    )
    ours = base.replace(old.encode("utf-8"), PLANNER_CHANGED_LINE.encode("utf-8"))
    assert ours != base
    result = merge_prompt(base, ours, theirs)
    assert result.kind == "conflict"
    assert result.text == theirs
    assert result.quote is not None
    assert "+" + PLANNER_CHANGED_LINE.rstrip("\n") in result.quote.splitlines()


def test_quote_change_is_limited() -> None:
    base = "".join(f"line {i}\n" for i in range(50)).encode()
    ours = "".join(f"other {i}\n" for i in range(50)).encode()
    quote = quote_change(base, ours, limit=5)
    assert len(quote.splitlines()) == 6
    assert quote.splitlines()[-1].endswith("more lines)")


# ── quality.py ────────────────────────────────────────────────────────────────


def test_parse_quality_stock() -> None:
    blocks, error = parse_quality(stock().quality_source)
    assert error is None
    assert blocks["test"].argv == ("just", "test") and blocks["test"].timeout == 600
    assert blocks["test"].literal and not blocks["test"].placeholder
    assert blocks["lint"].placeholder and blocks["lint"].argv is None
    assert blocks["typecheck"].argv == ("just", "typecheck")
    assert blocks["build"].argv == ("just", "build")


def test_parse_quality_literals_and_not() -> None:
    source = stock().quality_source
    omnibus = source.replace("timeout_seconds=600,", "timeout_seconds=1800,").replace(
        'argv=_placeholder("lint"),', 'argv=["just", "lint"],'
    )
    blocks, _ = parse_quality(omnibus)
    assert blocks["test"].timeout == 1800 and blocks["lint"].argv == ("just", "lint")
    assert same_as_stock(omnibus, source)
    computed = source.replace('argv=["just", "test"],', 'argv=["just", *EXTRA],')
    blocks, _ = parse_quality(computed)
    assert not blocks["test"].literal and blocks["test"].argv is None
    assert same_as_stock(computed, source)
    flag = source.replace("timeout_seconds=600,", "timeout_seconds=True,")
    assert not parse_quality(flag)[0]["test"].literal
    added = source + "\nprint('extra')\n"
    assert not same_as_stock(added, source)
    assert parse_quality("def (:\n")[1] is not None
    assert not same_as_stock("def (:\n", source)


# ── TS imports ────────────────────────────────────────────────────────────────


def test_ts_closure() -> None:
    folder = SSSF_TEMPLATES / "harness_engineering"
    files = {f"he/{p.name}": p.read_bytes() for p in folder.glob("*.ts")}
    paths, error = _ts_closure("he/subagents.ts", files)
    assert error is None and paths == ["he/subagents.ts", "he/themeMap.ts"]
    assert _ts_closure("he/themeMap.ts", files) == (["he/themeMap.ts"], None)
    files["he/out.ts"] = b'import { x } from "../shared/x.ts";\n'
    files["shared/x.ts"] = b"export const x = 1;\n"
    paths, error = _ts_closure("he/out.ts", files)
    assert paths == [] and error is not None and "outside" in error
    files["he/gone.ts"] = b'export * from "./missing";\n'
    paths, error = _ts_closure("he/gone.ts", files)
    assert error is not None and "not a file" in error
    files["he/dyn.ts"] = b'const m = await import("./lib");\n'
    files["he/lib/index.ts"] = b"export {};\n"
    assert _ts_closure("he/dyn.ts", files) == (["he/dyn.ts", "he/lib/index.ts"], None)
