#!/usr/bin/env python3
"""Emit + validate mappings/so.sssom.tsv from the curated tables below.

ONGA terms denote SETS of genomic elements (a file, a track, a set of rows);
Sequence Ontology classes denote INDIVIDUAL element types. That level shift is
not a SKOS concept-to-concept mapping, so the membership relation is carried by
ONGA's own property `onga:has_element_type` and the exact/close/broad grade
moves to the declared SSSOM extension column `element_type_fit`.

See the ADR "ONGA terms denote sets; SO terms denote elements"
(pepkit/onga_so_set_vs_element_adr.md) and DECISIONS.md design principle #7.

Four curated tables:
  CUR              membership rows -> predicate onga:has_element_type
  SET_TO_SET       the whitelisted rows where the SO class is ITSELF
                   set-denoting, so a plain SKOS match is correct
  RELATED          non-membership rows -> predicate skos:relatedMatch
  NO_ELEMENT_TYPE  terms reviewed and found to have no SO element type at all
                   (annotation-only; they produce no SSSOM row)

`element_type_annotations()` is imported by scripts/apply_element_type.py so the
TSV and the `annotations:` blocks in src/file_content.yaml cannot drift apart.
`scripts/check_roundtrip.py` re-checks the agreement in `make test`.
"""
import os, re, sys, yaml
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "embeddings"))
from onga_embeddings.ontology_loader import parse_obo

# Element-type FIT grades (a curation grade, not a relation). Mechanical
# conversion from the old SKOS ladder: exactMatch->exact, closeMatch->approximate,
# broadMatch->broad.
EX, AP, BR, NA = "exact", "approximate", "broad", "not_applicable"
FITS = {EX, AP, BR, NA}

HAS_ELEMENT_TYPE = "onga:has_element_type"
RELATED_MATCH = "skos:relatedMatch"
BANNED_SKOS = {"skos:exactMatch", "skos:closeMatch", "skos:broadMatch", "skos:narrowMatch"}

# SO classes that are THEMSELVES set-denoting, so a SKOS match is correct.
# Verified against so.obo: both definitions begin "A collection of sequences".
SET_DENOTING_SO = {"SO:0001505", "SO:0001506"}

SUBJECT_CATEGORY = "genomic element set"
OBJECT_CATEGORY = "sequence feature type"

ENUM_NAME = {"F": "FeatureType", "D": "DataType"}

