"""The sssf conversion of ``factory onboard`` (AR32): ``adws/`` of base into ``.factory/``.

Only the tree of base is read (``ls-tree`` and ``cat-file``) and of the rosters only
``adws/adw_sssf_config/sssf.config.yaml``; ``adws/`` stays byte for byte. The decisions:

- agents: ``coding_agent`` becomes ``harness`` (``claude_code`` -> ``claude``); ``model``,
  ``tools``, ``color``, ``writes`` and ``disallowed_commands`` are copied; ``thinking: auto``
  becomes ``medium`` (``changed_meaning``), as does nothing else; ``writes`` with
  ``**/*.md`` is ``changed_meaning``. ``defaults.data_dir`` and ``observability`` are
  ``not_converted``; ``defaults.protected_files`` goes to ``config.yaml`` after ``.factory/``.
- prompts: a stock ``system.md`` is the library's; a changed one is merged three ways
  (base stock sssf, ours repo, theirs library). ``user.md`` is always the library's. An
  agent without a stock template keeps its prompts (``manual``). The result is linked to
  the library when the library has it, else a new library item (D30 names).
- ``harness_engineering``: every ``.ts`` entry point with its relative imports is an
  extension item; the agent binding is ``harness_engineering: [.factory/extensions/...]``.
- chains: stock chains by blob id are the library workflows of the same name;
  ``simple-sdlc`` is always added, the others with ``--workflows``.
- ``adws/adw_modules/quality.py``: the test block's literal argv and timeout become
  ``test_command`` and ``test_timeout`` (read with ``ast``, nothing runs).
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import ValidationError

from aifactory import harness
from aifactory.config.loader import AGENTS_FILE, PROMPTS_DIR, WORKFLOWS_DIR
from aifactory.config.manifest import ManifestEntry
from aifactory.config.settings import CONFIG_FILE, ProjectSettings
from aifactory.harness.override import THINKING_LEVELS
from aifactory.library.load import library_path
from aifactory.library.model import AgentDefaults, Item, ItemFile, ItemType, check_name
from aifactory.library.store import LibraryStoreError, NewFile, SeedItem
from aifactory.library.tree import TreeFile, read_blobs, tree_files
from aifactory.library.version import agent_version, tree_version
from aifactory.onboard.extract import (
    Extraction,
    ReportCode,
    ReportRow,
    _check_options,
    _library_heads,
    _link,
    _new_name,
    slug,
)
from aifactory.onboard.merge import merge_prompt, quote_change
from aifactory.onboard.quality import parse_quality, same_as_stock
from aifactory.onboard.stock import SSSF_ROSTER, stock

if TYPE_CHECKING:
    from aifactory.library.detect import Detected
    from aifactory.library.install import _Source

SSSF_DIR = "adws/"
SSSF_CONFIG_DIR = "adws/adw_sssf_config/"
HARNESS_DIR = "adws/adw_data/harness_engineering/"
MODULES_DIR = "adws/adw_modules/"
RECIPES_DIR = "adws/adw_recipes/"
QUALITY_FILE = "adws/adw_modules/quality.py"
SKILL_DIR = ".claude/skills/sssf/"
LEFT_FILES = ("justfile", ".env", ".env.sample")
EXTENSIONS_DIR = ".factory/extensions"
# keys an agent inherits from the roster defaults (sssf's engine)
INHERITED = (
    "coding_agent",
    "harness",
    "model",
    "thinking",
    "color",
    "tools",
    "writes",
    "disallowed_commands",
    "harness_engineering",
)
COPIED = ("model", "tools", "writes", "color", "disallowed_commands")
ENTRY_ORDER = (
    "name",
    "purpose",
    "harness",
    "model",
    "thinking",
    "tools",
    "writes",
    "color",
    "harness_engineering",
    "disallowed_commands",
)
ALL_MARKDOWN = "**/*.md"
_IMPORTS = (
    re.compile(r"""from\s+["'](\.{1,2}/[^"']+)["']"""),
    re.compile(r"""import\s+["'](\.{1,2}/[^"']+)["']"""),
    re.compile(r"""import\(\s*["'](\.{1,2}/[^"']+)["']\s*\)"""),
)
_REGULAR = ("100644", "100755")


@dataclass
class SssfConversion:
    """What the sssf conversion plans: the extraction, the settings and the roster."""

    extraction: Extraction
    settings: ProjectSettings
    roster: list[dict[str, Any]]
    workflows: list[str]
    source_paths: list[str]
    source_files: dict[str, TreeFile] = field(default_factory=dict)


@dataclass
class _Agent:
    """One roster agent on its way through the conversion."""

    slot: str
    raw: dict[str, Any]
    entry: dict[str, Any]
    harness: str
    entry_points: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=list)
    rows: list[ReportRow] = field(default_factory=list)


@dataclass
class _Rows:
    agents: list[ReportRow] = field(default_factory=list)
    added: list[ReportRow] = field(default_factory=list)
    extensions: list[ReportRow] = field(default_factory=list)
    roster: list[ReportRow] = field(default_factory=list)
    workflows: list[ReportRow] = field(default_factory=list)
    chains: list[ReportRow] = field(default_factory=list)
    config: list[ReportRow] = field(default_factory=list)
    quality: list[ReportRow] = field(default_factory=list)
    leftovers: list[ReportRow] = field(default_factory=list)
    modules: list[ReportRow] = field(default_factory=list)
    left: list[ReportRow] = field(default_factory=list)

    def all(self) -> list[ReportRow]:
        return [
            *self.agents,
            *self.added,
            *self.extensions,
            *self.roster,
            *self.workflows,
            *self.chains,
            *self.config,
            *self.quality,
            *self.leftovers,
            *self.modules,
            *self.left,
        ]


# ── TS imports ────────────────────────────────────────────────────────────────


def _ts_closure(entry: str, files: Mapping[str, bytes]) -> tuple[list[str], str | None]:
    """The entry ``.ts`` file and every file it reaches by relative imports.

    A target outside the entry's directory or missing in base is an error text.
    """
    if entry not in files:
        return [], f"{entry} is not a file in base"
    top = posixpath.dirname(entry)
    seen = {entry}
    queue = [entry]
    while queue:
        path = queue.pop(0)
        text = files[path].decode("utf-8", "replace")
        here = posixpath.dirname(path)
        specs = [m for pattern in _IMPORTS for m in pattern.findall(text)]
        for spec in specs:
            joined = posixpath.normpath(posixpath.join(here, spec))
            target = next(
                (c for c in (joined, joined + ".ts", joined + "/index.ts") if c in files), None
            )
            inside = top == "" or joined == top or joined.startswith(top + "/")
            if not inside:
                return [], f"{path} imports {spec}, outside {top or '.'}/"
            if target is None:
                return [], f"{path} imports {spec}, which is not a file in base"
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return [entry, *sorted(seen - {entry})], None


# ── helpers ───────────────────────────────────────────────────────────────────


def _roster_error(problem: str) -> LibraryStoreError:
    return LibraryStoreError(
        "sssf_roster_invalid", f"{SSSF_ROSTER}: {problem}; only this roster is converted"
    )


def _load_roster(data: bytes | None) -> dict[str, Any]:
    if data is None:
        raise _roster_error("missing in base")
    try:
        raw = yaml.safe_load(data.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise _roster_error(f"not YAML ({exc})") from exc
    if not isinstance(raw, dict):
        raise _roster_error("not a mapping")
    agents = raw.get("agents")
    if not isinstance(agents, list) or not all(
        isinstance(a, dict) and isinstance(a.get("name"), str) and a["name"] for a in agents
    ):
        raise _roster_error("agents must be a list of mappings with a name")
    if raw.get("defaults") is not None and not isinstance(raw["defaults"], dict):
        raise _roster_error("defaults must be a mapping")
    return raw


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _yaml(header: str, data: Mapping[str, Any]) -> bytes:
    from aifactory.library.install import _yaml as render

    return render(header, data)


def _git_blob(data: bytes) -> str:
    import hashlib

    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _load_library(source: _Source, kind: ItemType, name: str) -> Item | None:
    try:
        return source.load(kind, [name])[name]
    except LibraryStoreError as exc:
        if exc.code in ("unknown_item", "invalid_item"):
            return None
        raise


# ── the converter ─────────────────────────────────────────────────────────────


class _Converter:
    def __init__(
        self,
        root: Path,
        base: str,
        base_sha: str,
        source: _Source,
        environ: Mapping[str, str] | None,
        detected: Detected,
        keep: set[tuple[ItemType, str]],
        renames: Mapping[tuple[ItemType, str], str],
        workflows: bool,
        rosters: tuple[str, ...],
    ) -> None:
        self.root, self.base, self.base_sha = root, base, base_sha
        self.source, self.environ, self.detected = source, environ, detected
        self.keep, self.renames, self.with_workflows = keep, renames, workflows
        self.rosters = rosters
        self.out = Extraction()
        self.rows = _Rows()
        self.repo_slug = slug(root.name)
        self.planned: dict[tuple[ItemType, str], str] = {}
        self.by_version: dict[tuple[ItemType, str], str] = {}
        self.read_paths: set[str] = set()

    # base

    def read_base(self) -> None:
        listed = tree_files(
            self.root,
            self.base_sha,
            [SSSF_DIR, SKILL_DIR, *LEFT_FILES],
        )
        self.tree: dict[str, TreeFile] = {f.path: f for f in listed}
        roster = self.tree.get(SSSF_ROSTER)
        if roster is not None and roster.mode not in _REGULAR:
            raise _roster_error("not a regular file")
        wanted = [roster.blob] if roster is not None else []
        self.raw = _load_roster(read_blobs(self.root, wanted)[roster.blob] if roster else None)
        self.defaults: dict[str, Any] = dict(self.raw.get("defaults") or {})
        extra: list[str] = []
        for agent in self.raw["agents"]:
            pe = agent.get("prompt_engineering")
            if isinstance(pe, dict):
                extra += [str(p) for p in pe.values() if isinstance(p, str)]
            for key in ("harness_engineering",):
                for p in _as_list(agent.get(key, self.defaults.get(key))):
                    if isinstance(p, str):
                        extra.append(posixpath.dirname(p) + "/" if "/" in p else p)
        outside = sorted({p for p in extra if not p.startswith(SSSF_DIR) and p not in self.tree})
        if outside:
            for f in tree_files(self.root, self.base_sha, outside):
                self.tree.setdefault(f.path, f)
        blobs = [
            f.blob
            for f in self.tree.values()
            if f.mode in _REGULAR
            and (
                f.path.endswith(".ts")
                or f.path == QUALITY_FILE
                or f.path in {p for p in extra if not p.endswith("/")}
            )
        ]
        self.blobs = read_blobs(self.root, blobs)

    def data(self, path: str) -> bytes | None:
        f = self.tree.get(path)
        if f is None or f.mode not in _REGULAR:
            return None
        self.read_paths.add(path)
        return self.blobs.get(f.blob)

    # naming (D30, same as O2)

    def decide(
        self, kind: ItemType, slot: str, version: str, files: tuple[NewFile, ...]
    ) -> tuple[ReportCode, str, str, str]:
        """(code, item, version, message) of a slot whose content has `version`."""
        found = _link(self.root, kind, slot, version, self.heads, self.environ)
        if found is not None:
            return "linked", found[0], version, found[1]
        if (kind, version) in self.by_version:
            name = self.by_version[(kind, version)]
            return "linked", name, version, f"same content as the new library item {name}"
        if (kind, slot) in self.keep:
            head = self.heads.get((kind, slot))
            if head is None:
                raise LibraryStoreError(
                    "unknown_item",
                    f"--keep-local {kind}/{slot}: the library has no {kind} {slot!r}",
                )
            return (
                "carried_over",
                slot,
                head,
                f"the converted content differs from library item {slot}; the difference "
                "stays in the repo",
            )
        name = _new_name(kind, slot, self.renames, self.heads, self.planned, self.repo_slug)
        self.planned[(kind, name)] = version
        self.by_version[(kind, version)] = name
        return "converted", name, version, f"new library item {name}"

    # settings

    def settings(self) -> None:
        protected = [".factory/"]
        for value in _as_list(self.defaults.get("protected_files")):
            if not isinstance(value, str) or not value.strip():
                self.rows.leftovers.append(
                    ReportRow(
                        "manual",
                        f"{SSSF_ROSTER}:protected_files",
                        f"entry {value!r} is not a path; it is left out",
                    )
                )
            elif value not in protected:
                protected.append(value)
        self.quality()
        detected = self.detected
        values: dict[str, Any] = {
            "base": self.base,
            "remote": detected.remote or "origin",
            "git_provider": detected.provider,
            "protected_files": protected,
        }
        if detected.provider == "azure" and detected.info.azure is not None:
            values["azure"] = dict(detected.info.azure)
        if self.test_command is not None:
            values["test_command"] = list(self.test_command)
        if self.test_timeout is not None:
            values["test_timeout"] = self.test_timeout
        try:
            self.project = ProjectSettings.model_validate(values)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or 'settings'}: {err['msg']}"
                for err in exc.errors()
            )
            raise LibraryStoreError("invalid_value", f"invalid settings: {problems}") from exc
        s = self.project
        config: dict[str, Any] = {"base": s.base}
        if detected.remote is not None:
            config["remote"] = s.remote
        config["git_provider"] = s.git_provider
        if s.azure is not None:
            config["azure"] = s.azure.model_dump(mode="json")
        config.update({"backlog_dir": s.backlog_dir, "specs_dir": s.specs_dir})
        config["docs_dir"] = s.docs_dir
        if s.test_command is not None:
            config["test_command"] = list(s.test_command)
        if s.test_timeout is not None:
            config["test_timeout"] = s.test_timeout
        config["protected_files"] = list(s.protected_files)
        header = (
            "# factory project settings, converted by factory onboard from sssf (adws/) in "
            f"{self.base}@{self.base_sha[:12]}\n"
        )
        self.out.files[CONFIG_FILE] = _yaml(header, config)
        where = f"remote {s.remote}" if detected.remote is not None else "no remote"
        self.rows.config.append(
            ReportRow(
                "converted",
                CONFIG_FILE,
                f"base {s.base}, {where}, provider {s.git_provider} detected; "
                "protected_files .factory/ plus the sssf defaults.protected_files",
            )
        )

    def quality(self) -> None:
        self.test_command: tuple[str, ...] | None = None
        self.test_timeout: int | None = None
        text = self.data(QUALITY_FILE)
        if text is None:
            return
        source = text.decode("utf-8", "replace")
        blocks, error = parse_quality(source)
        rows = self.rows.quality
        if error is not None:
            rows.append(ReportRow("manual", QUALITY_FILE, f"{error}; nothing is converted"))
            return
        for name, block in blocks.items():
            subject = f"{QUALITY_FILE}:{name}"
            if name == "test":
                if block.placeholder:
                    rows.append(
                        ReportRow(
                            "not_converted",
                            subject,
                            "placeholder; set test_command in .factory/config.yaml",
                        )
                    )
                elif not block.literal or block.argv is None:
                    rows.append(
                        ReportRow(
                            "manual",
                            subject,
                            "argv or timeout_seconds is not a literal; set test_command and "
                            "test_timeout in .factory/config.yaml",
                        )
                    )
                else:
                    self.test_command, self.test_timeout = block.argv, block.timeout
                    message = f"test_command [{', '.join(block.argv)}]"
                    if block.timeout is not None:
                        message += f", test_timeout {block.timeout}"
                    rows.append(ReportRow("converted", subject, message))
                continue
            if block.placeholder:
                what = "placeholder"
            elif block.argv is not None:
                what = "argv [" + ", ".join(block.argv) + "]"
            else:
                what = "argv not a literal"
            rows.append(
                ReportRow(
                    "not_converted",
                    subject,
                    f"{what}; HAIFA runs only the test command (test_command)",
                )
            )
        if not same_as_stock(source, stock().quality_source):
            rows.append(
                ReportRow(
                    "manual",
                    QUALITY_FILE,
                    "changes beyond the QualityCheckSpec literals are engine code (EX7); "
                    "not converted",
                )
            )

    # agents: bindings

    def bindings(self) -> list[_Agent]:
        agents: list[_Agent] = []
        inherited = {k: self.defaults[k] for k in INHERITED if k in self.defaults}
        for raw in self.raw["agents"]:
            slot = str(raw["name"])
            eff = {**inherited, **raw}
            subject = f"agent/{slot}"
            rows: list[ReportRow] = []
            name = eff.get("harness") or eff.get("coding_agent") or "pi"
            try:
                used = harness.canonical(str(name))
            except ValueError:
                self.rows.agents.append(
                    ReportRow(
                        "manual",
                        subject,
                        f"unknown coding_agent {name!r}; the agent is not converted",
                    )
                )
                continue
            entry: dict[str, Any] = {"name": slot, "harness": used}
            thinking = eff.get("thinking")
            if thinking == "auto":
                entry["thinking"] = "medium"
                rows.append(
                    ReportRow(
                        "changed_meaning",
                        f"{subject}/thinking",
                        "sssf auto: claude ran on medium, pi got auto; HAIFA uses medium",
                    )
                )
            elif thinking is not None and thinking not in THINKING_LEVELS:
                rows.append(
                    ReportRow(
                        "manual",
                        f"{subject}/thinking",
                        f"thinking {thinking!r} is not one of {list(THINKING_LEVELS)}; left out",
                    )
                )
            elif thinking is not None:
                entry["thinking"] = str(thinking)
            for key in COPIED:
                if eff.get(key) is not None:
                    entry[key] = eff[key]
            writes = entry.get("writes")
            if isinstance(writes, list) and ALL_MARKDOWN in writes:
                rows.append(
                    ReportRow(
                        "changed_meaning",
                        f"{subject}/writes",
                        "writes **/*.md lets the agent edit every markdown file, also protected "
                        "ones such as .factory/prompts/",
                    )
                )
            points = [str(p) for p in _as_list(eff.get("harness_engineering")) if p]
            agent = _Agent(slot, raw, entry, used, rows=rows)
            if points and used != "pi":
                rows.append(
                    ReportRow(
                        "not_converted",
                        f"{subject}/harness_engineering",
                        "pi extensions are pi's; the binding is left out",
                    )
                )
            elif points:
                agent.entry_points = points
            agents.append(agent)
        return agents

    # extensions

    def extensions(self, agents: list[_Agent]) -> None:
        ts = {
            path: data
            for path, f in self.tree.items()
            if path.endswith(".ts") and (data := self.blobs.get(f.blob)) is not None
        }
        points: list[str] = []
        for agent in agents:
            points += [p for p in agent.entry_points if p not in points]
        done: dict[str, str] = {}  # entry point -> extension name in the repo
        reached: set[str] = set()
        for point in points:
            name = PurePosixPath(point).stem
            label = name if check_name(name) else point
            subject = f"extension/{label}"
            if not check_name(name):
                self.rows.extensions.append(
                    ReportRow("manual", subject, f"{name!r} is not a valid item name")
                )
                continue
            if name in done.values():
                self.rows.extensions.append(
                    ReportRow("manual", subject, f"{point}: another entry point is named {name}")
                )
                continue
            closure, error = _ts_closure(point, ts)
            if error is not None:
                self.rows.extensions.append(ReportRow("manual", subject, error))
                continue
            top = posixpath.dirname(point)
            item_files = [
                ItemFile(
                    posixpath.relpath(p, top) if top else p,
                    self.tree[p].mode == "100755",
                    ts[p],
                )
                for p in closure
            ]
            self.read_paths.update(closure)
            reached.update(closure)
            version = tree_version(item_files)
            rel = library_path("extension", name)
            news = tuple(NewFile(f"{rel}/{f.path}", f.executable, f.data) for f in item_files)
            try:
                code, item, at, message = self.decide("extension", name, version, news)
            except LibraryStoreError as exc:
                if exc.code != "name_taken":
                    raise
                self.rows.extensions.append(ReportRow("manual", subject, exc.message))
                continue
            if code == "converted" and item != name:
                # an extension item keeps the file name of its entry point
                self.planned.pop(("extension", item), None)
                self.by_version.pop(("extension", version), None)
                self.rows.extensions.append(
                    ReportRow(
                        "manual",
                        subject,
                        f"the library has another extension {name}; port {point} by hand",
                    )
                )
                continue
            if code == "converted":
                self.out.library_items.append(SeedItem("extension", item, version, news))
            for f in item_files:
                self.out.files[f"{EXTENSIONS_DIR}/{name}/{f.path}"] = f.data
            self.out.entries["extension"][name] = ManifestEntry(item=item, version=at)
            imports = [posixpath.basename(p) for p in closure[1:]]
            if imports:
                message += "; imports " + ", ".join(imports)
            self.rows.extensions.append(ReportRow(code, subject, message, item, at))
            done[point] = name
        for agent in agents:
            names = [done[p] for p in agent.entry_points if p in done]
            agent.extensions = names
            if names:
                agent.entry["harness_engineering"] = [f"{EXTENSIONS_DIR}/{n}/{n}.ts" for n in names]
        for path in sorted(self.tree):
            if path.startswith(HARNESS_DIR) and path.endswith(".ts") and path not in reached:
                self.rows.extensions.append(ReportRow("not_converted", path, "no agent loads it"))

    # agents: content

    def agent_content(self, agent: _Agent) -> bool:
        slot, raw = agent.slot, agent.raw
        subject = f"agent/{slot}"
        pe = raw.get("prompt_engineering")
        texts: dict[str, bytes] = {}
        for kind in ("system", "user"):
            path = pe.get(kind) if isinstance(pe, dict) else None
            data = self.data(str(path)) if isinstance(path, str) else None
            if data is None:
                self.rows.agents.append(
                    ReportRow(
                        "manual",
                        subject,
                        f"prompt {path or f'prompt_engineering.{kind}'} missing in base; the "
                        "agent is not converted",
                    )
                )
                return False
            texts[kind] = data
        sys_r, usr_r = texts["system"], texts["user"]
        roster_purpose = str(raw.get("purpose") or "")
        stock_agent = stock().agents.get(slot)
        library = _load_library(self.source, "agent", slot)
        sub: list[ReportRow] = []
        note = ""
        if stock_agent is not None and library is not None:
            lib_system = library.file("system.md")
            lib_user = library.file("user.md")
            merged = merge_prompt(stock_agent.system, sys_r, lib_system.data if lib_system else b"")
            system = merged.text
            if merged.kind == "union":
                sub.append(
                    ReportRow(
                        "carried_over",
                        f"{subject}/system.md",
                        "the changes to stock sssf system.md were insertions next to the "
                        "library's; both kept (git merge-file --union)",
                    )
                )
                note = "; system.md merged with --union"
            elif merged.kind == "conflict":
                sub.append(
                    ReportRow(
                        "manual",
                        f"{subject}/system.md",
                        "the change conflicts with the library text; the library text is used, "
                        "port the change by hand",
                        detail=merged.quote,
                    )
                )
            elif merged.kind == "clean":
                note = "; system.md merged cleanly"
            user = lib_user.data if lib_user else b""
            if usr_r != stock_agent.user:
                sub.append(
                    ReportRow(
                        "manual",
                        f"{subject}/user.md",
                        "sssf names outputs by adw_id and HAIFA returns them (R25); the library "
                        "text is used",
                        detail=quote_change(stock_agent.user, usr_r),
                    )
                )
            if not roster_purpose or roster_purpose == stock_agent.purpose:
                purpose = library.purpose
            else:
                purpose = roster_purpose
                note += "; the roster's own purpose is kept"
        else:
            system, user, purpose = sys_r, usr_r, roster_purpose
            sub.append(
                ReportRow(
                    "manual",
                    subject,
                    "no stock sssf template: the prompts are taken over unchanged; check them "
                    "by hand",
                )
            )
        version = agent_version(purpose, system, user)
        news = self.agent_files(agent, purpose, system, user)
        code, item, at, message = self.decide("agent", slot, version, news(slot))
        if code == "converted":
            self.out.library_items.append(SeedItem("agent", item, version, news(item)))
        self.out.entries["agent"][slot] = ManifestEntry(item=item, version=at)
        self.out.files[f"{PROMPTS_DIR}/{slot}/system.md"] = system
        self.out.files[f"{PROMPTS_DIR}/{slot}/user.md"] = user
        agent.entry["purpose"] = purpose
        self.rows.agents.append(ReportRow(code, subject, message + note, item, at))
        self.rows.agents += agent.rows + sub
        return True

    def agent_files(self, agent: _Agent, purpose: str, system: bytes, user: bytes) -> Any:
        from aifactory.onboard.adopt import _unexpand

        entry = agent.entry
        defaults: dict[str, Any] = {"harness": agent.harness}
        for key in ("model", "thinking", "tools", "writes", "color"):
            value = entry.get(key)
            if value is None:
                continue
            if key == "writes" and isinstance(value, list):
                value = _unexpand(value, self.project)
            defaults[key] = value
        if agent.extensions:
            defaults["extensions"] = list(agent.extensions)
        try:
            AgentDefaults.model_validate(defaults)
        except ValidationError:
            defaults = {}

        def files(name: str) -> tuple[NewFile, ...]:
            meta: dict[str, Any] = {"purpose": purpose}
            if defaults:
                meta["defaults"] = defaults
            text = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).encode("utf-8")
            rel = library_path("agent", name)
            return (
                NewFile(f"{rel}/agent.yaml", False, text),
                NewFile(f"{rel}/system.md", False, system),
                NewFile(f"{rel}/user.md", False, user),
            )

        return files

    # workflows and chains

    def chains(self) -> list[str]:
        known = stock()
        wanted: dict[str, str] = {}
        for path in sorted(self.tree):
            name = path[len(SSSF_DIR) :]
            if "/" in name or not (name.startswith("adw_") and name.endswith(".py")):
                if path.startswith(RECIPES_DIR) and path != f"{RECIPES_DIR}README.md":
                    self.rows.chains.append(
                        ReportRow("not_converted", path, "recipes are not converted")
                    )
                continue
            f = self.tree[path]
            self.read_paths.add(path)
            workflow = known.chains.get(f.blob) if f.mode in _REGULAR else None
            if workflow is not None:
                if workflow == "simple-sdlc" or self.with_workflows:
                    wanted.setdefault(workflow, path)
                else:
                    self.rows.chains.append(
                        ReportRow(
                            "not_converted",
                            path,
                            f"stock chain; the library workflow {workflow} replaces it: "
                            f"factory onboard --workflows or later factory config add "
                            f"workflow {workflow}",
                        )
                    )
            elif name in known.chain_files:
                workflow = known.chain_files[name]
                self.rows.chains.append(
                    ReportRow(
                        "manual",
                        path,
                        f"differs from stock sssf; the library workflow {workflow} is the stock "
                        "version, port the change by hand",
                    )
                )
            elif known.scripts.get(name) == f.blob:
                self.rows.chains.append(ReportRow("not_converted", path, "no HAIFA workflow"))
            else:
                self.rows.chains.append(
                    ReportRow(
                        "manual", path, "not a stock sssf script; not converted, port it by hand"
                    )
                )
        self.chain_of = wanted
        rest = sorted(w for w in wanted if w != "simple-sdlc")
        return ["simple-sdlc", *rest]

    def workflows(self, names: list[str], converted: list[_Agent]) -> list[str]:
        from aifactory.library.agent import roster_entry
        from aifactory.library.install import _workflow_agents

        planned: list[str] = []
        present = {a.slot for a in converted}
        for wf in names:
            subject = f"workflow/{wf}"
            item = _load_library(self.source, "workflow", wf)
            if item is None:
                self.rows.workflows.append(
                    ReportRow("manual", subject, "the library has no such workflow")
                )
                self.out.warnings.append(
                    f"unknown_workflow: workflow {wf} replaces an sssf chain; the library "
                    "does not have it"
                )
                continue
            self.out.files[f"{WORKFLOWS_DIR}/{wf}.yaml"] = item.files[0].data
            self.out.entries["workflow"][wf] = ManifestEntry(item=wf, version=item.version)
            self.out.added_workflows.append(wf)
            planned.append(wf)
            chain = self.chain_of.get(wf)
            how = f"; replaces the stock chain {chain}" if chain else ""
            self.rows.workflows.append(
                ReportRow("linked", subject, f"added from the library{how}", wf, item.version)
            )
            for name in _workflow_agents(item):
                if name in present:
                    continue
                present.add(name)
                agent = _load_library(self.source, "agent", name)
                if agent is None:
                    self.rows.added.append(
                        ReportRow(
                            "manual",
                            f"agent/{name}",
                            f"workflow {wf} needs it; neither the roster nor the library has it",
                        )
                    )
                    continue
                self.added_roster.append(roster_entry(agent, self.project))
                for prompt in ("system.md", "user.md"):
                    found = agent.file(prompt)
                    self.out.files[f"{PROMPTS_DIR}/{name}/{prompt}"] = found.data if found else b""
                self.out.entries["agent"][name] = ManifestEntry(item=name, version=agent.version)
                self.rows.added.append(
                    ReportRow(
                        "linked",
                        f"agent/{name}",
                        f"added from the library; workflow {wf} needs it",
                        name,
                        agent.version,
                    )
                )
        return planned

    # leftovers

    def leftovers(self) -> None:
        if "data_dir" in self.defaults:
            self.rows.leftovers.append(
                ReportRow(
                    "not_converted",
                    f"{SSSF_ROSTER}:data_dir",
                    "runtime data and the tracer live in .factory/ and factory obs",
                )
            )
        if "observability" in self.raw:
            self.rows.leftovers.append(
                ReportRow(
                    "not_converted",
                    f"{SSSF_ROSTER}:observability",
                    "runtime data and the tracer live in .factory/ and factory obs",
                )
            )
        others = [r for r in self.rosters if r != SSSF_ROSTER]
        for path in others:
            self.rows.leftovers.append(
                ReportRow("not_converted", path, f"only {SSSF_ROSTER} is converted")
            )
        if others:
            self.out.warnings.append(
                f"alternate_rosters: {', '.join(others)} are not converted; only {SSSF_ROSTER} is"
            )
        modules = stock().modules
        for path in sorted(self.tree):
            if not path.startswith(MODULES_DIR) or path == QUALITY_FILE:
                continue
            rel = path[len(MODULES_DIR) :]
            if modules.get(rel) == self.tree[path].blob:
                continue
            self.rows.modules.append(
                ReportRow(
                    "manual", path, "differs from stock sssf; engine code, not converted (EX7)"
                )
            )
        if any(p.startswith(SSSF_DIR) for p in self.tree):
            self.rows.left.append(
                ReportRow(
                    "left_in_place", SSSF_DIR, "stays unchanged; delete it in a separate commit"
                )
            )
        if any(p.startswith(SKILL_DIR) for p in self.tree):
            self.rows.left.append(
                ReportRow("left_in_place", SKILL_DIR, "the sssf skill stays as it is")
            )
        for path in LEFT_FILES:
            if path in self.tree:
                self.rows.left.append(ReportRow("left_in_place", path, "stays as it is"))

    # all

    def run(self) -> SssfConversion:
        self.read_base()
        slots: list[tuple[ItemType, str]] = [("agent", str(a["name"])) for a in self.raw["agents"]]
        _check_options(f"an agent of {SSSF_ROSTER} in {self.base}", self.keep, self.renames, slots)
        self.heads = _library_heads(self.source, ("agent", "workflow", "extension"))
        self.added_roster: list[dict[str, Any]] = []
        self.settings()
        agents = self.bindings()
        self.extensions(agents)
        converted = [a for a in agents if self.agent_content(a)]
        workflows = self.workflows(self.chains(), converted)
        roster = [
            {k: a.entry[k] for k in ENTRY_ORDER if k in a.entry} for a in converted
        ] + self.added_roster
        header = (
            "# agents of this repo, converted by factory onboard from the sssf roster "
            f"{SSSF_ROSTER} ({self.base}@{self.base_sha[:12]})\n"
        )
        self.out.files[AGENTS_FILE] = _yaml(header, {"agents": roster})
        self.rows.roster.append(
            ReportRow(
                "converted",
                AGENTS_FILE,
                f"bindings of {len(converted)} agents from {SSSF_ROSTER}: coding_agent -> "
                "harness (claude_code -> claude), model, thinking, tools, color, writes; pi model "
                "ids are checked by factory check against this machine's catalogue",
            )
        )
        self.leftovers()
        self.out.report = self.rows.all()
        prefixes = (SSSF_CONFIG_DIR, HARNESS_DIR, MODULES_DIR, RECIPES_DIR)
        paths = {p for p in self.tree if p.startswith(prefixes)} | self.read_paths
        paths |= {
            p
            for p in self.tree
            if p.startswith(SSSF_DIR) and "/" not in p[len(SSSF_DIR) :] and p.endswith(".py")
        }
        source_paths = sorted(paths)
        return SssfConversion(
            extraction=self.out,
            settings=self.project,
            roster=roster,
            workflows=workflows,
            source_paths=source_paths,
            source_files={p: self.tree[p] for p in source_paths if p in self.tree},
        )


def extract_sssf(
    root: Path,
    base: str,
    base_sha: str,
    source: _Source,
    environ: Mapping[str, str] | None,
    *,
    detected: Detected,
    keep_local: set[tuple[ItemType, str]] | None = None,
    names: Mapping[tuple[ItemType, str], str] | None = None,
    workflows: bool = False,
    rosters: tuple[str, ...] = (),
) -> SssfConversion:
    """Convert the sssf configuration of base; see the module docstring.

    Raises ``sssf_roster_invalid`` (the roster is missing or not a roster),
    ``invalid_value``, ``conflicting_options``, ``unknown_item`` and ``name_taken``.
    """
    return _Converter(
        root,
        base,
        base_sha,
        source,
        environ,
        detected,
        set(keep_local or ()),
        dict(names or {}),
        workflows,
        rosters,
    ).run()


__all__ = ["SssfConversion", "extract_sssf"]
