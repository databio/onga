#!/usr/bin/env python3
"""Apply the set/element separation to src/file_content.yaml (operation #18).

ONGA terms denote SETS of genomic elements; SO classes denote INDIVIDUAL element
types. See the ADR "ONGA terms denote sets; SO terms denote elements" and
DECISIONS.md design principle #7.

Driven by the curated tables in scripts/build_so_sssom.py (imported, so the
SSSOM file and this schema cannot state different things). In one ruamel
round-trip pass over src/file_content.yaml this script:

  1. Deletes EVERY `meaning:` key from every permissible value in both enums
     (all 48: 15 SO + 33 EDAM).
       - The 15 SO ones made the permissible value's IRI *be* the SO CURIE, so
         gen-owl relabelled, redefined and re-parented live SO classes and put
         raw SO IRIs inside the owl:unionOf list defining onga:FeatureType.
       - The 33 EDAM ones used only 24 distinct CURIEs, so `meaning:`-as-identity
         COLLAPSED 24 distinct permissible values into single OWL nodes.
     ONGA->EDAM is a legitimate set-to-set relation and stays in
     exact_mappings / close_mappings / broad_mappings -- just never in
     `meaning:`, which asserts identity. An EDAM CURIE that is not already
     recorded in one of those slots is MOVED into `exact_mappings` (the old
     `meaning:` asserted identity, so exact is the faithful landing slot);
     nothing is lost. SO CURIEs are NOT moved -- they go to the annotations.
  2. Deletes every SO CURIE from `exact_mappings`, `close_mappings` and
     `broad_mappings` (the banned SKOS predicates against SO). EDAM CURIEs stay.
     Empty slots are removed entirely.
  3. Prunes `related_mappings` down to exactly the SO ids of the RELATED table
     (this removes `peaks` -> SO:0000703, re-graded to a membership row).
     Genuine skos:relatedMatch SO CURIEs stay.
  4. Inserts `annotations: {element_type, element_type_fit}` immediately after
     `description:` on every curated permissible value. `element_type` is a
     PIPE-JOINED STRING, never a YAML list -- a list stringifies as
     "['SO:0000165', 'SO:0000167']" in gen-owl output (verified).
  5. Extends the top-level `description` (rendered as the site's About lead
     paragraph) and adds a header comment block documenting the two annotation
     keys.

This operation must not add, remove, rename or re-home a single term:
DataType 162 / FeatureType 75 is asserted before and after.

Usage:
    python scripts/apply_element_type.py
"""

import sys
from pathlib import Path

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap
except ImportError:
    print("ERROR: ruamel.yaml is required. Install with: pip install ruamel.yaml")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "embeddings"))

from build_so_sssom import (  # noqa: E402
    NO_ELEMENT_TYPE, RELATED, ENUM_NAME, element_type_annotations,
)

SCHEMA_PATH = ROOT / "src" / "file_content.yaml"

EXPECTED_DATATYPE = 162
EXPECTED_FEATURETYPE = 75

MAPPING_SLOTS = ("exact_mappings", "close_mappings", "broad_mappings")
ALL_MAPPING_SLOTS = MAPPING_SLOTS + ("related_mappings", "narrow_mappings")

DESCRIPTION_ADDENDUM = """

  Both vocabularies are **set-denoting**: a DataType or FeatureType term names a file or track whose rows are instances of some element type, not the element itself. Where every row instantiates one Sequence Ontology class, that class is recorded as the term's `element_type` annotation. ONGA is a user of SO, never a substitute for it.
"""

HEADER_MARKER = "# ANNOTATION KEYS ON PERMISSIBLE VALUES"