# ---------------------------------------------------------------------------
# Membership rows. (onga_term, enum_code, fit, SO id, comment)
# "Every row of a file bearing this ONGA term is an instance of this SO class."
# ---------------------------------------------------------------------------
CUR = [
# ---------------- FeatureType: chromatin accessibility
("open chromatin regions","F",EX,"SO:0001747","Direct match"),
("footprints","F",AP,"SO:0000235","Nuclease footprint marks an inferred TF binding site; SO has no footprint term"),
# ---------------- FeatureType: 3D genome
("contact domains","F",EX,"SO:0002304","ONGA definition is TADs verbatim"),
("nested contact domains","F",BR,"SO:0002304","Hierarchical nesting is not modeled in SO"),
("loops","F",EX,"SO:0002307","Chromatin loop. NOTE: SO:0002254 'loop' is an RNA stem-loop, a lexical false friend"),
# ---------------- FeatureType: DNA methylation
("methylation state at CpG","F",BR,"SO:0000114","SO has no sequence-context-specific methylation terms"),
("methylation state at CHG","F",BR,"SO:0000114","SO has no CHG-context term"),
("methylation state at CHH","F",BR,"SO:0000114","SO has no CHH-context term"),
("smoothed methylation state at CpG","F",BR,"SO:0000114","Smoothing is provenance; content is CpG methylation"),
# ---------------- FeatureType: regulatory elements
("candidate Cis-Regulatory Elements","F",BR,"SO:0001055","cCREs mix enhancers/promoters/insulators; SO:0001055 is the correct common ancestor and 'candidate' is an ONGA derivation facet"),
("candidate enhancers","F",BR,"SO:0000165","'candidate' is a derivation facet, not a distinct SO class"),
("predicted enhancers","F",BR,"SO:0000165","'predicted' is a derivation facet"),
("enhancers reference","F",BR,"SO:0000165","Reference set of enhancers"),
("candidate promoters","F",BR,"SO:0000167","'candidate' is a derivation facet"),
("promoters reference","F",BR,"SO:0000167","Reference set of promoters"),
# `regulatory elements` is a MIXED set: its definition enumerates the four
# kinds, so it gets one row per SO class rather than a single ancestor row.
("regulatory elements","F",EX,"SO:0000165","Mixed set; the ONGA definition enumerates enhancers, promoters, silencers, insulators"),
("regulatory elements","F",EX,"SO:0000167","Mixed set; see the enhancer row"),
("regulatory elements","F",EX,"SO:0000625","Mixed set; see the enhancer row"),
("regulatory elements","F",EX,"SO:0000627","Mixed set; see the enhancer row"),
("curated binding sites","F",BR,"SO:0000235","Curation is provenance; content is a TF binding site"),
("polyA sites","F",EX,"SO:0000553","Direct match"),
("transcription start sites","F",EX,"SO:0000315","Direct match"),
("TSS reference","F",BR,"SO:0000315","Reference set of TSSs"),
# ---------------- FeatureType: variants
("copy number variation","F",EX,"SO:0001019","Direct match"),
("SNPs","F",EX,"SO:0000694","Direct match"),
("curated SNVs","F",BR,"SO:0001483","Curation is provenance; content is an SNV"),
("indels","F",AP,"SO:1000032","SO 'delins' carries the 'indel' synonym; SO:0002217 unspecified_indel is a narrower sibling"),
("variant calls","F",AP,"SO:0001060","Generic called variants"),
("reference variants","F",BR,"SO:0001060","Known-variant reference set"),
("variant reference","F",BR,"SO:0001060","Known-variant reference database"),
("allele-specific variants","F",BR,"SO:0001060","Allele-specificity is an interpretation facet, not an SO class"),
("maternal variant calls","F",AP,"SO:0001775","Direct match on parental origin"),
("paternal variant calls","F",AP,"SO:0001776","Direct match on parental origin"),
("eQTLs","F",BR,"SO:0000771","SO has no expression-specific QTL subtype"),
("dsQTLs","F",BR,"SO:0000771","SO has no accessibility-specific QTL subtype"),
# ---------------- FeatureType: motifs
("sequence motifs","F",EX,"SO:0001683","Direct match"),
("sequence motifs instances","F",AP,"SO:0000714","Located motif occurrences in nucleotide sequence"),
# ---------------- FeatureType: annotation
("splice junctions","F",EX,"SO:0001421","Direct match"),
("transcribed fragments","F",EX,"SO:0001418","Direct match"),
("repeat elements annotation","F",BR,"SO:0000657","Annotation of repeat regions"),
("miRNA annotations","F",BR,"SO:0000276","Annotation of miRNA genes and precursors"),
("restriction enzyme site locations","F",AP,"SO:0001687","Locations of recognition sites"),
("RNA-binding protein associated mRNAs","F",AP,"SO:0000279","Transcripts bound by protein"),
("functional conservation mapping","F",AP,"SO:0000330","Conserved regions across species"),
# ---------------- FeatureType: structure / haplotype
("contigs","F",EX,"SO:0000149","Direct match"),
# ---------------- FeatureType: RNA modification
("m6A methylation state","F",EX,"SO:0001297","Direct match"),
("m5C methylation state","F",AP,"SO:0001282","RNA 5-methylcytidine (not the DNA term SO:0001918)"),
("inosine methylation state","F",AP,"SO:0001274","A-to-I editing product"),
("pseudouridine methylation state","F",AP,"SO:0001229","Direct match on the modified base"),
("Nm methylation state","F",BR,"SO:0000250","SO has only base-specific 2'-O-methyl terms, no generic Nm"),
# ---------------- DataType, Group A: sequence-object sets.
# The rows really are sequence features, so has_element_type is admissible.
("reads","D",EX,"SO:0000150","Direct match"),
("rejected reads","D",BR,"SO:0000150","Rejection is a QC facet"),
("subreads","D",BR,"SO:0000150","Long-read subread; SO has no subread term"),
("R2C2 subreads","D",BR,"SO:0000150","Rolling-circle subread; SO has no subread term"),
("index reads","D",AP,"SO:0002023","Demultiplexing index sequence"),
("sequence barcodes","D",AP,"SO:0002023","Sample or cell multiplexing tag"),
("primer sequence","D",EX,"SO:0000112","Direct match"),
("gRNAs","D",EX,"SO:0001998","CRISPR single-guide RNA (SO:0000602 guide_RNA is the RNA-editing sense)"),
("non-targeting gRNAs","D",BR,"SO:0001998","Control guides; targeting status is not an SO axis"),
("safe-targeting gRNAs","D",BR,"SO:0001998","Control guides"),
("ranked gRNAs","D",BR,"SO:0001998","Ranking is provenance"),
("chromosomes reference","D",BR,"SO:0000340","Per-chromosome reference sequences"),
("mitochondrial genome reference","D",AP,"SO:0000737","Mitochondrial reference sequence"),
("repeats reference","D",BR,"SO:0000657","Reference repeat annotation"),
("rRNA reference","D",BR,"SO:0000252","Reference rRNA sequences"),
("tRNA reference","D",BR,"SO:0000253","Reference tRNA sequences"),
("snRNA reference","D",BR,"SO:0000274","Reference snRNA sequences"),
("miRNA reference","D",BR,"SO:0000276","Reference miRNA sequences and annotations"),
# ---------------- DataType, Group B: located-region sets with biological names.
# Element-type holds. That it holds is a DIAGNOSTIC: a DataType with a clean SO
# element type is FeatureType-shaped. Re-homing is deferred (DECISIONS.md
# "Cleanup decisions"), NOT an oversight.
("peaks","D",AP,"SO:0000703","Re-graded from relatedMatch: peak rows ARE experimental result regions; the earlier objection was that SO:0001697 ChIP_seq_region is assay-bound, a different point"),
("DHS peaks","D",EX,"SO:0000685","Direct match"),
("consensus DNase hypersensitivity sites","D",BR,"SO:0000685","Consensus across samples is provenance"),
("representative DNase hypersensitivity sites","D",BR,"SO:0000685","Curated representative set"),
("DHS regions reference","D",BR,"SO:0000685","Reference set of DHSs"),
("hotspots","D",AP,"SO:0002331","Broad accessible-chromatin domains"),
]

