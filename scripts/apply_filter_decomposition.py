#!/usr/bin/env python3
"""Apply the filter_status facet decomposition to file_content.yaml.

Driven by the filter rows of mappings/facet_decomposition.tsv (rows whose
filter_status column is non-empty). Mirrors apply_facet_decomposition.py (the
strand/read_multiplicity step) for the filter axis:

  1. Add the atomic base output_types that do not yet exist (base_exists=no),
     generalizing their description/subset from a source compound sibling.
  2. Remove the compound DataType terms (every filter-row encode_term).

The removed compound terms remain losslessly recoverable via the map plus the
TrackInterpretation facet slot filter_status -> FilterStatus, per the
round-trip:
  compound term = output_type + filter_status.

`rejected reads` and `filtered regions` are deliberately NOT in the map: they
are the discarded/excluded complement set (an identity, not reads/regions +
filter status), so they stay as atomic leaves.

Usage:
    python scripts/apply_filter_decomposition.py
"""

import sys
from pathlib import Path

try:
    from ruamel.yaml import YAML
except ImportError:
    print("ERROR: ruamel.yaml is required. Install with: pip install ruamel.yaml")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "src" / "file_content.yaml"
TSV_PATH = ROOT / "mappings" / "facet_decomposition.tsv"

# Leaves that must NOT be touched (sanity guard).
PROTECTED_LEAVES = ["rejected reads", "filtered regions"]

# Crafted atomic-base entries for the base_exists=no filter output_types.
# Descriptions are generalized from the source compound siblings (filter-status
# language stripped); subsets and EDAM meanings match the compound siblings.
NEW_BASES = {
    "modified peptide quantification": {
        "description": "Quantification of post-translationally modified peptides.",
        "in_subset": ["quantification"],
    },
    "sparse splice junction count matrix": {
        "description": "Sparse count matrix of splice junctions.",
        "in_subset": ["count_matrix"],
        "meaning": "edam:data_3917",
    },
}


def load_filter_rows(path):
    rows = []
    with open(path, newline="") as f:
        for line in f:
            if line.startswith("#"):
                continue
            row = line.rstrip("\n").split("\t")
            if not row or row[0] == "encode_term":
                continue
            if len(row) < 6:
                continue
            r = {
                "encode_term": row[0],
                "output_type": row[1],
                "strand": row[2],
                "read_multiplicity": row[3],
                "filter_status": row[4],
                "base_exists": row[5],
            }
            # Only the filter rows.
            if r["filter_status"]:
                rows.append(r)
    return rows


def make_entry(spec):
    """Build a CommentedMap entry mirroring existing permissible-value style."""
    from ruamel.yaml.comments import CommentedMap
    entry = CommentedMap()
    entry["description"] = spec["description"]
    if "meaning" in spec:
        entry["meaning"] = spec["meaning"]
    entry["in_subset"] = list(spec["in_subset"])
    return entry


def main():
    rows = load_filter_rows(TSV_PATH)

    encode_terms = [r["encode_term"] for r in rows]
    missing_bases = sorted({r["output_type"] for r in rows if r["base_exists"] == "no"})
    all_bases = sorted({r["output_type"] for r in rows})

    # Sanity: every missing base must have a crafted spec.
    unknown = [b for b in missing_bases if b not in NEW_BASES]
    if unknown:
        print("ERROR: base_exists=no terms without a crafted spec:", unknown)
        sys.exit(1)

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 120

    print(f"Loading {SCHEMA_PATH}...")
    data = yaml.load(SCHEMA_PATH)
    pv = data["enums"]["DataType"]["permissible_values"]

    start_count = len(pv)
    print(f"Starting DataType count: {start_count}")

    # Pre-flight checks.
    not_found = [t for t in encode_terms if t not in pv]
    if not_found:
        print("ERROR: encode_terms not found in DataType enum:", not_found)
        sys.exit(1)
    for b in missing_bases:
        if b in pv:
            print(f"ERROR: base flagged base_exists=no already in enum: {b!r}")
            sys.exit(1)
    for b in all_bases:
        if b not in missing_bases and b not in pv:
            print(f"ERROR: base flagged base_exists=yes not in enum: {b!r}")
            sys.exit(1)
    for leaf in PROTECTED_LEAVES:
        if leaf not in pv:
            print(f"ERROR: protected leaf missing before edit: {leaf!r}")
            sys.exit(1)
        if leaf in encode_terms:
            print(f"ERROR: protected leaf appears in removal set: {leaf!r}")
            sys.exit(1)

    # 1. Add missing atomic bases.
    added = []
    for base in missing_bases:
        pv[base] = make_entry(NEW_BASES[base])
        added.append(base)
        print(f"  ADD base '{base}'")

    # 2. Remove the compound filter terms.
    removed = []
    for term in encode_terms:
        del pv[term]
        removed.append(term)
        print(f"  REMOVE '{term}'")

    end_count = len(pv)

    # Guardrails.
    for term in encode_terms:
        assert term not in pv, f"compound term still present: {term}"
    for base in all_bases:
        assert base in pv, f"base output_type missing after edit: {base}"
    for leaf in PROTECTED_LEAVES:
        assert leaf in pv, f"protected leaf removed: {leaf}"

    print(f"\nWriting {SCHEMA_PATH}...")
    yaml.dump(data, SCHEMA_PATH)

    print("\n=== Summary ===")
    print(f"Starting count: {start_count}")
    print(f"Added ({len(added)}): {added}")
    print(f"Removed: {len(removed)} compound terms")
    print(f"Ending count: {end_count}")
    print(f"Check: {start_count} - {len(removed)} + {len(added)} = "
          f"{start_count - len(removed) + len(added)} (actual {end_count})")
    print(f"Protected leaves intact: {PROTECTED_LEAVES}")


if __name__ == "__main__":
    main()