HEADER_COMMENT = """# ANNOTATION KEYS ON PERMISSIBLE VALUES
# -------------------------------------
# An ONGA DataType or FeatureType term names a SET of genomic elements -- a
# file, a track, a set of rows. A Sequence Ontology class names an INDIVIDUAL
# element type. ONGA never asserts identity, equivalence or hierarchy against an
# SO class (design principle #7; see the ADR "ONGA terms denote sets; SO terms
# denote elements"). Two annotation keys carry the level shift:
#
#   element_type      Pipe-separated ("|") SO CURIEs naming the class(es) the
#                     individual rows/records instantiate. MUST BE A STRING, not
#                     a YAML list -- a list stringifies as
#                     "['SO:0000165', 'SO:0000167']" in gen-owl output. One value
#                     = a homogeneous set; several = a mixed set.
#   element_type_fit  How tightly the SO class fits the members. A curation
#                     grade, not a different relation:
#                       exact           the SO class is the tight fit
#                       approximate     SO's nearest available class; imperfect
#                       broad           all members are instances but the SO
#                                       class is broader -- AN SO GAP, and the
#                                       machine-readable feed into
#                                       proposals/upstream_requests.yaml
#                       not_applicable  reviewed and found to have no SO element
#                                       type (signal values, matrices, models,
#                                       edges). Distinguishes CURATED-NONE from
#                                       NOT-YET-CURATED (an absent annotation).
#
# NEVER use `meaning:` for a cross-reference. `meaning:` sets the permissible
# value's IRI, so an SO CURIE there hijacks the SO class and a repeated EDAM
# CURIE collapses distinct terms into one OWL node. Cross-references belong in
# exact_mappings / close_mappings / broad_mappings (EDAM, set-to-set) or in
# related_mappings (SO, non-membership). Machine-generated companion file:
# mappings/so.sssom.tsv, written by scripts/build_so_sssom.py.

"""


def so_curies(values):
    return [v for v in (values or []) if str(v).startswith("SO:")]


