#!/usr/bin/env -S uv run
# /// script
# dependencies = ["pydantic", "python-dotenv", "pyyaml", "rich"]
# ///
"""Models — what this machine can actually run, across both coding agents.

Usage:
    uv run adws/adw_models.py                 # free pi models + every Claude alias
    uv run adws/adw_models.py kimi            # search everything for "kimi"
    uv run adws/adw_models.py --all           # the whole catalog, both harnesses

Not an ADW: it spawns nothing and traces nothing. It exists because composing a
chain means choosing models, and choosing from memory is how you end up with
`--model buidler=opus` and a validation error twenty seconds later.

The harness column is the point. It is derived from the name exactly as
`adw_modules/models.py` derives it at run time, so what this prints is what a
chain will do — an alias or claude-* id goes to Claude Code, provider/id to pi.
"""

import argparse
import sys

from adw_modules import models


def main(query: str = "", show_all: bool = False) -> int:
    rows = models.catalog(free_only=not show_all and not query, query=query)
    if not rows:
        print(f"nothing matches {query!r} — try `uv run adws/adw_models.py --all`")
        return 1
    width = max(len(model) for _, model, _ in rows)
    print(f"{'harness':12} {'model':{width}}  context")
    for harness, model, window in rows:
        ceiling = f"{window:,}" if window else "-"
        print(f"{harness:12} {model:{width}}  {ceiling:>9}")
    print(f"\n{len(rows)} model(s). Use one as `--model <agent>=<model>` or in a "
          f"chain step as `build@<model>`.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", nargs="?", default="", help="substring to search for")
    parser.add_argument("--all", action="store_true", help="every model, not just the free ones")
    args = parser.parse_args()
    sys.exit(main(args.query, args.all))