# ---------------------------------------------------------------------------
# The ONLY rows allowed to use skos:exactMatch / closeMatch / broadMatch against
# SO: the object SO class is itself SET-denoting, so the level shift does not
# apply and a plain SKOS concept-to-concept match is correct.
# (onga_term, enum_code, skos predicate, SO id, comment)
# ---------------------------------------------------------------------------
SET_TO_SET = [
("genome reference","D","skos:exactMatch","SO:0001505","Set-to-set exception: SO:0001505 is itself defined as 'A collection of sequences (often chromosomes) taken as the standard for a given organism and genome assembly'"),
("personalized genome assembly","F","skos:closeMatch","SO:0001506","Set-to-set exception: SO:0001506 is itself defined as 'A collection of sequences (often chromosomes) of an individual'"),
]

# ---------------------------------------------------------------------------
# Non-membership rows. The ONGA term's rows are NOT instances of the SO class;
# the two concepts are merely associatively related. skos:relatedMatch is the
# only SKOS predicate ONGA uses against an element-level SO class, because it
# asserts neither equivalence nor hierarchy.
# (onga_term, enum_code, SO id, comment)
# ---------------------------------------------------------------------------
RELATED = [
("methylated reads","F","SO:0000306","Rows are reads CARRYING the base modification, not the base feature itself"),
("variant effect quantifications","F","SO:0001536","Rows are numbers about variants, not variants"),
("PWMs","F","SO:0001683","A PWM is a MODEL of a motif; SO has no matrix/model term"),
("maternal haplotype mapping","F","SO:0001024","Rows are haplotype assignments, not haplotypes"),
("paternal haplotype mapping","F","SO:0001024","Rows are haplotype assignments, not haplotypes"),
("mapping","F","SO:0001024","Rows are haplotype assignments, not haplotypes"),
("nuclease cleavage frequency","D","SO:0000684","Group C: rows are per-base numbers, not nuclease-sensitive sites; fails the DataType admissibility rule"),
("sequence adapters","D","SO:0000150","Group D: adapters are not reads and SO has no adapter term (see SO-REQ-010)"),
]

