"""The ``library`` rule group: the library in ``$HAIFA_HOME`` and the installed HAIFA.

Everything comes from one ``library_status(fetch=False)``: ahead/behind compare the
library with its local remote-tracking ref, so they are as of the last fetch. Nothing
is fetched and nothing is written (no lock, no ``$HAIFA_HOME``). The rules run outside a
git repository too.
"""

from __future__ import annotations

from collections.abc import Iterator

from aifactory import __version__
from aifactory.check.context import CheckContext
from aifactory.check.model import Finding, Rule, RuleGroup
from aifactory.library.store import library_root

_LIST_MAX = 5


def _ids(ids: list[str]) -> str:
    shown = ", ".join(ids[:_LIST_MAX])
    more = len(ids) - _LIST_MAX
    return f"{shown} (+{more} more)" if more > 0 else shown


def library(ctx: CheckContext) -> Iterator[Finding]:
    data = ctx.library
    if data is None:
        yield Finding(
            "library_missing",
            "library",
            "warning",
            f"no library at {library_root(ctx.environ)}",
            "factory library clone URL (the team library), or factory library init",
        )
        return
    path = data["library"]
    if data["dirty"]:
        uncommitted = list(data["uncommitted"])
        yield Finding(
            "library_dirty",
            "library",
            "warning",
            f"the library has {len(uncommitted)} uncommitted change(s): {_ids(uncommitted)}",
            f"commit or discard them in {path} (git -C {path} status)",
        )
    if data["remote"] is None:
        return
    when = f"as of the last fetch ({data['last_fetch'] or 'never'})"
    if data["behind"]:
        yield Finding(
            "library_behind",
            "library",
            "warning",
            f"the library is {data['behind']} commit(s) behind {data['remote']}, {when}",
            "factory library pull",
        )
    if data["ahead"]:
        yield Finding(
            "library_unpushed",
            "library",
            "warning",
            f"the library has {data['ahead']} commit(s) not pushed to {data['remote']}, {when}",
            "factory library push",
        )


def seed(ctx: CheckContext) -> Iterator[Finding]:
    data = ctx.library
    if data is None or not data["seed_update_available"]:
        return
    yield Finding(
        "seed_update_available",
        "library",
        "info",
        f"the installed seed has new versions of {_ids(list(data['seed_updates']))}",
        "factory library seed",
    )


def factory_version(ctx: CheckContext) -> Iterator[Finding]:
    data = ctx.library
    if data is None or data["compatible"] is not False:
        return
    yield Finding(
        "factory_outdated",
        "machine",
        "error",
        f"the library needs factory {data['min_factory_version']}, installed {__version__}",
        "factory upgrade",
    )


LIBRARY_GROUP = RuleGroup(
    "library",
    (
        Rule("factory version", factory_version, needs_install=False, needs_repo=False),
        Rule("library", library, needs_install=False, needs_repo=False),
        Rule("seed", seed, needs_install=False, needs_repo=False),
    ),
    scope="library",
)
