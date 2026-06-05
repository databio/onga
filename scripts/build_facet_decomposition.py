#!/usr/bin/env python3
"""Build mappings/facet_decomposition.tsv from the DataType enum.

Decomposes each compound ENCODE/DataType term carrying a strand,
read_multiplicity, and/or filter_status qualifier into its faceted form
(output_type + strand + read_multiplicity + filter_status). This is the
authoritative, lossless round-trip bridge between the compound ENCODE
output_type terms and ONGA's faceted TrackInterpretation slots.

The strand, read_multiplicity, and filter_status axes are factored out here.
Other qualifiers (normalized / observed / predicted / raw / "selected regions
for" / redacted) are DEFERRED axes and remain baked into the output_type base.

ADDITIVE ONLY: this reads the DataType enum but does not modify it. The actual
removal of compound terms is a separate reviewed step driven by this map.

SNAPSHOT: only emits rows for compound terms still present in the enum, so run
it BEFORE the matching apply_*.py removal step; the committed TSV persists rows
for terms later removed.
"""
import os
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src", "file_content.yaml")
OUT = os.path.join(ROOT, "mappings", "facet_decomposition.tsv")

READMULT_SUFFIXES = [(" of all reads", "all reads"), (" of unique reads", "unique reads")]
STRAND_INFIX = [("minus strand ", "minus"), ("plus strand ", "plus")]
STRAND_SUFFIX = [(" (minus strand)", "minus"), (" (plus strand)", "plus")]

# The filter axis (filtered / unfiltered) is not a clean prefix strip: the base
# name can change (singular -> plural: "filtered peptide quantification" ->
# "peptide quantifications") and one term keeps a sibling qualifier baked in
# ("redacted unfiltered alignments" -> "redacted alignments", redacted is a
# deferred axis). So the compound -> (base, filter_status) mapping is given
# explicitly here. base_exists is still computed against the live enum.
#
# NOTE: this table can only be regenerated while the compound filter terms are
# still present in the enum (i.e. before scripts/apply_facet_decomposition.py
# removes them). Compound terms named here but absent from the enum are skipped.
FILTER_DECOMPOSITION = {
    "filtered reads": ("reads", "filtered"),
    "unfiltered alignments": ("alignments", "unfiltered"),
    "redacted unfiltered alignments": ("redacted alignments", "unfiltered"),
    "filtered peaks": ("peaks", "filtered"),
    "filtered peptide quantification": ("peptide quantifications", "filtered"),
    "unfiltered peptide quantification": ("peptide quantifications", "unfiltered"),
    "filtered modified peptide quantification": ("modified peptide quantification", "filtered"),
    "unfiltered modified peptide quantification": ("modified peptide quantification", "unfiltered"),
    "unfiltered sparse gene count matrix": ("sparse gene count matrix", "unfiltered"),
    "unfiltered sparse splice junction count matrix": ("sparse splice junction count matrix", "unfiltered"),
}

# The normalization (scaling) axis is likewise not a clean prefix strip: the
# qualifier word varies ("raw" / "normalized" / "read-depth normalized" / "raw
# normalized" / "percentage normalized" / "depth normalized") and the base can
# change shape ("depth normalized signals matrix" -> "signals matrix"). So the
# compound -> (base, normalization) mapping is given explicitly here.
# base_exists is still computed against the live enum.
#
# SYNONYM MERGE: `normalized signal`, `read-depth normalized signal`, and `raw
# normalized signal` all collapse onto signal + depth_normalized (many-to-one).
# ENCODE->ONGA stays well-defined (all three rows recorded); ONGA->ENCODE is
# intentionally ambiguous for these — a deliberate non-1:1 collapse.
NORMALIZATION_DECOMPOSITION = {
    "raw signal": ("signal", "raw"),
    "normalized signal": ("signal", "depth_normalized"),
    "read-depth normalized signal": ("signal", "depth_normalized"),
    "raw normalized signal": ("signal", "depth_normalized"),
    "percentage normalized signal": ("signal", "percentage_normalized"),
    "normalized end position signal": ("end position signal", "depth_normalized"),
    "normalized observed signal profile": ("observed signal profile", "depth_normalized"),
    "normalized predicted signal profile": ("predicted signal profile", "depth_normalized"),
    "normalized predicted bias profile": ("predicted bias profile", "depth_normalized"),
    "normalized bias-corrected predicted signal profile": ("bias-corrected predicted signal profile", "depth_normalized"),
    "depth normalized signals matrix": ("signals matrix", "depth_normalized"),
}


def decompose(term):
    strand = ""
    read_mult = ""
    base = term
    # read-multiplicity suffix
    for suf, val in READMULT_SUFFIXES:
        if base.endswith(suf):
            read_mult = val
            base = base[: -len(suf)]
            break
    # strand: the "minus strand "/"plus strand " token may be preceded by a
    # deferred qualifier (e.g. "raw "), so strip it wherever it appears.
    matched = False
    for tok, val in STRAND_INFIX:
        if tok in base:
            strand = val
            base = base.replace(tok, "", 1).strip()
            matched = True
            break
    if not matched:
        for suf, val in STRAND_SUFFIX:
            if base.endswith(suf):
                strand = val
                base = base[: -len(suf)].rstrip()
                break
    return base, strand, read_mult