def main():
    annotations = element_type_annotations()
    related_ok = {}
    for name, cat, oid, _c in RELATED:
        related_ok.setdefault((ENUM_NAME[cat], name), set()).add(oid)
    # The NO_ELEMENT_TYPE rationale has no SSSOM row to live in (SSSOM needs an
    # object), so it is preserved as an inline comment on the annotation.
    no_et_reason = {(ENUM_NAME[cat], name): reason
                    for name, cat, reason in NO_ELEMENT_TYPE}

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 120

    print(f"Loading {SCHEMA_PATH}...")
    data = yaml.load(SCHEMA_PATH)
    pools = {
        "DataType": data["enums"]["DataType"]["permissible_values"],
        "FeatureType": data["enums"]["FeatureType"]["permissible_values"],
    }

    start = {k: len(v) for k, v in pools.items()}
    print(f"Starting DataType count:    {start['DataType']}")
    print(f"Starting FeatureType count: {start['FeatureType']}")
    if start["DataType"] != EXPECTED_DATATYPE or start["FeatureType"] != EXPECTED_FEATURETYPE:
        print(f"ERROR: expected DataType={EXPECTED_DATATYPE} "
              f"FeatureType={EXPECTED_FEATURETYPE} before the edit")
        sys.exit(1)

    # Pre-flight: every curated term must exist in the enum it names.
    missing = [k for k in annotations if k[1] not in pools[k[0]]]
    if missing:
        for enum_name, term in missing:
            print(f"ERROR: curated term {term!r} not found in {enum_name}")
        sys.exit(1)

    n_meaning_so = n_meaning_edam = n_meaning_other = n_meaning_moved = 0
    n_so_removed = 0
    n_slots_emptied = 0
    n_related_pruned = 0
    n_annotated = 0
    touched = set()

    for enum_name, pool in pools.items():
        for term, pv in pool.items():
            if not isinstance(pv, dict):
                continue

            # 1. Delete meaning: outright, moving a non-SO CURIE that is not
            #    already recorded elsewhere into exact_mappings.
            if "meaning" in pv:
                m = str(pv["meaning"])
                if m.startswith("SO:"):
                    n_meaning_so += 1
                elif m.startswith("edam:"):
                    n_meaning_edam += 1
                else:
                    n_meaning_other += 1
                del pv["meaning"]
                if not m.startswith("SO:"):
                    already = {str(v) for slot in ALL_MAPPING_SLOTS
                               for v in (pv.get(slot) or [])}
                    if m not in already:
                        pv["exact_mappings"] = list(pv.get("exact_mappings") or []) + [m]
                        n_meaning_moved += 1
                touched.add((enum_name, term))

            # 2. Strip SO CURIEs from the banned SKOS mapping slots.
            for slot in MAPPING_SLOTS:
                if slot not in pv:
                    continue
                gone = so_curies(pv[slot])
                if not gone:
                    continue
                kept = [v for v in pv[slot] if not str(v).startswith("SO:")]
                n_so_removed += len(gone)
                touched.add((enum_name, term))
                if kept:
                    pv[slot] = kept
                else:
                    del pv[slot]
                    n_slots_emptied += 1

            # 3. Prune related_mappings to the RELATED table's SO ids.
            if "related_mappings" in pv:
                allowed = related_ok.get((enum_name, term), set())
                kept = [v for v in pv["related_mappings"]
                        if not str(v).startswith("SO:") or str(v) in allowed]
                dropped = len(pv["related_mappings"]) - len(kept)
                if dropped:
                    n_related_pruned += dropped
                    touched.add((enum_name, term))
                    if kept:
                        pv["related_mappings"] = kept
                    else:
                        del pv["related_mappings"]

            # 4. Insert annotations: immediately after description:.
            ann = annotations.get((enum_name, term))
            if ann is None:
                if "annotations" in pv:
                    del pv["annotations"]
                    touched.add((enum_name, term))
                continue
            block = CommentedMap()
            if ann.get("element_type"):
                block["element_type"] = ann["element_type"]
            block["element_type_fit"] = ann["element_type_fit"]
            reason = no_et_reason.get((enum_name, term))
            if reason:
                block.yaml_add_eol_comment(reason, "element_type_fit")
            if "annotations" in pv:
                del pv["annotations"]
            keys = list(pv.keys())
            pos = keys.index("description") + 1 if "description" in keys else 0
            pv.insert(pos, "annotations", block)
            n_annotated += 1
            touched.add((enum_name, term))

    # Guardrails: this operation must not change the term inventory.
    end = {k: len(v) for k, v in pools.items()}
    for k in pools:
        assert end[k] == start[k], f"{k} count changed: {start[k]} -> {end[k]}"
    leftover = [(e, t) for e, pool in pools.items() for t, pv in pool.items()
                if isinstance(pv, dict) and "meaning" in pv]
    assert not leftover, f"meaning: survived on {leftover}"
    leftover = [(e, t, s) for e, pool in pools.items() for t, pv in pool.items()
                if isinstance(pv, dict) for s in MAPPING_SLOTS if so_curies(pv.get(s))]
    assert not leftover, f"SO CURIE survived in a banned slot: {leftover}"

    print(f"\nWriting {SCHEMA_PATH}...")
    yaml.dump(data, SCHEMA_PATH)

    # 5. Text-level: extend the top-level description and add the header block.
    text = SCHEMA_PATH.read_text()
    anchor = ("  The same DataType can represent different FeatureTypes "
              "depending on the experiment.\n")
    if DESCRIPTION_ADDENDUM.strip() not in text:
        assert anchor in text, "description anchor not found"
        text = text.replace(anchor, anchor.rstrip("\n") + DESCRIPTION_ADDENDUM, 1)
    if HEADER_MARKER not in text:
        assert "\nenums:\n" in text, "'enums:' anchor not found"
        text = text.replace("\nenums:\n", "\n" + HEADER_COMMENT + "enums:\n", 1)
    SCHEMA_PATH.write_text(text)

    print("\n=== Summary ===")
    print(f"meaning: removed              {n_meaning_so + n_meaning_edam + n_meaning_other} "
          f"({n_meaning_so} SO, {n_meaning_edam} EDAM, {n_meaning_other} other)")
    print(f"  of which moved into exact_mappings (not already recorded)  {n_meaning_moved}")
    print(f"SO CURIEs pulled out of exact/close/broad_mappings  {n_so_removed} "
          f"({n_slots_emptied} slots removed entirely)")
    print(f"related_mappings SO CURIEs pruned (re-graded rows)  {n_related_pruned}")
    print(f"annotations: blocks added     {n_annotated}")
    print(f"permissible values touched    {len(touched)}")
    print(f"DataType:    {start['DataType']} -> {end['DataType']} (unchanged)")
    print(f"FeatureType: {start['FeatureType']} -> {end['FeatureType']} (unchanged)")


if __name__ == "__main__":
    main()
