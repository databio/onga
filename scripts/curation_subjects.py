#!/usr/bin/env python3
"""Generate the subject registry: curation/subjects.json and curation/term_crosswalk.json.

subjects.json holds one record per reviewable subject (term, enum, class, slot,
usage, subset, module), keyed by SID, with its authored payload and a sha256
hash of it, plus a `schema_fingerprint` over all `sid:hash` lines and the
per-kind `counts`. The counts are asserted against a separate parse of `src/`.

term_crosswalk.json maps every label a term ever had (live, former, retired)
and every legacy reference form (the old gen-owl IRI
`https://databio.org/onga/<Enum>#<percent-encoded label>` and the old
`onga:<underscored label>` CURIE) to its term id. It is a lookup table for our
own tools, not a compatibility layer.

Both files are generated and tracked; never hand-edit them.

Usage:
    python scripts/curation_subjects.py           # write both files
    python scripts/curation_subjects.py --check   # write nothing; exit 1 if stale
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workbench import subjects  # noqa: E402

CURATION = subjects.ROOT / "curation"
SUBJECTS = CURATION / "subjects.json"
CROSSWALK = CURATION / "term_crosswalk.json"
GENERATED_BY = "scripts/curation_subjects.py (make subjects); do not edit"


def render():
    try:
        records, crosswalk = subjects.build()
    except subjects.RegistryError as e:
        sys.exit(f"SUBJECT REGISTRY FAILED: {e}")
    counts = subjects.counts(records)
    live = subjects.live_counts()
    got = {k: counts[k] for k in live}
    if got != live:
        sys.exit(f"SUBJECT REGISTRY FAILED: counts {got} disagree with src/ {live}")
    doc = {"_generated_by": GENERATED_BY,
           "schema_fingerprint": subjects.fingerprint(records),
           "counts": counts,
           "subjects": records}
    xw = {"_generated_by": GENERATED_BY, **crosswalk}
    dump = lambda d: json.dumps(d, indent=1, ensure_ascii=False, default=str) + "\n"  # noqa: E731
    return {SUBJECTS: dump(doc), CROSSWALK: dump(xw)}, counts


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="write nothing; exit non-zero if a generated file is stale")
    args = ap.parse_args()
    files, counts = render()
    line = " ".join(f"{k}={v}" for k, v in counts.items())
    stale = [p for p, text in files.items()
             if not p.exists() or p.read_text() != text]
    if args.check:
        if stale:
            rel = ", ".join(str(p.relative_to(subjects.ROOT)) for p in stale)
            print(f"subjects check FAILED: {rel} stale; run `make subjects`")
            sys.exit(1)
        print(f"subjects OK: {line}")
        return
    CURATION.mkdir(exist_ok=True)
    for p in stale:
        p.write_text(files[p])
    print(line)


if __name__ == "__main__":
    main()
