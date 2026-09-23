#!/usr/bin/env python3
"""Project mappings/*.sssom.tsv onto the DataType / FeatureType values in src/file_content.yaml.

The SSSOM files are the source of truth for term-level mappings (data-first
ADR). The LinkML mapping slots and the set/element annotations on each
DataType / FeatureType permissible value are generated from them here and are
never hand-edited:

  skos:* rows (EDAM, and SO skos:relatedMatch)
      -> exact_ / close_ / broad_ / narrow_ / related_mappings
  onga:has_element_type rows (SO)
      -> annotations.element_type (pipe-joined SO CURIEs) + element_type_fit
  onga:has_element_type -> sssom:NoTermFound
      -> element_type_fit: not_applicable, no element_type
  SO skos:relatedMatch rows on a subject with no has_element_type row
      -> element_type_fit: not_applicable

Not projected: a SKOS exact/close/broad/narrow row against SO. Policy allows
those only for the set-denoting SO classes (mappings/policy.yaml), and SO CURIEs
are banned from the LinkML exact/close/broad slots (check_roundtrip.py check 7),
so those rows live in SSSOM and in the generated OWL only.

Rows with `predicate_modifier: Not` are negations: they never project, and they
are the only thing that licenses removing an existing mapping from the YAML. A
YAML mapping or element_type annotation with no supporting TSV row is an ERROR,
never a silent deletion.

Subjects resolve by `subject_label` against the live enums.

Usage:
    python scripts/project_mappings.py           # rewrite src/file_content.yaml
    python scripts/project_mappings.py --check   # write nothing; exit 1 if it would change
"""
import argparse
import difflib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ruamel.yaml.comments import CommentedMap, CommentedSeq  # noqa: E402

from workbench import yamlio  # noqa: E402
from workbench.mappings import (  # noqa: E402
    CONTENT, CONTENT_ENUMS, HAS_ELEMENT_TYPE, NO_TERM_FOUND, RELATED_MATCH,
    ROOT, SKOS_SLOT, all_rows, is_negated, load_policy,
)

ANNOTATION_KEYS = ("element_type", "element_type_fit")
TRAILING_KEYS = ("in_subset", "keywords", "see_also")


class ProjectionError(Exception):
    pass


def desired_state(pools, policy):
    """{(enum, term): {"slots": {slot: [curie]}, "negated": {(slot, curie)},
    "element_type": [SO ids] | None, "fit": str | None, "reason": str}}"""
    errs = []
    enum_of = {}
    for enum_name in CONTENT_ENUMS:
        for term in pools[enum_name]:
            if term in enum_of:
                errs.append(f"term {term!r} is in both DataType and FeatureType; "
                            f"subjects cannot resolve by label")
            enum_of[term] = enum_name

    state = {}

    def rec(key):
        return state.setdefault(key, {"slots": {}, "negated": set(), "so": [],
                                      "fit": None, "none": None, "related_so": False})

    for fname, r in all_rows():
        label = r.get("subject_label", "")
        if label not in enum_of:
            errs.append(f"{fname}: subject_label {label!r} is not a live "
                        f"DataType/FeatureType value")
            continue
        key = (enum_of[label], label)
        pred, obj = r["predicate_id"], r["object_id"]
        s = rec(key)
        if pred == HAS_ELEMENT_TYPE:
            if is_negated(r):
                continue
            fit = r.get("element_type_fit", "")
            if s["fit"] is not None and s["fit"] != fit:
                errs.append(f"{fname}: {key[0]} {label!r} has conflicting "
                            f"element_type_fit {s['fit']!r} vs {fit!r}")
            s["fit"] = fit
            if obj == NO_TERM_FOUND:
                s["none"] = r.get("comment", "")
            elif obj not in s["so"]:
                s["so"].append(obj)
        elif pred in SKOS_SLOT:
            slot = SKOS_SLOT[pred]
            if obj.startswith("SO:") and pred in policy["banned_skos"]:
                continue  # set-to-set SO rows: SSSOM + OWL only (see docstring)
            if is_negated(r):
                s["negated"].add((slot, obj))
                continue
            if obj.startswith("SO:") and pred == RELATED_MATCH:
                s["related_so"] = True
            lst = s["slots"].setdefault(slot, [])
            if obj not in lst:
                lst.append(obj)
        else:
            errs.append(f"{fname}: {label!r} uses predicate {pred!r}, which has "
                        f"no projection")

    for key, s in state.items():
        if s["none"] is not None and s["so"]:
            errs.append(f"{key[0]} {key[1]!r} has both sssom:NoTermFound and SO "
                        f"element types {s['so']}")
        if s["related_so"] and (s["so"] or s["none"] is not None):
            errs.append(f"{key[0]} {key[1]!r} is both a membership row and an SO "
                        f"skos:relatedMatch row")
        if s["so"] or s["none"] is not None:
            s["element_type"] = "|".join(s["so"]) or None
        elif s["related_so"]:
            s["fit"], s["element_type"] = "not_applicable", None
        else:
            s["fit"], s["element_type"] = None, None
    if errs:
        raise ProjectionError("\n".join(errs))
    return state


