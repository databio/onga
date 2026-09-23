"""The handler contract for applying decisions.

One handler per (kind, verdict) from `curation/verdicts.yaml`. The apply engine
(`scripts/workbench/apply.py`) looks each pending record up in `REGISTRY`, calls
`preflight` on every record first (all-or-nothing: any reason aborts the run),
then `apply` on each, and commits the staged files only when every handler
succeeded.

Handlers live in separate modules so they can be written in parallel:
`content.py` (term, enum, subset) and `schema.py` (class, slot, usage, module)
each call `register(...)` at import time. Record-only verdicts (those with
`writes: none` in verdicts.yaml: keep, keep_atomic, defer, mint_base) are
registered here as no-ops.

A handler never touches disk. It reads through `ctx.read_yaml` / `read_tsv` /
`read_text` (which see earlier staged writes in the same run) and writes by
mutating what those return (the object stays staged) or through `stage_text`.
Handler modules in this package are discovered by `load_all()`; a new module
only has to call `register(...)` at import time.
"""
import importlib
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .. import store, yamlio as _yamlio
from ..tsv import Table


class ApplyError(Exception):
    """A handler (or the engine) found, while staging, that a record cannot apply."""


@dataclass
class Effects:
    """What one applied decision did. The engine stamps `created` / `retired`
    onto the record's `applied` block and feeds `renamed` to the alias map."""
    files: list = field(default_factory=list)      # repo-relative paths touched
    created: list = field(default_factory=list)    # SIDs created
    retired: list = field(default_factory=list)    # SIDs retired
    renamed: dict = field(default_factory=dict)    # old SID -> new SID


@dataclass
class Ctx:
    """Everything a handler may use.

    root      repo root; staged paths are relative to it
    yamlio    the one YAML writer
    ids       scripts/workbench/ids.py (term id allocation and resolution)
    subjects  store.Subjects index over curation/subjects.json
    staged    {relative path: yamlio.Doc | tsv.Table | str}, the pending
              writes; nothing reaches disk until the engine commits (and only
              files whose rendered text differs from disk are written)
    """
    root: Path
    ids: Any
    subjects: Any
    yamlio: Any = _yamlio
    staged: dict = field(default_factory=dict)

    def _key(self, path):
        p = Path(path)
        return str(p.relative_to(self.root) if p.is_absolute() else p)

    def read_yaml(self, path):
        """The staged Doc for `path`, loading (and staging) it on first use."""
        key = self._key(path)
        if key not in self.staged:
            self.staged[key] = self.yamlio.load(self.root / key)
        return self.staged[key]

    def read_tsv(self, path):
        """The staged tsv.Table for `path`, loading (and staging) it on first use."""
        key = self._key(path)
        if key not in self.staged:
            self.staged[key] = Table.parse((self.root / key).read_text())
        return self.staged[key]

    def render(self, key):
        """The text the staged object for `key` would write."""
        cur = self.staged[key]
        if isinstance(cur, str):
            return cur
        if isinstance(cur, Table):
            return cur.dumps()
        return self.yamlio.dumps(cur)

    def read_text(self, path):
        key = self._key(path)
        if key not in self.staged:
            return (self.root / key).read_text()
        return self.render(key)

    def changed(self):
        """{relative path: new text} for every staged file that differs from disk."""
        out = {}
        for key in sorted(self.staged):
            text = self.render(key)
            p = self.root / key
            if not p.exists() or p.read_text() != text:
                out[key] = text
        return out

    def stage_text(self, path, text):
        self.staged[self._key(path)] = text


class Handler(Protocol):
    kind: str
    verdict: str

    def preflight(self, rec: dict, ctx: Ctx) -> list:
        """Every reason `rec` cannot be applied; [] if it can."""

    def apply(self, rec: dict, ctx: Ctx) -> Effects:
        """Stage the writes in `ctx`; return what changed."""


REGISTRY: dict = {}


def register(handler):
    """Add `handler` (an instance with kind/verdict/preflight/apply)."""
    key = (handler.kind, handler.verdict)
    if key in REGISTRY:
        raise ValueError(f"duplicate handler for {key}")
    REGISTRY[key] = handler
    return handler


class RecordOnly:
    """No-op handler for verdicts that only record a judgment."""

    def __init__(self, kind, verdict):
        self.kind = kind
        self.verdict = verdict

    def preflight(self, rec, ctx):
        return []

    def apply(self, rec, ctx):
        return Effects()


def missing(verdicts=None):
    """(kind, verdict) pairs in verdicts.yaml with no registered handler."""
    verdicts = verdicts or store.load_verdicts()
    return sorted((k, v) for k, vs in verdicts.items() for v in vs if (k, v) not in REGISTRY)


def load_all():
    """Import every handler module in this package (each registers itself)."""
    for info in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{info.name}")
    return REGISTRY


for _kind, _vs in store.load_verdicts().items():
    for _verdict, _entry in _vs.items():
        if _entry["writes"] == "none":
            register(RecordOnly(_kind, _verdict))