# ---------------------------------------------------------------------------
# Reviewed and found to have NO SO element type. Annotation-only: these produce
# `element_type_fit: not_applicable` with no `element_type`, and no SSSOM row
# (SSSOM needs an object). This value is what distinguishes CURATED-NONE from
# NOT-YET-CURATED (an absent annotation).
# (onga_term, enum_code, reason)
# ---------------------------------------------------------------------------
NO_ELEMENT_TYPE = [
("element gene links","F","Rows are PAIRS (edges) between an element and a gene, not features; see TrackGeometry.has_edges"),
("links","F","Rows are PAIRS (edges), not features; see TrackGeometry.has_edges"),
("element gene interactions p-value","F","Rows are statistics about edges, not features"),
("element gene interactions signal","F","Rows are statistics about edges, not features"),
("sequence motifs report","F","Rows are report entries, not located features"),
("3D structure","F","Rows are structural model coordinates, not sequence features"),
("cell type annotations","F","Rows are cell labels; cell type is delegated to CL (SO-REJ-001)"),
("cell type data","F","Rows are per-cell values; cell type is delegated to CL (SO-REJ-001)"),
]

HEADER = """# SSSOM Mapping file: ONGA -> Sequence Ontology (SO)
# curie_map:
#   onga: https://databio.org/onga/
#   SO: http://purl.obolibrary.org/obo/SO_
#   skos: http://www.w3.org/2004/02/skos/core#
#   semapv: https://w3id.org/semapv/vocab/
# mapping_set_id: https://databio.org/onga/mappings/so
# mapping_set_description: ONGA subjects denote SETS of genomic elements; SO objects denote INDIVIDUAL element types, so the relation is membership, not equivalence. Membership rows use onga:has_element_type with an element_type_fit grade; skos:relatedMatch marks rows whose members are NOT instances; skos:exactMatch/closeMatch/broadMatch are banned against SO except for the two whitelisted SO classes that are themselves set-denoting.
# creator_id: https://orcid.org/0000-0001-5884-4247
# license: https://creativecommons.org/licenses/by/4.0/
# mapping_date: 2026-08-31
# subject_source: https://databio.org/onga/
# object_source: SO
# object_source_version: so.obo 2026-08-07
# extension_definitions:
#   - slot_name: element_type_fit
#     property: https://databio.org/onga/element_type_fit
#     type_hint: http://www.w3.org/2001/XMLSchema#string
#
# THE SET / ELEMENT RULE
# ----------------------
# An ONGA DataType or FeatureType term names a SET of genomic elements -- a
# file, a track, a set of rows. A Sequence Ontology class names an INDIVIDUAL
# element type. These are different kinds of thing, so ONGA never asserts
# identity, equivalence, or hierarchy against an SO class. ONGA is a USER of SO,
# not a competitor to it. See the ADR "ONGA terms denote sets; SO terms denote
# elements" and DECISIONS.md design principle #7.
#
# PREDICATE POLICY
# ----------------
#   onga:has_element_type  every row of a file bearing the subject term is an
#                          INSTANCE of the object SO class. This is the
#                          membership relation, not a mapping. Multi-element-type
#                          subjects (mixed sets) carry one row per SO class.
#   skos:relatedMatch      the members are NOT instances of the object class;
#                          the two concepts are merely associatively related
#                          (a model of a feature, a measurement about a feature,
#                          an assignment to a feature). This is the only SKOS
#                          predicate ONGA uses against an element-level SO class.
#   skos:exactMatch        BANNED against SO, except for the two whitelisted
#   skos:closeMatch        set-denoting SO classes below.
#   skos:broadMatch
#
# THE TWO WHITELISTED SET-TO-SET EXCEPTIONS
# -----------------------------------------
#   SO:0001505 reference_genome -- "A collection of sequences (often
#     chromosomes) taken as the standard for a given organism and genome
#     assembly."
#   SO:0001506 variant_genome -- "A collection of sequences (often chromosomes)
#     of an individual."
# Both SO classes are THEMSELVES set-denoting, so the level shift does not apply
# and a plain SKOS match is correct. scripts/build_so_sssom.py fails the build if
# any other SO id is given a SKOS *Match predicate.
#
# COLUMNS
# -------
#   subject_category   constant "genomic element set"      (ONGA side: a SET)
#   object_category    constant "sequence feature type"    (SO side: an ELEMENT)
#   element_type_fit   how tightly the SO class fits the members -- a curation
#                      grade, NOT a different relation:
#                        exact       the SO class is the tight fit
#                        approximate SO's nearest available class; imperfect
#                        broad       all members are instances but the SO class
#                                    is broader -- AN SO GAP, and the
#                                    machine-readable feed into
#                                    proposals/upstream_requests.yaml
#                      Empty on skos:* rows, where fit does not apply.
#
# Terms reviewed and found to have NO SO element type at all (signal values,
# matrices, models, edges) carry `element_type_fit: not_applicable` as an
# annotation on the permissible value in src/file_content.yaml and appear in no
# row here, since SSSOM requires an object.
"""

