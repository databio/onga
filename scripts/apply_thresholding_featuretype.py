#!/usr/bin/env python3
"""Apply the thresholding facet decomposition to the FeatureType enum.

Operation #13 (FeatureType extension). The thresholding facet
(Thresholding on TrackProvenance) — first applied to DataType compound terms
in apply_thresholding_decomposition.py — also applies to two FeatureType
compound terms in the `element_gene_linkage` subset that bake a significance
retention-cut into the term string:

  thresholded element gene links -> element gene links + thresholding:significance
  thresholded links              -> links              + thresholding:significance

`element gene links` already exists (base_exists=yes). `links` is a generic
base that does not yet exist (base_exists=no) and is minted here, mirroring the
FeatureType base-minting in apply_feature_strand_filter.py. Its sibling
`element gene links` carries no `meaning:` CURIE, so `links` gets none either.

NOTE: an earlier draft of apply_thresholding_decomposition.py wrongly concluded
these two terms did not exist. They were checked only against the DataType enum;
both are live FeatureType terms. This script corrects that omission.

Driven by the thresholding rows of mappings/facet_decomposition.tsv whose
`feature_type` column is non-empty.

The removed compound terms remain recoverable via the map plus the facet slot:
  compound term = feature_type + thresholding (thresholding -> Thresholding on
                  TrackProvenance).

Usage:
    python scripts/apply_thresholding_featuretype.py
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

# The atomic base `element gene links` must survive untouched.
PROTECTED = [
    "element gene links",
]

# Crafted atomic-base entries for the base_exists=no feature_types.
# `links` generalizes its sibling `element gene links`; no meaning CURIE (the
# sibling has none).
NEW_BASES = {
    "links": {
        "description": "Generic regulatory links associating genomic elements with target features.",
        "in_subset": ["element_gene_linkage"],
    },
}


def load_feature_thresholding_rows(path):
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
            if r.get("thresholding") and r.get("feature_type"):
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
    rows = load_feature_thresholding_rows(TSV_PATH)

    encode_terms = [r["encode_term"] for r in rows]
    missing_bases = sorted({r["feature_type"] for r in rows if r["base_exists"] == "no"})
    all_bases = sorted({r["feature_type"] for r in rows})

    if len(set(encode_terms)) != len(encode_terms):
        dupes = [t for t in encode_terms if encode_terms.count(t) > 1]
        print("ERROR: duplicate encode_terms in feature thresholding rows:", sorted(set(dupes)))
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
    pv = data["enums"]["FeatureType"]["permissible_values"]
    dt_count_before = len(data["enums"]["DataType"]["permissible_values"])

    start_count = len(pv)
    print(f"Starting FeatureType count: {start_count}")
    print(f"DataType count (must not change): {dt_count_before}")

    # Pre-flight checks.
    not_found = [t for t in encode_terms if t not in pv]
    if not_found:
        print("ERROR: encode_terms not found in FeatureType enum:", not_found)
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

    # 1. Mint missing atomic bases.
    added = []
    for base in missing_bases:
        pv[base] = make_entry(NEW_BASES[base])
        added.append(base)
        print(f"  MINT base '{base}'")

    # 2. Remove the compound FeatureType terms.
    removed = []
    for term in encode_terms:
        del pv[term]
        removed.append(term)
        print(f"  REMOVE '{term}'")

    end_count = len(pv)
    dt_count_after = len(data["enums"]["DataType"]["permissible_values"])

    # Guardrails.
    for term in encode_terms:
        assert term not in pv, f"compound term still present: {term}"
    for base in all_bases:
        assert base in pv, f"base feature_type missing after edit: {base}"
    for term in PROTECTED:
        assert term in pv, f"protected term removed: {term}"
    assert dt_count_after == dt_count_before, "DataType count changed!"

    print(f"\nWriting {SCHEMA_PATH}...")
    yaml.dump(data, SCHEMA_PATH)

    print("\n=== Summary ===")
    print(f"Starting FeatureType count: {start_count}")
    print(f"Minted ({len(added)}): {added}")
    print(f"Removed: {len(removed)} compound terms: {removed}")
    print(f"Ending FeatureType count: {end_count}")
    print(f"Check: {start_count} - {len(removed)} + {len(added)} = "
          f"{start_count - len(removed) + len(added)} (actual {end_count})")
    print(f"DataType unchanged: {dt_count_before} -> {dt_count_after}")


if __name__ == "__main__":
    main()
