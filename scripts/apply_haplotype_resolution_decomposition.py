#!/usr/bin/env python3
"""Apply the haplotype-resolution (CONTENT) facet decomposition to file_content.yaml.

Operation #17. Driven by the haplotype_resolution rows of
mappings/facet_decomposition.tsv. Mirrors the prior facet-apply scripts, but this
is a CONTENT facet (the second intrinsic-content facet after strand): the
`haplotype_resolution` slot is homed on TrackInterpretation, not TrackProvenance,
because it answers *what the values represent* (allele-resolved vs
haplotype-partitioned vs phased), not an operation applied to the data.

This script reads the TSV by HEADER NAME (robust to column insertion) to derive
the removal set and the bases, then:

  1. Mint the 2 atomic bases that do not yet exist (base_exists=no):
       DataType:    `nuclease cleavage corrected frequency`
                    (in_subset chromatin_accessibility, matching its sibling
                    `nuclease cleavage frequency`; retains the deferred
                    `corrected` bias-correction axis baked in; no meaning)
       FeatureType: `mapping`
                    (in_subset haplotype; residual of `phased mapping`; no meaning)
  2. Remove the 7 compound terms from the CORRECT enum:
       DataType (5): haplotype-specific alignments,
                     haplotype-specific contact matrix,
                     allele-specific contact matrix,
                     haplotype-specific nuclease cleavage frequency,
                     haplotype-specific nuclease cleavage corrected frequency
       FeatureType (2): phased variant calls, phased mapping

The removed compound terms remain recoverable via the map plus the
TrackInterpretation facet slot haplotype_resolution -> HaplotypeResolution:
  compound term = output_type/feature_type + haplotype_resolution (+ other facets).

DELIBERATELY KEPT ATOMIC (guarded PROTECTED, confirmed intact after the run):
  - `diploid personal genome alignments` (DataType) — reference-ploidy, not
    resolution.
  - `allele-specific variants` (FeatureType) — the allelic-imbalance sense, a
    different sense of "allele-specific".
  - `maternal/paternal variant calls`, `maternal/paternal haplotype mapping`
    (FeatureType) — the parental-origin axis (maternal/paternal) is a separate
    DEFERRED axis, not a value of haplotype_resolution.

Usage:
    python scripts/apply_haplotype_resolution_decomposition.py
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
FACET_TSV = ROOT / "mappings" / "facet_decomposition.tsv"

# The 7 compound terms of this operation, by enum (the authoritative removal set).
DATATYPE_REMOVE = [
    "haplotype-specific alignments",
    "haplotype-specific contact matrix",
    "allele-specific contact matrix",
    "haplotype-specific nuclease cleavage frequency",
    "haplotype-specific nuclease cleavage corrected frequency",
]
FEATURETYPE_REMOVE = [
    "phased variant calls",
    "phased mapping",
]

# Bases to mint (base_exists=no). No meaning CURIEs.
NEW_DATATYPE_BASES = {
    "nuclease cleavage corrected frequency": {
        "description": "Bias-corrected per-base nuclease cleavage frequency.",
        "in_subset": ["chromatin_accessibility"],
    },
}
NEW_FEATURETYPE_BASES = {
    "mapping": {
        "description": "Sequence reads or contigs assigned to a haplotype.",
        "in_subset": ["haplotype"],
    },
}

# Reused bases that must already exist (the decomposition targets).
DATATYPE_BASE_MUST_EXIST = [
    "alignments",
    "contact matrix",
    "nuclease cleavage frequency",
]
FEATURETYPE_BASE_MUST_EXIST = [
    "variant calls",
]

# Terms that must NOT be touched (deferred / different sense). Confirmed intact.
PROTECTED_DATATYPE = [
    "diploid personal genome alignments",
]
PROTECTED_FEATURETYPE = [
    "allele-specific variants",
    "maternal variant calls",
    "paternal variant calls",
    "maternal haplotype mapping",
    "paternal haplotype mapping",
]


def read_tsv_haplotype_rows():
    """Read TSV by header name; return (dt_remove, ft_remove) for hap rows."""
    with open(FACET_TSV) as fh:
        reader = csv.DictReader(
            (l for l in fh if not l.startswith("#")), delimiter="\t")
        if "haplotype_resolution" not in reader.fieldnames:
            print("ERROR: TSV has no haplotype_resolution column")
            sys.exit(1)
        dt, ft = [], []
        for r in reader:
            if not (r.get("haplotype_resolution") or "").strip():
                continue
            term = r["encode_term"].strip()
            if (r.get("output_type") or "").strip():
                dt.append(term)
            elif (r.get("feature_type") or "").strip():
                ft.append(term)
            else:
                print(f"ERROR: hap row {term!r} has no base column")
                sys.exit(1)
        return dt, ft


def make_entry(spec):
    from ruamel.yaml.comments import CommentedMap
    entry = CommentedMap()
    entry["description"] = spec["description"]
    if "meaning" in spec:
        entry["meaning"] = spec["meaning"]
    entry["in_subset"] = list(spec["in_subset"])
    return entry


def main():
    # Cross-check the hardcoded removal set against the TSV (by header name).
    tsv_dt, tsv_ft = read_tsv_haplotype_rows()
    if sorted(tsv_dt) != sorted(DATATYPE_REMOVE):
        print(f"ERROR: TSV DataType hap rows {sorted(tsv_dt)} != expected "
              f"{sorted(DATATYPE_REMOVE)}")
        sys.exit(1)
    if sorted(tsv_ft) != sorted(FEATURETYPE_REMOVE):
        print(f"ERROR: TSV FeatureType hap rows {sorted(tsv_ft)} != expected "
              f"{sorted(FEATURETYPE_REMOVE)}")
        sys.exit(1)
    print(f"TSV hap rows verified: {len(tsv_dt)} DataType + {len(tsv_ft)} FeatureType")

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 120

    print(f"Loading {SCHEMA_PATH}...")
    data = yaml.load(SCHEMA_PATH)
    dt = data["enums"]["DataType"]["permissible_values"]
    ft = data["enums"]["FeatureType"]["permissible_values"]

    dt_start = len(dt)
    ft_start = len(ft)
    print(f"Starting DataType count:    {dt_start}")
    print(f"Starting FeatureType count: {ft_start}")

    # Pre-flight checks.
    for t in DATATYPE_REMOVE:
        if t not in dt:
            print(f"ERROR: DataType term to remove not found: {t!r}")
            sys.exit(1)
    for t in FEATURETYPE_REMOVE:
        if t not in ft:
            print(f"ERROR: FeatureType term to remove not found: {t!r}")
            sys.exit(1)
    for b in NEW_DATATYPE_BASES:
        if b in dt or b in ft:
            print(f"ERROR: DataType base to mint already exists: {b!r}")
            sys.exit(1)
    for b in NEW_FEATURETYPE_BASES:
        if b in dt or b in ft:
            print(f"ERROR: FeatureType base to mint already exists: {b!r}")
            sys.exit(1)
    for b in DATATYPE_BASE_MUST_EXIST:
        if b not in dt:
            print(f"ERROR: DataType base expected to exist is missing: {b!r}")
            sys.exit(1)
    for b in FEATURETYPE_BASE_MUST_EXIST:
        if b not in ft:
            print(f"ERROR: FeatureType base expected to exist is missing: {b!r}")
            sys.exit(1)
    # Verify mint subset matches sibling for nuclease cleavage corrected frequency.
    sib = dt["nuclease cleavage frequency"].get("in_subset")
    if list(sib) != ["chromatin_accessibility"]:
        print(f"ERROR: sibling subset mismatch: {sib!r}")
        sys.exit(1)
    # Verify haplotype subset exists.
    subsets = data.get("subsets", {})
    if "haplotype" not in subsets:
        print("ERROR: 'haplotype' subset missing from schema")
        sys.exit(1)
    for t in PROTECTED_DATATYPE:
        if t not in dt:
            print(f"ERROR: protected DataType term missing before edit: {t!r}")
            sys.exit(1)
        if t in DATATYPE_REMOVE:
            print(f"ERROR: protected term in removal set: {t!r}")
            sys.exit(1)
    for t in PROTECTED_FEATURETYPE:
        if t not in ft:
            print(f"ERROR: protected FeatureType term missing before edit: {t!r}")
            sys.exit(1)
        if t in FEATURETYPE_REMOVE:
            print(f"ERROR: protected term in removal set: {t!r}")
            sys.exit(1)

    # 1. Mint bases.
    minted_dt = []
    for base, spec in NEW_DATATYPE_BASES.items():
        dt[base] = make_entry(spec)
        minted_dt.append(base)
        print(f"  MINT DataType base '{base}'")
    minted_ft = []
    for base, spec in NEW_FEATURETYPE_BASES.items():
        ft[base] = make_entry(spec)
        minted_ft.append(base)
        print(f"  MINT FeatureType base '{base}'")

    # 2a. Remove the 5 compound DataType terms.
    removed_dt = []
    for term in DATATYPE_REMOVE:
        del dt[term]
        removed_dt.append(term)
        print(f"  REMOVE DataType '{term}'")

    # 2b. Remove the 2 compound FeatureType terms.
    removed_ft = []
    for term in FEATURETYPE_REMOVE:
        del ft[term]
        removed_ft.append(term)
        print(f"  REMOVE FeatureType '{term}'")

    dt_end = len(dt)
    ft_end = len(ft)

    # Guardrails.
    for term in DATATYPE_REMOVE:
        assert term not in dt, f"DataType compound still present: {term}"
    for term in FEATURETYPE_REMOVE:
        assert term not in ft, f"FeatureType compound still present: {term}"
    for base in NEW_DATATYPE_BASES:
        assert base in dt, f"minted DataType base missing: {base}"
    for base in NEW_FEATURETYPE_BASES:
        assert base in ft, f"minted FeatureType base missing: {base}"
    for base in DATATYPE_BASE_MUST_EXIST:
        assert base in dt, f"DataType base missing after edit: {base}"
    for base in FEATURETYPE_BASE_MUST_EXIST:
        assert base in ft, f"FeatureType base missing after edit: {base}"
    for term in PROTECTED_DATATYPE:
        assert term in dt, f"PROTECTED DataType term removed: {term}"
    for term in PROTECTED_FEATURETYPE:
        assert term in ft, f"PROTECTED FeatureType term removed: {term}"

    print(f"\nWriting {SCHEMA_PATH}...")
    yaml.dump(data, SCHEMA_PATH)

    print("\n=== Summary ===")
    print(f"DataType:    {dt_start} -> {dt_end} (minted {len(minted_dt)}: "
          f"{minted_dt}; removed {len(removed_dt)})")
    print(f"FeatureType: {ft_start} -> {ft_end} (minted {len(minted_ft)}: "
          f"{minted_ft}; removed {len(removed_ft)})")
    print(f"Protected DataType intact:    {len(PROTECTED_DATATYPE)}")
    print(f"Protected FeatureType intact: {len(PROTECTED_FEATURETYPE)} "
          f"(total {len(PROTECTED_DATATYPE) + len(PROTECTED_FEATURETYPE)}/6)")


if __name__ == "__main__":
    main()
