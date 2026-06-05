#!/usr/bin/env python3
"""Apply the derivation (observed vs. predicted) facet decomposition to file_content.yaml.

Operation #14. Driven by the derivation rows of mappings/facet_decomposition.tsv
(the six rows whose derivation column is non-empty and base_exists/encode_term
name a plain-form decomposition). Mirrors the prior facet-apply scripts:

  1. Mint the atomic DataType base output_types that do not yet exist
     (base_exists=no), generalizing description/subset from a compound sibling
     (observed/predicted scaling stripped). Here three bases:
       `signal profile`, `bias profile`, `control profile`  (signal_track subset)
  2. Remove the six compound terms from the CORRECT enum:
       DataType (5): observed signal profile, predicted signal profile,
                     observed bias profile, predicted bias profile,
                     observed control profile
       FeatureType (1): predicted transcription start sites
     The FeatureType base `transcription start sites` already exists.

The removed compound terms remain recoverable via the map plus the
TrackProvenance facet slot derivation -> Derivation, per the round-trip:
  compound term = output_type/feature_type + derivation (+ other facets).

`control` is deliberately NOT a derivation value (it denotes an experimental role
or a normalization reference, not measured-vs-model), so control-role terms are
left as distinct output_types. The bias-correction case
(`bias-corrected predicted signal profile`), the `selected regions for predicted
...` family, the enhancer family (`predicted enhancers`, etc.), assay-fused
predicted signals (`DNN-MPRA predicted signal`, `HMM predicted chromatin state`),
and `predicted 3D structural ensembles` are all DEFERRED / out of scope and
guarded as PROTECTED.

Usage:
    python scripts/apply_derivation_decomposition.py
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

# Six compound terms to remove, by enum.
DATATYPE_REMOVE = [
    "observed signal profile",
    "predicted signal profile",
    "observed bias profile",
    "predicted bias profile",
    "observed control profile",
]
FEATURETYPE_REMOVE = [
    "predicted transcription start sites",
]

# Three DataType bases to mint (base_exists=no). Descriptions generalized from
# the observed/predicted sibling compounds (derivation language stripped);
# subset matched to the siblings (signal_track).
NEW_DATATYPE_BASES = {
    "signal profile": {
        "description": "Signal profile across genomic positions.",
        "in_subset": ["signal_track"],
    },
    "bias profile": {
        "description": "Sequencing bias profile across genomic positions.",
        "in_subset": ["signal_track"],
    },
    "control profile": {
        "description": "Control signal profile.",
        "in_subset": ["signal_track"],
    },
}

# FeatureType base that must already exist (the decomposition target).
FEATURETYPE_BASE_MUST_EXIST = ["transcription start sites"]

# Terms that must NOT be touched (deferred / out of scope). Confirmed intact
# after the run. `control` is excluded from derivation, so control-role terms
# stay; bias-corrected / selected-regions / enhancer / assay-fused predicted /
# 3D-ensemble cases are deferred.
PROTECTED_DATATYPE = [
    "control normalized signal",
    "fold change over control",
    "negative control regions",
    "positive control regions",
    "DNN-MPRA predicted signal",
    "HMM predicted chromatin state",
    "bias-corrected predicted signal profile",
    "selected regions for predicted signal profile",
    "selected regions for predicted bias profile",
    "selected regions for bias-corrected predicted signal profile",
    "selected regions for predicted signal and sequence contribution scores",
]
PROTECTED_FEATURETYPE = [
    "predicted enhancers",
    "predicted forebrain enhancers",
    "predicted heart enhancers",
    "predicted whole brain enhancers",
    "predicted 3D structural ensembles",
]


def make_entry(spec):
    from ruamel.yaml.comments import CommentedMap
    entry = CommentedMap()
    entry["description"] = spec["description"]
    if "meaning" in spec:
        entry["meaning"] = spec["meaning"]
    entry["in_subset"] = list(spec["in_subset"])
    return entry


def main():
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
            print(f"ERROR: base to mint already exists: {b!r}")
            sys.exit(1)
    for b in FEATURETYPE_BASE_MUST_EXIST:
        if b not in ft:
            print(f"ERROR: FeatureType base expected to exist is missing: {b!r}")
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

    # 1. Mint the three DataType bases.
    minted = []
    for base, spec in NEW_DATATYPE_BASES.items():
        dt[base] = make_entry(spec)
        minted.append(base)
        print(f"  MINT DataType base '{base}'")

    # 2a. Remove the five compound DataType terms.
    removed_dt = []
    for term in DATATYPE_REMOVE:
        del dt[term]
        removed_dt.append(term)
        print(f"  REMOVE DataType '{term}'")

    # 2b. Remove the one compound FeatureType term.
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
        assert base in dt, f"minted base missing: {base}"
    for base in FEATURETYPE_BASE_MUST_EXIST:
        assert base in ft, f"FeatureType base missing after edit: {base}"
    for term in PROTECTED_DATATYPE:
        assert term in dt, f"PROTECTED DataType term removed: {term}"
    for term in PROTECTED_FEATURETYPE:
        assert term in ft, f"PROTECTED FeatureType term removed: {term}"

    print(f"\nWriting {SCHEMA_PATH}...")
    yaml.dump(data, SCHEMA_PATH)

    print("\n=== Summary ===")
    print(f"DataType:    {dt_start} -> {dt_end} (minted {len(minted)}: {minted}; "
          f"removed {len(removed_dt)})")
    print(f"FeatureType: {ft_start} -> {ft_end} (removed {len(removed_ft)})")
    print(f"Protected DataType intact:    {len(PROTECTED_DATATYPE)}")
    print(f"Protected FeatureType intact: {len(PROTECTED_FEATURETYPE)}")


if __name__ == "__main__":
    main()
