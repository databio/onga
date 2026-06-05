#!/usr/bin/env python3
"""Apply operation #15: reference-build-sex faceting + anatomy scope ejection.

Two independent removals against src/file_content.yaml, NO mints:

  PART 1 (DataType) — reference-build sex faceting. Remove the 4 compound
  `male/female genome reference|index` DataType terms. They decompose onto the
  already-existing atomic bases `genome reference` / `genome index` plus the new
  `build_sex` (ReferenceBuildSex) facet on the ReferenceGenome descriptor schema.
  Round-trip preserved in mappings/facet_decomposition.tsv (reference_build_sex
  column). The male/female qualifies the REFERENCE assembly, not the sample.

  PART 2 (FeatureType) — anatomy scope ejection (delegation, NOT a facet). Remove
  the 3 `predicted <tissue> enhancers` FeatureType terms. They collapse onto the
  already-existing content base `predicted enhancers`; the tissue is ejected to
  UBERON (a biospecimen property), recorded in mappings/scope_delegations.tsv —
  NOT in the facet map. `predicted enhancers` keeps its baked `predicted`
  (enhancer-family derivation deferred); do not touch it.

Usage:
    python scripts/apply_reference_sex_and_anatomy.py
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

# PART 1: sex DataType compounds -> existing bases (no mint).
SEX_REMOVE = [
    "male genome reference",
    "female genome reference",
    "male genome index",
    "female genome index",
]
SEX_BASES = ["genome reference", "genome index"]  # must already exist, must survive

# PART 2: anatomy FeatureType compounds -> existing content base (no mint).
ANATOMY_REMOVE = [
    "predicted forebrain enhancers",
    "predicted heart enhancers",
    "predicted whole brain enhancers",
]
ANATOMY_BASE = ["predicted enhancers"]  # must already exist, must survive


def main():
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 120

    print(f"Loading {SCHEMA_PATH}...")
    data = yaml.load(SCHEMA_PATH)
    dt = data["enums"]["DataType"]["permissible_values"]
    ft = data["enums"]["FeatureType"]["permissible_values"]

    dt_before = len(dt)
    ft_before = len(ft)
    print(f"DataType before:   {dt_before}")
    print(f"FeatureType before: {ft_before}")

    # Pre-flight: removals present.
    for t in SEX_REMOVE:
        if t not in dt:
            print(f"ERROR: sex compound not in DataType: {t!r}")
            sys.exit(1)
    for t in ANATOMY_REMOVE:
        if t not in ft:
            print(f"ERROR: anatomy compound not in FeatureType: {t!r}")
            sys.exit(1)
    # Pre-flight: bases present (no mint expected).
    for b in SEX_BASES:
        if b not in dt:
            print(f"ERROR: sex base missing (would require mint): {b!r}")
            sys.exit(1)
    for b in ANATOMY_BASE:
        if b not in ft:
            print(f"ERROR: anatomy base missing (would require mint): {b!r}")
            sys.exit(1)

    # PART 1: remove sex DataType compounds.
    for t in SEX_REMOVE:
        del dt[t]
        print(f"  REMOVE DataType    '{t}'")

    # PART 2: remove anatomy FeatureType compounds.
    for t in ANATOMY_REMOVE:
        del ft[t]
        print(f"  REMOVE FeatureType '{t}'")

    dt_after = len(dt)
    ft_after = len(ft)

    # Guardrails.
    for t in SEX_REMOVE:
        assert t not in dt, t
    for t in ANATOMY_REMOVE:
        assert t not in ft, t
    for b in SEX_BASES:
        assert b in dt, f"sex base removed: {b}"
    for b in ANATOMY_BASE:
        assert b in ft, f"anatomy base removed: {b}"
    assert dt_after == dt_before - 4, (dt_before, dt_after)
    assert ft_after == ft_before - 3, (ft_before, ft_after)

    print(f"\nWriting {SCHEMA_PATH}...")
    yaml.dump(data, SCHEMA_PATH)

    print("\n=== Summary ===")
    print(f"DataType:    {dt_before} -> {dt_after}  (-{dt_before - dt_after})")
    print(f"FeatureType: {ft_before} -> {ft_after}  (-{ft_before - ft_after})")
    print(f"Sex bases intact:     {SEX_BASES}")
    print(f"Anatomy base intact:  {ANATOMY_BASE}")


if __name__ == "__main__":
    main()
