"""The apply engine: turn pending decisions into schema edits, all or nothing.

    result = apply.run(ids=None, dry_run=False)

1. Select `pending` records with a terminal verdict (optionally only `ids`).
2. Recompute every subject hash from `src/` + `mappings/` and validate each
   record (`store.validate`); a record whose `subject_hashes` no longer match
   is refused as stale.
3. Order the records: renames, then adds, then everything else, then merges,
   then deletes, then facets; within that, a record that references another
   record's subject in its `operation` runs after it. A cycle aborts.
4. Stage: call each handler's `preflight` against the state staged so far and,
   if it has no objection, its `apply`. Any objection from any record aborts
   the run with the full list; nothing has touched disk yet.
5. Dry run: return the unified diff of every staged file. Stop.
6. Otherwise snapshot every file the run can touch (`SNAPSHOT`), write the
   staged files, re-project mappings (`project_mappings.py`), rebuild the
   registry (`curation_subjects.py`), stamp each record (`status: applied`,
   `applied.on`, `subject_hashes_after`, `created`, `retired`, `renamed`), then
   `make regen` and `make test`. Any failure restores the snapshot.

Handlers are looked up in `handlers.REGISTRY` by (kind, verdict); every module
in `scripts/workbench/handlers/` registers its own at import time.
"""
import datetime
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import handlers, ids, store, subjects as registry, yamlio
from .handlers import ApplyError

ROOT = store.ROOT
PY = sys.executable
# Everything an apply (including `make regen`) may write.
SNAPSHOT = ("src", "mappings", "curation", "examples", "proposals", "DECISIONS.md",
            "site/public/api")

RANK_FIRST = {"rename": 0, "rename_enum": 0, "rename_class": 0, "rename_slot": 0,
              "rename_subset": 0,
              "add_term": 1, "add_slot": 1, "add_rule": 1, "set_slot_usage": 1}
RANK_LAST = {"merge": 3, "merge_subset": 3,
             "delete": 4, "delete_enum": 4, "delete_class": 4, "delete_slot": 4,
             "delete_subset": 4, "drop_slot": 4, "drop_usage": 4, "drop_rule": 4,
             "facet": 5}


def rank(verdict):
    return RANK_FIRST.get(verdict, RANK_LAST.get(verdict, 2))


@dataclass
class Result:
    ok: bool
    records: list = field(default_factory=list)      # applied (or would-apply) records, in order
    effects: dict = field(default_factory=dict)      # id -> handlers.Effects
    errors: dict = field(default_factory=dict)       # id (or "run") -> [reason]
    diff: dict = field(default_factory=dict)         # path -> unified diff text
    log: list = field(default_factory=list)


def fresh_subjects():
    """A store.Subjects index over the registry as `src/` is right now."""
    records, _ = registry.build()
    return store.Subjects({"schema_fingerprint": registry.fingerprint(records),
                           "subjects": records})


def order(recs, subjects, verdicts):
    """Records sorted by rank, id, and operation references. Raises ApplyError on a cycle."""
    by_subject = {}
    for r in recs:
        by_subject.setdefault(r["subject"], []).append(r["id"])
    deps = {r["id"]: set() for r in recs}
    for r in recs:
        kind = subjects.get(r["subject"])["kind"]
        _, refs = store.check_operation(r["verdict"], verdicts[kind][r["verdict"]],
                                        r.get("operation"), subjects)
        for sid in refs:
            deps[r["id"]] |= {q for q in by_subject.get(sid, []) if q != r["id"]}
    key = {r["id"]: (rank(r["verdict"]), r["id"]) for r in recs}
    done, out = set(), []
    while len(out) < len(recs):
        ready = sorted((rid for rid in deps if rid not in done and deps[rid] <= done),
                       key=key.get)
        if not ready:
            cyc = sorted(rid for rid in deps if rid not in done)
            raise ApplyError(f"decisions depend on each other in a cycle: {', '.join(cyc)}")
        done.add(ready[0])
        out.append(ready[0])
    idx = {r["id"]: r for r in recs}
    return [idx[i] for i in out]


def select(doc, verdicts, subjects, want=None):
    recs, errors = [], {}
    known = {r["id"] for r in doc.data["decisions"]}
    for rid in want or ():
        if rid not in known:
            errors[rid] = [f"no decision {rid}"]
    for r in doc.data["decisions"]:
        r = store.to_plain(r)
        if want and r["id"] not in want:
            continue
        if r["status"] != "pending":
            if want:
                errors[r["id"]] = [f"{r['id']} is {r['status']}, not pending"]
            continue
        subj = subjects.get(r["subject"])
        kind = subj["kind"] if subj else None
        entry = verdicts.get(kind, {}).get(r["verdict"])
        if entry is not None and not entry["terminal"]:
            continue
        recs.append(r)
    return recs, errors


