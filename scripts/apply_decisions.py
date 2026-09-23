#!/usr/bin/env python3
"""Apply pending decisions from curation/decisions.yaml to the schema.

All or nothing: every selected record is preflighted and staged in memory
first; any objection aborts the whole run with the full list, and a failure
after writing (projection, registry, `make regen`, `make test`) restores every
file. See scripts/workbench/apply.py for the steps.

  python scripts/apply_decisions.py                      # apply every pending terminal record
  python scripts/apply_decisions.py --ids DEC-0003 DEC-0007
  python scripts/apply_decisions.py --dry-run            # print the diff it would make
  python scripts/apply_decisions.py --dry-run --emit curation/pending.json

`--emit` writes the staged diff plus each decision's effects (created, retired,
renamed SIDs) as JSON, for the site's Pending page.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workbench import apply  # noqa: E402


def emit(result, path):
    data = {
        "_generated_by": "scripts/apply_decisions.py --dry-run --emit (make pending); do not edit",
        "ok": result.ok,
        "decisions": [
            {"id": r["id"], "subject": r["subject"], "verdict": r["verdict"],
             **({"created": e.created, "retired": e.retired, "renamed": e.renamed}
                if (e := result.effects.get(r["id"])) else {})}
            for r in result.records],
        "files": [{"path": p, "diff": d} for p, d in sorted(result.diff.items())],
        "errors": result.errors,
    }
    Path(path).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="stage and print the diff; write nothing")
    ap.add_argument("--ids", nargs="+", metavar="DEC-NNNN", help="apply only these records")
    ap.add_argument("--emit", metavar="PATH", help="write the staged diff and effects as JSON")
    args = ap.parse_args()
    result = apply.run(want=args.ids, dry_run=args.dry_run)
    if args.emit:
        emit(result, args.emit)
    if not result.ok:
        print(f"APPLY REFUSED ({sum(map(len, result.errors.values()))} problem(s)); nothing applied:")
        for rid, errs in sorted(result.errors.items()):
            for e in errs:
                print(f"  {rid}: {e}")
        sys.exit(1)
    if args.dry_run:
        sys.stdout.write("".join(d for _, d in sorted(result.diff.items())))
        return
    for line in result.log:
        print(line)
    if result.records:
        print(f"applied {len(result.records)} decision(s): "
              + ", ".join(f"{r['id']} ({r['verdict']})" for r in result.records))


if __name__ == "__main__":
    main()