COLUMNS = ["subject_id", "predicate_id", "object_id", "mapping_justification",
           "subject_label", "object_label", "subject_category", "object_category",
           "element_type_fit", "comment"]


def curie(name):
    return "onga:" + re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def element_type_annotations():
    """The permissible-value annotations implied by the curated tables.

    Returns {(enum_name, term): {"element_type": "SO:a|SO:b", "element_type_fit": fit}}
    Imported by scripts/apply_element_type.py so the TSV and src/file_content.yaml
    cannot state different things.
    """
    out = {}
    for name, cat, fit, oid, _c in CUR:
        key = (ENUM_NAME[cat], name)
        rec = out.setdefault(key, {"element_type": [], "element_type_fit": fit})
        if rec["element_type_fit"] != fit:
            raise ValueError(f"conflicting element_type_fit for {key}: "
                             f"{rec['element_type_fit']} vs {fit}")
        if oid not in rec["element_type"]:
            rec["element_type"].append(oid)
    for key in list(out):
        out[key]["element_type"] = "|".join(out[key]["element_type"])
    for name, cat, oid, _c in RELATED:
        key = (ENUM_NAME[cat], name)
        if key in out:
            raise ValueError(f"{key} is both a membership and a related row")
        out[key] = {"element_type_fit": NA}
    for name, cat, _reason in NO_ELEMENT_TYPE:
        key = (ENUM_NAME[cat], name)
        if key in out:
            raise ValueError(f"{key} is both mapped and declared element-type-less")
        out[key] = {"element_type_fit": NA}
    return out


