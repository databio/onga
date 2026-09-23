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

A handler never touches disk. It reads through `ctx.read_*` (which sees earlier
staged writes in the same run) and writes through `ctx.stage_*`.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .. import store, yamlio as _yamlio


@dataclass
class Effects:
    """What one applied decision did. The engine stamps `created` / `retired`
    onto the record's `applied` block and feeds `renamed` to the alias map."""
    files: list = field(default_factory=list)      # repo-relative paths touched
    created: list = field(default_factory=list)    # SIDs created
    retired: list = field(default_factory=list)    # SIDs retired
    renamed: dict = field(default_factory=dict)    # old SID -> new SID
    ledger: list = field(default_factory=list)     # curation/term_ids.tsv row updates


@dataclass
class Ctx:
    """Everything a handler may use.

    root      repo root; staged paths are relative to it
    yamlio    the one YAML writer
    ids       scripts/workbench/ids.py (term id allocation and resolution)
    subjects  store.Subjects index over curation/subjects.json
    staged    {relative path: yamlio.Doc | str}, the pending writes; nothing
              reaches disk until the engine commits
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

    def read_text(self, path):
        key = self._key(path)
        cur = self.staged.get(key)
        if cur is None:
            return (self.root / key).read_text()
        return cur if isinstance(cur, str) else self.yamlio.dumps(cur)

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


for _kind, _vs in store.load_verdicts().items():
    for _verdict, _entry in _vs.items():
        if _entry["writes"] == "none":
            register(RecordOnly(_kind, _verdict))