def validate(recs, subjects, verdicts):
    errors = {}
    for r in recs:
        rec = dict(r)
        if isinstance(rec.get("decided_on"), str):
            rec["decided_on"] = datetime.date.fromisoformat(rec["decided_on"])
        try:
            store.validate(rec, subjects, verdicts, check_hashes=False)
        except store.StoreError as e:
            errors[r["id"]] = e.errors
            continue
        stale = [f"{sid} changed since the decision was recorded"
                 for sid, h in (r.get("subject_hashes") or {}).items()
                 if subjects.get(sid) and subjects.get(sid)["hash"] != h]
        if stale:
            errors[r["id"]] = stale
        elif (subjects.get(r["subject"])["kind"], r["verdict"]) not in handlers.REGISTRY:
            errors[r["id"]] = [f"no handler for {subjects.get(r['subject'])['kind']} "
                               f"{r['verdict']} yet"]
    return errors


def stage(recs, subjects, root=ROOT):
    """(ctx, effects, errors) after preflight + apply of every record in order."""
    ctx = handlers.Ctx(root=root, ids=ids, subjects=subjects)
    effects, errors = {}, {}
    for r in recs:
        h = handlers.REGISTRY[(subjects.get(r["subject"])["kind"], r["verdict"])]
        problems = h.preflight(r, ctx)
        if problems:
            errors[r["id"]] = problems
            continue
        try:
            effects[r["id"]] = h.apply(r, ctx)
        except ApplyError as e:
            errors[r["id"]] = [str(e)]
    return ctx, effects, errors


def diffs(changed, root=ROOT):
    out = {}
    for path, text in changed.items():
        p = root / path
        before = p.read_text() if p.exists() else ""
        out[path] = "".join(difflib.unified_diff(
            before.splitlines(True), text.splitlines(True), f"a/{path}", f"b/{path}"))
    return out


def plan(want=None, root=ROOT):
    """Everything up to (and including) staging. Returns (Result, ctx or None)."""
    verdicts = store.load_verdicts()
    handlers.load_all()
    try:
        subjects = fresh_subjects()
    except registry.RegistryError as e:
        return Result(False, errors={"run": [f"subject registry: {e}"]}), None
    doc = store.load()
    recs, errors = select(doc, verdicts, subjects, want)
    errors.update(validate([r for r in recs if r["id"] not in errors], subjects, verdicts))
    if errors:
        return Result(False, errors=errors), None
    try:
        recs = order(recs, subjects, verdicts)
    except ApplyError as e:
        return Result(False, errors={"run": [str(e)]}), None
    ctx, effects, errors = stage(recs, subjects, root)
    if errors:
        return Result(False, records=recs, errors=errors), None
    return Result(True, records=recs, effects=effects, diff=diffs(ctx.changed(), root)), ctx


# ---------------------------------------------------------------- commit

def _snapshot(root, tmp):
    for rel in SNAPSHOT:
        src = root / rel
        if src.is_dir():
            shutil.copytree(src, tmp / rel, symlinks=True)
        elif src.exists():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tmp / rel)


def _restore(root, tmp):
    for rel in SNAPSHOT:
        dst, saved = root / rel, tmp / rel
        if dst.is_dir():
            shutil.rmtree(dst)
        elif dst.exists():
            dst.unlink()
        if saved.is_dir():
            shutil.copytree(saved, dst, symlinks=True)
        elif saved.exists():
            shutil.copy2(saved, dst)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _run(cmd, root, log):
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    log.append(f"$ {' '.join(map(str, cmd))} -> exit {proc.returncode}")
    if proc.returncode:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-40:]
        raise ApplyError(f"`{' '.join(map(str, cmd))}` failed:\n" + "\n".join(tail))


def _stamp(result, root):
    """Mark every applied record, with post-apply hashes from the new registry."""
    after = json.loads((root / "curation" / "subjects.json").read_text())["subjects"]
    doc = store.load()
    today = datetime.date.today()
    by_id = {r["id"]: r for r in doc.data["decisions"]}
    for r in result.records:
        eff = result.effects[r["id"]]
        affected = [r["subject"], *(r.get("also_affects") or []), *eff.created]
        affected = [eff.renamed.get(s, s) for s in affected]
        hashes = {s: after[s]["hash"] for s in dict.fromkeys(affected) if s in after}
        rec = by_id[r["id"]]
        rec["status"] = "applied"
        rec["applied"] = store._to_yaml({
            "on": datetime.date.fromordinal(today.toordinal()),  # own object: no YAML anchor "subject_hashes_after": hashes,
            "created": list(eff.created), "retired": list(eff.retired),
            **({"renamed": dict(eff.renamed)} if eff.renamed else {}),
        })
    yamlio.dump(doc, store.STORE)


def run(want=None, dry_run=False, root=ROOT):
    result, ctx = plan(want, root)
    if not result.ok or dry_run or not result.records:
        return result
    with tempfile.TemporaryDirectory(prefix="onga-apply-") as tmp:
        tmp = Path(tmp)
        _snapshot(root, tmp)
        try:
            for path, text in ctx.changed().items():
                _write(root / path, text)
            _run([PY, "scripts/project_mappings.py"], root, result.log)
            _run([PY, "scripts/curation_subjects.py"], root, result.log)
            _stamp(result, root)
            _run(["make", "regen"], root, result.log)
            _run(["make", "test"], root, result.log)
        except (ApplyError, OSError, registry.RegistryError) as e:
            _restore(root, tmp)
            result.ok = False
            result.errors["run"] = [str(e), "all files restored; nothing applied"]
    return result