def main():
    onga = yaml.safe_load(open("src/file_content.yaml"))["enums"]
    pools = {"D": onga["DataType"]["permissible_values"],
             "F": onga["FeatureType"]["permissible_values"]}
    so = {t["id"]: t for t in parse_obo("embeddings/data/ontologies/so.obo")}

    errs, rows = [], []
    seen = set()

    def check_term(name, cat, where):
        if cat not in pools:
            errs.append(f"{where}: bad enum code {cat!r} for {name!r}")
            return False
        if name not in pools[cat]:
            errs.append(f"{where}: ONGA term not found in {ENUM_NAME[cat]}: {name!r}")
            return False
        return True

    def check_so(oid, name, where):
        if oid not in so:
            errs.append(f"{where}: SO id not found or obsolete: {oid} (for {name!r})")
            return False
        return True

    def add(name, cat, pred, oid, fit, comment):
        # Duplicate key is (term, enum, SO id): a term may deliberately carry
        # several element types (a mixed set), but never the same one twice.
        key = (name, cat, oid)
        if key in seen:
            errs.append(f"duplicate row: {name!r} ({ENUM_NAME.get(cat, cat)}) -> {oid}")
        seen.add(key)
        # HARD GUARD: the whole point of the ADR.
        if pred in BANNED_SKOS and oid not in SET_DENOTING_SO:
            errs.append(
                f"BANNED PREDICATE {pred} against {oid} for {name!r}. ONGA terms denote "
                f"SETS and SO classes denote ELEMENTS, so exact/close/broadMatch are not "
                f"licensed. Use onga:has_element_type with an element_type_fit grade, or "
                f"skos:relatedMatch if the members are not instances. Only "
                f"{sorted(SET_DENOTING_SO)} are whitelisted (they are themselves "
                f"set-denoting). See the ADR 'ONGA terms denote sets; SO terms denote "
                f"elements'.")
        if fit and fit not in FITS:
            errs.append(f"bad element_type_fit {fit!r} for {name!r}")
        rows.append([curie(name), pred, oid, "semapv:ManualMappingCuration",
                     name, so.get(oid, {}).get("name", ""),
                     SUBJECT_CATEGORY, OBJECT_CATEGORY, fit or "", comment])

    for name, cat, fit, oid, comment in CUR:
        ok = check_term(name, cat, "CUR") & check_so(oid, name, "CUR")
        if not ok:
            continue
        add(name, cat, HAS_ELEMENT_TYPE, oid, fit, comment)

    for name, cat, pred, oid, comment in SET_TO_SET:
        ok = check_term(name, cat, "SET_TO_SET") & check_so(oid, name, "SET_TO_SET")
        if not ok:
            continue
        if oid not in SET_DENOTING_SO:
            errs.append(f"SET_TO_SET row {name!r} names {oid}, which is not in "
                        f"SET_DENOTING_SO")
            continue
        add(name, cat, pred, oid, "", comment)

    for name, cat, oid, comment in RELATED:
        ok = check_term(name, cat, "RELATED") & check_so(oid, name, "RELATED")
        if not ok:
            continue
        add(name, cat, RELATED_MATCH, oid, "", comment)

    for name, cat, _reason in NO_ELEMENT_TYPE:
        check_term(name, cat, "NO_ELEMENT_TYPE")

    try:
        annotations = element_type_annotations()
    except ValueError as e:
        errs.append(str(e))
        annotations = {}

    if errs:
        print("VALIDATION FAILED:\n  " + "\n  ".join(errs))
        sys.exit(1)

    with open("mappings/so.sssom.tsv", "w") as fh:
        fh.write(HEADER)
        fh.write("\t".join(COLUMNS) + "\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")

    from collections import Counter
    by_pred = Counter(r[1] for r in rows)
    by_fit = Counter(r[8] for r in rows if r[8])
    n_f = sum(1 for r in rows if r[4] in pools["F"])
    n_d = len(rows) - n_f
    subj_f = len({r[4] for r in rows if r[4] in pools["F"]})
    subj_d = len({r[4] for r in rows if r[4] in pools["D"]})
    print(f"wrote mappings/so.sssom.tsv: {len(rows)} rows "
          f"({n_f} FeatureType, {n_d} DataType) over "
          f"{subj_f}/{len(pools['F'])} FeatureType and "
          f"{subj_d}/{len(pools['D'])} DataType subjects")
    print("  by predicate:")
    for k, v in by_pred.most_common():
        print(f"    {k:24s} {v}")
    print("  by element_type_fit:")
    for k, v in by_fit.most_common():
        print(f"    {k:24s} {v}")
    print(f"    {NA + ' (annotation only)':24s} "
          f"{len(RELATED) + len(NO_ELEMENT_TYPE)}")
    print(f"  permissible values annotated: {len(annotations)}")


if __name__ == "__main__":
    main()
