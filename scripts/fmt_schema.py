#!/usr/bin/env python3
"""Normalize every src/*.yaml to the shared writer's output (scripts/workbench/yamlio.py).

Each file must be a fixed point of yamlio load + dump, so any later
programmatic edit yields a diff containing only its own change.

Usage:
    python scripts/fmt_schema.py           # rewrite files that are not normalized
    python scripts/fmt_schema.py --check   # write nothing; exit 1 on any difference
"""
import argparse
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from workbench import yamlio  # noqa: E402

SKIP = {"linkml_lint_config.yaml"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="write nothing; exit non-zero if any file would change")
    args = ap.parse_args()

    changed = []
    for path in sorted((ROOT / "src").glob("*.yaml")):
        if path.name in SKIP:
            continue
        before = path.read_text()
        doc = yamlio.load(path)
        after = yamlio.dumps(doc)
        if after == before:
            continue
        changed.append(path)
        rel = path.relative_to(ROOT)
        if args.check:
            sys.stdout.writelines(difflib.unified_diff(
                before.splitlines(True), after.splitlines(True),
                f"a/{rel}", f"b/{rel}", n=1))
        else:
            yamlio.dump(doc, path)
            print(f"normalized {rel}")

    if args.check:
        if changed:
            print(f"fmt-check FAILED: {len(changed)} file(s) not normalized; "
                  f"run `make fmt`")
            sys.exit(1)
        print("fmt-check OK: every src/*.yaml is a yamlio fixed point")


if __name__ == "__main__":
    main()
