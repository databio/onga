#!/usr/bin/env python3
"""Apply the thresholding facet decomposition to file_content.yaml.

Driven by the thresholding rows of mappings/facet_decomposition.tsv (rows whose
`thresholding` column is non-empty). Mirrors apply_normalization_decomposition.py
for the retention-cut (thresholding) axis:

  1. Mint any atomic base output_types that do not yet exist (base_exists=no),
     generalizing description/subset from a source compound sibling.
  2. Remove the compound DataType terms (every thresholding-row encode_term).

The removed compound terms remain recoverable via the map plus the
TrackProvenance facet slot thresholding -> Thresholding, per the round-trip:
  compound term = output_type + thresholding.

SCOPE NOTE (verified against live file_content.yaml 2026-06-05): the working
plan also named `thresholded element gene links` and `thresholded links` (to be
faceted onto thresholding:significance, with a minted `links` base). Neither
term — nor the base `element gene links` — exists in the live DataType enum
(the `element_gene_linkage` subset currently has zero member terms). Those rows
were therefore NOT added and `links` was NOT minted. Only the two verified
compound terms are decomposed here. The `significance` permissible value is
still defined in src/thresholding.yaml as a valid (currently unused) facet
value.

The reproducibility-selection axis (conservative/optimal/representative/
pseudoreplicated IDR thresholded peaks, replicated/pseudoreplicated peaks,
representative/consensus DNase hypersensitivity sites) is deliberately NOT
faceted in this operation and is guarded as PROTECTED below.

Usage:
    python scripts/apply_thresholding_decomposition.py
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

# Terms that must NOT be touched (sanity guard). The replicate/selection-mode
# reproducibility terms and the IDR-input / ranked terms stay atomic this op.
PROTECTED = [
    "conservative IDR thresholded peaks",
    "optimal IDR thresholded peaks",
    "representative IDR thresholded peaks",
    "pseudoreplicated IDR thresholded peaks",
    "replicated peaks",
    "pseudoreplicated peaks",
    "representative DNase hypersensitivity sites",
    "consensus DNase hypersensitivity sites",
    "peaks and background as input for IDR",
    "IDR ranked peaks",
    "ranked gRNAs",
]

# Crafted atomic-base entries for any base_exists=no thresholding output_types.
# (Currently empty: both verified bases already exist.)
NEW_BASES = {}


def load_thresholding_rows(path):
    rows = []
    with open(path, newline="") as f:
        header = None
        for line in f:
            if line.startswith("#"):
                continue
            row = line.rstrip("\n").split("\t")
            if not row or row[0] == "encode_term":
                header = row
                continue
            if header is None or len(row) < len(header):
                continue
            r = dict(zip(header, row))
            if r.get("thresholding"):
                rows.append(r)
    return rows


def make_entry(spec):
    from ruamel.yaml.comments import CommentedMap
    entry = CommentedMap()
    entry["description"] = spec["description"]
    if "meaning" in spec:
        entry["meaning"] = spec["meaning"]
    entry["in_subset"] = list(spec["in_subset"])
    return entry


def main():
    rows = load_thresholding_rows(TSV_PATH)

    encode_terms = [r["encode_term"] for r in rows]
    missing_bases = sorted({r["output_type"] for r in rows if r["base_exists"] == "no"})
    all_bases = sorted({r["output_type"] for r in rows})

    if len(set(encode_terms)) != len(encode_terms):
        dupes = [t for t in encode_terms if encode_terms.count(t) > 1]
        print("ERROR: duplicate encode_terms in thresholding rows:", sorted(set(dupes)))
        sys.exit(1)

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
    for term in PROTECTED:
        if term not in pv:
            print(f"ERROR: protected term missing before edit: {term!r}")
            sys.exit(1)
        if term in encode_terms:
            print(f"ERROR: protected term appears in removal set: {term!r}")
            sys.exit(1)

    # 1. Mint missing atomic bases (none currently).
    added = []
    for base in missing_bases:
        pv[base] = make_entry(NEW_BASES[base])
        added.append(base)
        print(f"  MINT base '{base}'")

    # 2. Remove the compound thresholding terms.
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
    for term in PROTECTED:
        assert term in pv, f"PROTECTED term removed: {term}"

    print(f"\nWriting {SCHEMA_PATH}...")
    yaml.dump(data, SCHEMA_PATH)

    print("\n=== Summary ===")
    print(f"Starting count: {start_count}")
    print(f"Minted ({len(added)}): {added}")
    print(f"Removed: {len(removed)} compound terms: {removed}")
    print(f"Ending count: {end_count}")
    print(f"Check: {start_count} - {len(removed)} + {len(added)} = "
          f"{start_count - len(removed) + len(added)} (actual {end_count})")
    print(f"PROTECTED terms intact: {len(PROTECTED)}")


if __name__ == "__main__":
    main()
