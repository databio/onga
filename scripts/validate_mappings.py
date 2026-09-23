#!/usr/bin/env python3
"""Validate mappings/*.sssom.tsv, the source of truth for term-level mappings.

Checks every row of every SSSOM file (by header name):
  - the subject_id is a live ONGA term id (onga:ONGA_NNNNNNN, a value's
    `meaning:`) and subject_label is that value's live label;
  - onga:has_element_type rows are about DataType / FeatureType terms only;
  - an SO object exists and is non-obsolete in embeddings/data/ontologies/so.obo,
    and its object_label is the SO name;
  - the set/element predicate policy in mappings/policy.yaml holds: against SO
    only onga:has_element_type, skos:relatedMatch, a SKOS match to a
    set-denoting SO class, or a SKOS match from a facet value to an SO sequence
    attribute; sssom:NoTermFound only on onga:has_element_type;
  - element_type_fit is set (and in range) exactly on positive
    onga:has_element_type rows, is not_applicable exactly on NoTermFound rows,
    and is consistent per subject;
  - a negated row (`predicate_modifier: Not`, a rejected suggestion) is exempt
    from the predicate policy and carries no element_type_fit;
  - a subject is never both a membership row and an SO skos:relatedMatch row;
  - no duplicate (subject, predicate, object) triple.

Exit 0 = valid. Run by `make validate-mappings`.
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workbench import ids  # noqa: E402
from workbench.mappings import (  # noqa: E402
    CONTENT_ENUMS, HAS_ELEMENT_TYPE, NO_TERM_FOUND, RELATED_MATCH, SKOS_SLOT,
    SubjectError, all_rows, live_so_terms, load_policy, skos_licensed_so, subject_term,
)

ADR = 'the ADR "ONGA terms denote sets; SO terms denote elements"'


def main():
    policy = load_policy()
    licensed = skos_licensed_so(policy)
    terms = {t.id: t for t in ids.schema_terms() if t.id}
    so = live_so_terms()
    errs = []
    if so is None:
        errs.append("embeddings/data/ontologies/so.obo is missing; cannot verify SO ids")
        so = {}

    seen = set()
    fits = defaultdict(set)
    membership, related = set(), set()
    rows = all_rows()
    for fname, r in rows:
        label = r.get("subject_label", "")
        sid = r.get("subject_id", "")
        pred, obj = r.get("predicate_id", ""), r.get("object_id", "")
        fit = r.get("element_type_fit", "") or ""
        where = f"{fname}: {sid} {label!r} {pred} {obj}"
        try:
            term = subject_term(r, terms)
        except SubjectError as e:
            errs.append(f"{where}: {e}")
            term = None
        content = term is not None and term.enum in CONTENT_ENUMS
        if pred == HAS_ELEMENT_TYPE and term is not None and not content:
            errs.append(f"{where}: {HAS_ELEMENT_TYPE} is only for DataType / "
                        f"FeatureType terms, not {term.enum}")
        mod = (r.get("predicate_modifier") or "").strip()
        if mod not in ("", "Not"):
            errs.append(f"{where}: predicate_modifier must be empty or 'Not', got {mod!r}")
        triple = (sid, pred, obj, mod)
        if triple in seen:
            errs.append(f"{where}: duplicate row")
        seen.add(triple)
        if pred not in SKOS_SLOT and pred != HAS_ELEMENT_TYPE:
            errs.append(f"{where}: unknown predicate")

        if obj == NO_TERM_FOUND:
            if pred != HAS_ELEMENT_TYPE:
                errs.append(f"{where}: {NO_TERM_FOUND} is only valid with {HAS_ELEMENT_TYPE}")
            if fit != "not_applicable":
                errs.append(f"{where}: a {NO_TERM_FOUND} row must have "
                            f"element_type_fit not_applicable, got {fit!r}")
        elif obj.startswith("SO:"):
            if obj not in so:
                errs.append(f"{where}: SO id not found or obsolete in so.obo")
            elif r.get("object_label", "") != so[obj]:
                errs.append(f"{where}: object_label {r.get('object_label')!r} is not "
                            f"the SO name {so[obj]!r}")
            attribute = obj in policy["sequence_attribute_so"]
            if pred in policy["banned_skos"] and obj not in licensed and not mod:
                errs.append(
                    f"{where}: BANNED PREDICATE. ONGA terms denote SETS and SO classes "
                    f"denote ELEMENTS, so exact/close/broad/narrowMatch are licensed only "
                    f"against the set-denoting SO classes "
                    f"{sorted(policy['set_denoting_so'])} and the SO sequence attributes "
                    f"{sorted(policy['sequence_attribute_so'])}. Use {HAS_ELEMENT_TYPE} "
                    f"with an element_type_fit grade, or {RELATED_MATCH}. See {ADR}.")
            if attribute and content:
                errs.append(f"{where}: SO sequence attributes are for facet values, "
                            f"not DataType / FeatureType terms (a set). See {ADR}.")
            if pred == HAS_ELEMENT_TYPE and not mod and fit not in policy["fits"] - {"not_applicable"}:
                errs.append(f"{where}: element_type_fit {fit!r} must be one of "
                            f"{sorted(policy['fits'] - {'not_applicable'})}")
            if mod and fit:
                errs.append(f"{where}: a negated row carries no element_type_fit")
            for col in ("subject_category", "object_category"):
                want = "" if attribute else policy[col]
                if r.get(col, "") != want:
                    errs.append(f"{where}: {col} {r.get(col)!r} is not {want!r}")
        elif pred == HAS_ELEMENT_TYPE:
            errs.append(f"{where}: {HAS_ELEMENT_TYPE} needs an SO object or {NO_TERM_FOUND}")

        if pred != HAS_ELEMENT_TYPE and fit:
            errs.append(f"{where}: element_type_fit is only for {HAS_ELEMENT_TYPE} rows")
        if pred == HAS_ELEMENT_TYPE and not mod:
            membership.add(sid)
            fits[sid].add(fit)
        if pred == RELATED_MATCH and obj.startswith("SO:") and not mod:
            related.add(sid)

    for sid, fs in sorted(fits.items()):
        if len(fs) > 1:
            errs.append(f"{sid}: conflicting element_type_fit values {sorted(fs)}")
    for sid in sorted(membership & related):
        errs.append(f"{sid}: both an element-type row and an SO {RELATED_MATCH} row")

    if errs:
        print(f"MAPPING VALIDATION FAILED ({len(errs)} issue(s)):")
        for e in errs:
            print("  -", e)
        sys.exit(1)
    by_file = defaultdict(int)
    for fname, _ in rows:
        by_file[fname] += 1
    summary = ", ".join(f"{f} {n}" for f, n in sorted(by_file.items()))
    print(f"Mappings OK: {len(rows)} rows ({summary}), "
          f"{len({r['subject_id'] for _, r in rows})} subjects")


if __name__ == "__main__":
    main()