def main():
    schema = yaml.safe_load(open(SRC))
    pv = schema["enums"]["DataType"]["permissible_values"]
    terms = list(pv.keys())
    termset = set(terms)

    rows = []
    # Strand / read-multiplicity rows (parsed from compound suffixes/infixes).
    for term in terms:
        base, strand, read_mult = decompose(term)
        if strand or read_mult:
            base_exists = "yes" if base in termset else "no"
            rows.append((term, base, strand, read_mult, "", "", base_exists))
    # Filter rows (explicit table; the filter axis is not a clean prefix strip).
    for term, (base, filter_status) in FILTER_DECOMPOSITION.items():
        if term not in termset:
            continue
        base_exists = "yes" if base in termset else "no"
        rows.append((term, base, "", "", "", filter_status, base_exists))
    # Normalization rows (explicit table; the scaling axis is not a clean strip).
    for term, (base, normalization) in NORMALIZATION_DECOMPOSITION.items():
        if term not in termset:
            continue
        base_exists = "yes" if base in termset else "no"
        rows.append((term, base, "", "", "", normalization, base_exists))
    rows.sort()

    header_comment = [
        "# facet_decomposition.tsv",
        "# Maps each compound ENCODE output_type / DataType term to its ONGA faceted",
        "# form: output_type (the atomic base) + strand + read_multiplicity +",
        "# filter_status + normalization. This is the lossless round-trip bridge",
        "# between the compound ENCODE terms and ONGA's faceted descriptor slots",
        "# (strand -> StrandOrientation on TrackInterpretation; read_multiplicity ->",
        "# ReadMultiplicity, filter_status -> FilterStatus, normalization ->",
        "# Normalization on TrackProvenance).",
        "#",
        "# Four axes are factored out: strand, read_multiplicity, filter_status,",
        "# normalization. Remaining deferred qualifiers (observed / predicted /",
        "# control / bias-corrected / 'selected regions for' / redacted) stay baked",
        "# into the output_type base.",
        "#",
        "# The `normalization` column (added operation #11) factors the scaling axis",
        "# (raw / depth_normalized / percentage_normalized) out of compound signal",
        "# terms. SYNONYM MERGE: three ENCODE terms collapse many-to-one onto signal",
        "# + depth_normalized — `normalized signal`, `read-depth normalized signal`,",
        "# and `raw normalized signal`. ENCODE->ONGA stays well-defined (all three",
        "# rows recorded); ONGA->ENCODE is intentionally ambiguous for these (a",
        "# deliberate non-1:1 collapse approved by the curator).",
        "#",
        "# base_exists=no flags atomic output_type terms that do NOT yet exist as",
        "# standalone DataType terms; the later (separate, reviewed) removal step",
        "# must add these when it removes the compound terms.",
        "#",
        "# Generated by scripts/build_facet_decomposition.py from src/file_content.yaml.",
        "# This generator is a SNAPSHOT tool: it only emits rows for compound terms",
        "# still present in the enum, so it must be run BEFORE the matching",
        "# apply_*.py removal step. The committed TSV is the persisted artifact.",
        "# DataType enum is NOT modified by this step.",
    ]

    with open(OUT, "w") as fh:
        fh.write("\n".join(header_comment) + "\n")
        fh.write("\t".join(["encode_term", "output_type", "strand", "read_multiplicity", "filter_status", "normalization", "base_exists"]) + "\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")

    no_count = sum(1 for r in rows if r[5] == "no")
    print(f"Wrote {OUT}: {len(rows)} rows, {no_count} with base_exists=no")


_GUARD = """
╔══════════════════════════════════════════════════════════════════════════╗
║  REFUSING TO RUN — this is a one-time SNAPSHOT generator, not a rebuilder. ║
╠══════════════════════════════════════════════════════════════════════════╣
║  mappings/facet_decomposition.tsv is now CURATED and hand-maintained. It   ║
║  persists rows for compound terms that have since been REMOVED from the    ║
║  enum, and it has grown columns this script does not know about            ║
║  (feature_type, thresholding, derivation, reference_build_sex).            ║
║                                                                            ║
║  Re-running this would emit only rows for compounds STILL in the enum      ║
║  (≈none remain) in the OLD 7-column shape — silently destroying the        ║
║  lossless round-trip map. To add new decompositions, append rows by hand   ║
║  / via an apply_*.py step and verify with scripts/check_roundtrip.py.      ║
║                                                                            ║
║  If you truly understand this and want the historical snapshot anyway,     ║
║  pass --force-regenerate-snapshot (it will OVERWRITE the curated TSV).     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

if __name__ == "__main__":
    import sys
    if "--force-regenerate-snapshot" not in sys.argv:
        print(_GUARD)
        sys.exit(2)
    main()
