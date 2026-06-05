#!/usr/bin/env python3
"""Apply the normalization (scaling) facet decomposition to file_content.yaml.

Driven by the normalization rows of mappings/facet_decomposition.tsv (rows whose
normalization column is non-empty). Mirrors apply_filter_decomposition.py and
apply_facet_decomposition.py for the scaling axis:

  1. Mint the atomic base output_types that do not yet exist (base_exists=no),
     generalizing their description/subset from a source compound sibling. Here
     that is exactly one base: `signals matrix` (count_matrix subset).
  2. Remove the compound DataType terms (every normalization-row encode_term),
     including the three SYNONYM-MERGE terms that collapse many-to-one onto
     signal + depth_normalized.

The removed compound terms remain recoverable via the map plus the
TrackProvenance facet slot normalization -> Normalization, per the round-trip:
  compound term = output_type + normalization.
The ENCODE->ONGA direction is well-defined; for the three merged synonyms
(`normalized signal`, `read-depth normalized signal`, `raw normalized signal`)
the ONGA->ENCODE direction is intentionally ambiguous (a deliberate non-1:1
collapse the curator approved).

Statistic-type output_types (fold change over control, control normalized
signal, signal p-value, enrichment, z scores matrix, fold over change matrix)
and smoothing terms (wavelet-smoothed signal, summed densities signal) are NOT
touched: they change what the values mean (or are a distinct transform), not the
scaling, so they stay as output_types. Also untouched: raw data, raw imaging
signal, bare signal, and the profile bases.

Usage:
    python scripts/apply_normalization_decomposition.py
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

# Terms that must NOT be touched (sanity guard). Statistic-type output_types and
# smoothing terms (distinct output_types, not scaling) plus the bare/profile
# bases and raw-data leaves.
PROTECTED = [
    "fold change over control",
    "control normalized signal",
    "signal p-value",
    "enrichment",
    "z scores matrix",
    "fold over change matrix",
    "wavelet-smoothed signal",
    "summed densities signal",
    "raw data",
    "raw imaging signal",
    "signal",
    "observed signal profile",
    "predicted signal profile",
    "predicted bias profile",
    "bias-corrected predicted signal profile",
    "end position signal",
]

# Crafted atomic-base entries for the base_exists=no normalization output_types.
# Description generalized from the compound sibling (scaling language stripped);
# subset matched to the sibling.
NEW_BASES = {
    "signals matrix": {
        "description": "Matrix of signal values across features and samples.",
        "in_subset": ["count_matrix"],
    },
}


def load_normalization_rows(path):
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
            if r.get("normalization"):
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
    rows = load_normalization_rows(TSV_PATH)

    # encode_terms may repeat-as-distinct strings but are unique here; bases may
    # repeat (synonym merge -> several encode_terms share base `signal`).
    encode_terms = [r["encode_term"] for r in rows]
    missing_bases = sorted({r["output_type"] for r in rows if r["base_exists"] == "no"})
    all_bases = sorted({r["output_type"] for r in rows})

    if len(set(encode_terms)) != len(encode_terms):
        dupes = [t for t in encode_terms if encode_terms.count(t) > 1]
        print("ERROR: duplicate encode_terms in normalization rows:", sorted(set(dupes)))
        sys.exit(1)

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
    for term in PROTECTED:
        if term not in pv:
            print(f"ERROR: protected term missing before edit: {term!r}")
            sys.exit(1)
        if term in encode_terms:
            print(f"ERROR: protected term appears in removal set: {term!r}")
            sys.exit(1)

    # 1. Mint missing atomic bases (only `signals matrix`).
    added = []
    for base in missing_bases:
        pv[base] = make_entry(NEW_BASES[base])
        added.append(base)
        print(f"  MINT base '{base}'")

    # 2. Remove the compound normalization terms (incl. the 3 merged synonyms).
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
        assert term in pv, f"protected term removed: {term}"

    print(f"\nWriting {SCHEMA_PATH}...")
    yaml.dump(data, SCHEMA_PATH)

    print("\n=== Summary ===")
    print(f"Starting count: {start_count}")
    print(f"Minted ({len(added)}): {added}")
    print(f"Removed: {len(removed)} compound terms")
    print(f"Ending count: {end_count}")
    print(f"Check: {start_count} - {len(removed)} + {len(added)} = "
          f"{start_count - len(removed) + len(added)} (actual {end_count})")
    print(f"Protected terms intact: {len(PROTECTED)}")


if __name__ == "__main__":
    main()
