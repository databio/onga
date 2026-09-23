"""Opaque, permanent ONGA term ids (`ONGA_NNNNNNN`).

Every permissible value in every enum carries its id as `meaning: onga:ONGA_NNNNNNN`,
so the generated OWL / JSON-LD IRI is `https://databio.org/onga/ONGA_NNNNNNN`.
The label (the permissible-value key) may change; the id never does, and an id
is never reused.

The id is written with the lowercase `onga:` prefix on purpose. LinkML matches
prefixes without regard to case, so an `ONGA:` prefix collides with `onga:` and
silently mints the wrong IRI.

`curation/term_ids.tsv` is the ledger: one row per id ever minted. It is the
allocation authority (next id = max + 1) and the only home of retired ids and
former labels. For live rows the enum and label are blank, because `src/` holds
them.

Stdlib + pyyaml only, so `scripts/check_roundtrip.py` can use it.
"""
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
LEDGER = ROOT / "curation" / "term_ids.tsv"

ONGA_BASE = "https://databio.org/onga/"
ID_RE = re.compile(r"^ONGA_\d{7}$")
MEANING_RE = re.compile(r"^onga:ONGA_\d{7}$")
LEDGER_COLUMNS = ("id", "status", "enum", "label", "replaced_by", "former_labels", "decision")
STATUSES = ("live", "merged", "deleted", "faceted")

LEDGER_HEADER = """\
# ONGA term-id ledger. One row per id ever minted; ids are never reused.
#
# The allocation authority for ONGA_NNNNNNN term ids (next id = max + 1) and the
# only home of retired ids and former labels. Read and written through
# scripts/workbench/ids.py.
#
# Columns:
#   id             ONGA_NNNNNNN. On the permissible value as `meaning: onga:<id>`.
#   status         live | merged | deleted | faceted
#   enum           blank for live rows (src/ holds it); the last enum for retired rows
#   label          blank for live rows (src/ holds it); the last label for retired rows
#   replaced_by    for merged / faceted rows, the id(s) that absorbed it (|-joined)
#   former_labels  labels this id carried before a rename (|-joined)
#   decision       the DEC-NNNN or DECISIONS.md operation that set the status
"""


@dataclass(frozen=True)
class Term:
    id: str | None     # ONGA_NNNNNNN, or None if the value has no valid meaning
    module: str        # module name (src/<module>.yaml)
    enum: str
    label: str


def enum_modules():
    """Module names in `src/onga.yaml` import order (the mint order)."""
    root = yaml.safe_load(open(SRC / "onga.yaml"))
    return [m for m in root.get("imports", []) if not m.startswith("linkml")]


def schema_terms():
    """Every permissible value in `src/`, in import / enum / value order."""
    out = []
    for mod in enum_modules():
        d = yaml.safe_load(open(SRC / f"{mod}.yaml")) or {}
        for enum_name, enum_def in (d.get("enums") or {}).items():
            for label, pv in ((enum_def or {}).get("permissible_values") or {}).items():
                meaning = str((pv or {}).get("meaning") or "")
                tid = meaning.split(":", 1)[1] if MEANING_RE.match(meaning) else None
                out.append(Term(tid, mod, enum_name, label))
    return out


def read_ledger():
    if not LEDGER.exists():
        return []
    with open(LEDGER) as fh:
        return list(csv.DictReader(
            (line for line in fh if not line.startswith("#")), delimiter="\t"))


def write_ledger(rows):
    rows = sorted(rows, key=lambda r: r["id"])
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "w", newline="") as fh:
        fh.write(LEDGER_HEADER)
        w = csv.DictWriter(fh, LEDGER_COLUMNS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") or "" for k in LEDGER_COLUMNS})


def live_ids():
    """The ids the ledger records as live."""
    return {r["id"] for r in read_ledger() if r["status"] == "live"}


def allocate(count=1):
    """Mint `count` new ids (max + 1 onward), record them as live, return them."""
    rows = read_ledger()
    top = max((int(r["id"].split("_")[1]) for r in rows), default=0)
    new = [f"ONGA_{top + i:07d}" for i in range(1, count + 1)]
    write_ledger(rows + [{"id": i, "status": "live"} for i in new])
    return new


def resolve_label(label, enum=None):
    """Id for a live label (or a former label in the ledger); None if unknown.

    Raises ValueError if the label is ambiguous across enums and `enum` is not given.
    """
    hits = {t.id for t in schema_terms()
            if t.label == label and (enum is None or t.enum == enum)}
    if not hits:
        hits = {r["id"] for r in read_ledger()
                if label in (r.get("former_labels") or "").split("|")
                or (r["status"] != "live" and r.get("label") == label
                    and (enum is None or r.get("enum") == enum))}
    hits.discard(None)
    if len(hits) > 1:
        raise ValueError(f"label {label!r} is ambiguous: {sorted(hits)}")
    return next(iter(hits), None)


def resolve_legacy(ref):
    """Id for any term reference form: `onga:ONGA_…`, its IRI, the old
    `onga:<underscored label>` CURIE and its IRI, or the old gen-owl IRI
    `https://databio.org/onga/<Enum>#<percent-encoded label>`. None if unknown."""
    ref = str(ref)
    if ref.startswith("onga:"):
        local = ref[len("onga:"):]
    elif ref.startswith(ONGA_BASE):
        local = ref[len(ONGA_BASE):]
    else:
        return None
    if ID_RE.match(local):
        return local
    if "#" in local:
        enum, label = local.split("#", 1)
        return resolve_label(unquote(label), enum)
    return resolve_label(local.replace("_", " "))
