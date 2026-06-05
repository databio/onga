#!/usr/bin/env python3
"""Apply the FeatureType strand + filter_status facet decomposition.

Operation #12. Extends the existing `strand` (StrandOrientation) and
`filter_status` (FilterStatus) facets — previously applied only to DataType
compound terms — to the FeatureType enum, where the same qualifiers were still
baked into compound term strings.

Driven by the rows of mappings/facet_decomposition.tsv whose `feature_type`
column is non-empty (added operation #12). Mirrors
apply_normalization_decomposition.py:

  1. Mint the atomic base feature_types that do not yet exist (base_exists=no),
     generalizing description/subset (and meaning) from a strand-specific
     compound sibling (strand/filter language stripped).
  2. Remove the compound FeatureType terms (every feature_type-row encode_term).

The removed compound terms remain recoverable via the map plus the facet slots:
  strand-row compound = feature_type + strand   (strand -> StrandOrientation
                                                  on TrackInterpretation)
  filter-row compound = feature_type + filter_status (filter_status ->
                                                  FilterStatus on TrackProvenance)

Strand rows decompose 14 compounds onto 7 bases (3 already exist:
`methylation state at CpG`, `transcription start sites`; the 5 RNA-modification
bases are minted). Filter rows decompose 3 compounds onto 3 bases (`transcribed
fragments` exists; `indels` and `SNPs` are minted).

`smoothed methylation state at CpG` is deliberately NOT touched: smoothing is a
separate axis; that term will share the `methylation state at CpG` base later.

Usage:
    python scripts/apply_feature_strand_filter.py
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

# Terms that must NOT be touched (sanity guard). The smoothing sibling shares a
# base but is a separate axis; the three bases that already exist must survive.
PROTECTED = [
    "smoothed methylation state at CpG",
    "methylation state at CpG",
    "transcription start sites",
    "transcribed fragments",
]

# Crafted atomic-base entries for the base_exists=no feature_types.
# Description generalized from a strand-specific compound sibling (strand
# language stripped); subset (and meaning) matched to the sibling.
NEW_BASES = {
    "inosine methylation state": {
        "description": "Inosine (A-to-I editing) modification.",
        "in_subset": ["rna_modification"],
    },
    "m5C methylation state": {
        "description": "5-methylcytosine (m5C) RNA modification.",
        "in_subset": ["rna_modification"],
    },
    "m6A methylation state": {
        "description": "N6-methyladenosine (m6A) modification on transcripts. m6A is the most abundant "
                       "internal mRNA modification.",
        "in_subset": ["rna_modification"],
    },
    "Nm methylation state": {
        "description": "2′-O-methylation (Nm) modification.",
        "in_subset": ["rna_modification"],
    },
    "pseudouridine methylation state": {
        "description": "Pseudouridine (Ψ) modification. Pseudouridine is the most abundant RNA modification.",
        "in_subset": ["rna_modification"],
    },
    "indels": {
        "description": "Insertion/deletion variants.",
        "meaning": "edam:data_0918",
        "in_subset": ["variant"],
    },
    "SNPs": {
        "description": "Single nucleotide polymorphisms.",
        "meaning": "edam:data_0918",
        "in_subset": ["variant"],
    },
}


def load_feature_rows(path):
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
            if r.get("feature_type"):
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
    rows = load_feature_rows(TSV_PATH)

    encode_terms = [r["encode_term"] for r in rows]
    missing_bases = sorted({r["feature_type"] for r in rows if r["base_exists"] == "no"})
    all_bases = sorted({r["feature_type"] for r in rows})

    if len(set(encode_terms)) != len(encode_terms):
        dupes = [t for t in encode_terms if encode_terms.count(t) > 1]
        print("ERROR: duplicate encode_terms in feature rows:", sorted(set(dupes)))
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
    print(f"Removed: {len(removed)} compound terms")
    print(f"Ending FeatureType count: {end_count}")
    print(f"Check: {start_count} - {len(removed)} + {len(added)} = "
          f"{start_count - len(removed) + len(added)} (actual {end_count})")
    print(f"DataType unchanged: {dt_count_before} -> {dt_count_after}")
    print(f"Protected terms intact: {len(PROTECTED)}")


if __name__ == "__main__":
    main()