def _curies(value):
    return [str(v) for v in (value or [])]


def project(pools, state):
    """Apply `state` to the ruamel pools in place. Returns the number of values changed."""
    errs, changed = [], 0
    empty = {"slots": {}, "negated": set(), "element_type": None, "fit": None, "none": None}
    for enum_name in CONTENT_ENUMS:
        for term, pv in pools[enum_name].items():
            want = state.get((enum_name, term), empty)
            if pv is None:
                if not want["slots"] and want["fit"] is None:
                    continue
                pv = pools[enum_name][term] = CommentedMap()
            touched = False

            # 1. The SKOS mapping slots.
            for slot in sorted(set(SKOS_SLOT.values())):
                have = _curies(pv.get(slot))
                target = want["slots"].get(slot, [])
                orphan = [c for c in have if c not in target
                          and (slot, c) not in want["negated"]]
                if orphan:
                    errs.append(f"{enum_name} {term!r} has {slot} {orphan} with no "
                                f"row in mappings/*.sssom.tsv. Add a row (or a "
                                f"predicate_modifier Not row to remove it).")
                    continue
                if set(have) == set(target):
                    continue
                touched = True
                if target:
                    seq = CommentedSeq(target)
                    if slot in pv:
                        pv[slot] = seq
                    else:
                        # House order: description, annotations, *_mappings, in_subset, ...
                        keys = list(pv.keys())
                        pos = next((i for i, k in enumerate(keys) if k in TRAILING_KEYS),
                                   len(keys))
                        pv.insert(pos, slot, seq)
                else:
                    del pv[slot]

            # 2. The set/element annotations.
            ann = pv.get("annotations")
            have_et = str(ann["element_type"]) if ann and "element_type" in ann else None
            have_fit = ann.get("element_type_fit") if ann else None
            want_et, want_fit = want["element_type"], want["fit"]
            if want_fit is None and (have_et or have_fit):
                errs.append(f"{enum_name} {term!r} has element_type annotations "
                            f"({have_et!r}, {have_fit!r}) with no row in "
                            f"mappings/so.sssom.tsv")
                continue
            same_et = (set((have_et or "").split("|")) == set((want_et or "").split("|")))
            if same_et and have_fit == want_fit:
                if touched:
                    changed += 1
                continue
            touched = True
            if ann is None:
                ann = CommentedMap()
                keys = list(pv.keys())
                pos = keys.index("description") + 1 if "description" in keys else 0
                pv.insert(pos, "annotations", ann)
            for k in ANNOTATION_KEYS:
                if k in ann:
                    del ann[k]
            if want_et:
                ann.insert(0, "element_type", want_et)
            ann.insert(1 if want_et else 0, "element_type_fit", want_fit)
            if want["none"]:
                ann.yaml_add_eol_comment(want["none"], "element_type_fit")
            changed += 1
    if errs:
        raise ProjectionError("\n".join(errs))
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="write nothing; exit non-zero if the projection would change src/")
    args = ap.parse_args()

    doc = yamlio.load(CONTENT)
    pools = {e: doc.data["enums"][e]["permissible_values"] for e in CONTENT_ENUMS}
    before = CONTENT.read_text()
    try:
        state = desired_state(pools, load_policy())
        n = project(pools, state)
    except ProjectionError as e:
        print(f"PROJECTION FAILED:\n  " + str(e).replace("\n", "\n  "))
        sys.exit(1)
    after = yamlio.dumps(doc)
    rel = CONTENT.relative_to(ROOT)

    if args.check:
        if after != before:
            sys.stdout.writelines(difflib.unified_diff(
                before.splitlines(True), after.splitlines(True),
                f"a/{rel}", f"b/{rel}", n=1))
            print(f"project-mappings check FAILED: {n} value(s) in {rel} disagree "
                  f"with mappings/*.sssom.tsv; run `make mappings`")
            sys.exit(1)
        print(f"project-mappings OK: {rel} agrees with mappings/*.sssom.tsv")
        return
    if after != before:
        yamlio.dump(doc, CONTENT)
    print(f"projected mappings/*.sssom.tsv onto {rel}: {n} value(s) changed")


if __name__ == "__main__":
    main()
