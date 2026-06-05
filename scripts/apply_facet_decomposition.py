#!/usr/bin/env python3
"""Apply the strand/read_multiplicity facet decomposition to file_content.yaml.

Driven by mappings/facet_decomposition.tsv. This APPLIES the decomposition
recorded by the (additive-only) faceting step:

  1. Add the atomic base output_types that do not yet exist (base_exists=no),
     generalizing their description/subset from a source compound sibling.
  2. Remove the 32 compound DataType terms (every encode_term in the TSV).

The removed compound terms remain losslessly recoverable via the map plus the
TrackInterpretation facet slots (strand -> StrandOrientation,
read_multiplicity -> ReadMultiplicity), per the round-trip:
  compound term = output_type + strand + read_multiplicity.

Usage:
    python scripts/apply_facet_decomposition.py
"""

import csv
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

# Crafted atomic-base entries for the base_exists=no output_types. Descriptions
# are generalized from the source compound siblings (strand / read-multiplicity specific
# language stripped); subsets and EDAM meanings match the compound siblings.
NEW_BASES = {
    "end position signal": {
        "description": "Signal of read end positions.",
        "in_subset": ["signal_track"],
    },
    "normalized end position signal": {
        "description": "Normalized signal of read end positions.",
        "in_subset": ["signal_track"],
    },
    "normalized signal": {
        "description": "Depth-normalized signal track.",
        "in_subset": ["signal_track"],
    },
    "observed control profile": {
        "description": "Observed control signal profile.",
        "in_subset": ["signal_track"],
    },
    "unfiltered sparse gene count matrix": {
        "description": "Unfiltered sparse matrix of gene-level read counts.",
        "in_subset": ["count_matrix"],
        "meaning": "edam:data_3917",
    },
    "unfiltered sparse splice junction count matrix": {
        "description": "Unfiltered sparse count matrix of splice junctions.",
        "in_subset": ["count_matrix"],
        "meaning": "edam:data_3917",
    },
}


def load_tsv(path):
    rows = []
    with open(path, newline="") as f:
        for line in f:
            if line.startswith("#"):
                continue
            row = line.rstrip("\n").split("\t")
            if not row or row[0] == "encode_term":
                continue
            if len(row) < 5:
                continue
            rows.append({
                "encode_term": row[0],
                "output_type": row[1],
                "strand": row[2],
                "read_multiplicity": row[3],
                "base_exists": row[4],
            })
    return rows


def make_entry(pv, spec):
    """Build a CommentedMap entry mirroring existing permissible-value style."""
    from ruamel.yaml.comments import CommentedMap
    entry = CommentedMap()
    entry["description"] = spec["description"]
    if "meaning" in spec:
        entry["meaning"] = spec["meaning"]
    entry["in_subset"] = list(spec["in_subset"])
    return entry


def main():
    rows = load_tsv(TSV_PATH)

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

    # 1. Add missing atomic bases.
    added = []
    for base in missing_bases:
        pv[base] = make_entry(pv, NEW_BASES[base])
        added.append(base)
        print(f"  ADD base '{base}'")

    # 2. Remove the 32 compound terms.
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

    print(f"\nWriting {SCHEMA_PATH}...")
    yaml.dump(data, SCHEMA_PATH)

    print("\n=== Summary ===")
    print(f"Starting count: {start_count}")
    print(f"Added ({len(added)}): {added}")
    print(f"Removed: {len(removed)} compound terms")
    print(f"Ending count: {end_count}")
    print(f"Check: {start_count} - {len(removed)} + {len(added)} = "
          f"{start_count - len(removed) + len(added)} (actual {end_count})")


if __name__ == "__main__":
    main()
