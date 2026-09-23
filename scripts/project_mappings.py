#!/usr/bin/env python3
"""Project mappings/*.sssom.tsv onto the permissible values in src/*.yaml.

The SSSOM files are the source of truth for term-level mappings (data-first
ADR). The LinkML mapping slots and the set/element annotations on every enum
permissible value are generated from them here and are never hand-edited:

  skos:* rows (EDAM, PATO, SO skos:relatedMatch, and SO sequence attributes)
      -> exact_ / close_ / broad_ / narrow_ / related_mappings
  onga:has_element_type rows (SO)
      -> annotations.element_type (pipe-joined SO CURIEs) + element_type_fit
  onga:has_element_type -> sssom:NoTermFound
      -> element_type_fit: not_applicable, no element_type
  SO skos:relatedMatch rows on a subject with no has_element_type row
      -> element_type_fit: not_applicable

Not projected: a SKOS exact/close/broad/narrow row against a set-denoting SO
class (mappings/policy.yaml). SO CURIEs are banned from the LinkML
exact/close/broad slots except for sequence attributes (check_roundtrip.py
check 7), so those rows live in SSSOM and in the generated OWL only.

Rows with `predicate_modifier: Not` are negations: they never project, and they
are the only thing that licenses removing an existing mapping from the YAML. A
YAML mapping or element_type annotation with no supporting TSV row is an ERROR,
never a silent deletion.

Subjects resolve by `subject_id` (onga:ONGA_NNNNNNN, the value's `meaning:`);
a `subject_label` that disagrees with the live label is an error.

Usage:
    python scripts/project_mappings.py           # rewrite src/*.yaml
    python scripts/project_mappings.py --check   # write nothing; exit 1 if it would change
"""
import argparse
import difflib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ruamel.yaml.comments import CommentedMap, CommentedSeq  # noqa: E402

from workbench import ids, yamlio  # noqa: E402
from workbench.mappings import (  # noqa: E402
    HAS_ELEMENT_TYPE, NO_TERM_FOUND, RELATED_MATCH, ROOT, SKOS_SLOT, SubjectError,
    all_rows, is_negated, load_policy, subject_term,
)

ANNOTATION_KEYS = ("element_type", "element_type_fit")
TRAILING_KEYS = ("in_subset", "keywords", "see_also")


class ProjectionError(Exception):
    pass


def load_pools():
    """({module: Doc}, {term id: (module, enum, label)}) for every module with enums."""
    docs, where = {}, {}
    for mod in ids.enum_modules():
        path = ids.SRC / f"{mod}.yaml"
        doc = yamlio.load(path)
        enums = doc.data.get("enums") or {}
        if not enums:
            continue
        docs[mod] = doc
        for enum_name, enum_def in enums.items():
            for label, pv in enum_def["permissible_values"].items():
                meaning = str((pv or {}).get("meaning") or "")
                if not ids.MEANING_RE.match(meaning):
                    raise ProjectionError(f"{mod}.yaml {enum_name} {label!r} has no "
                                          f"`meaning: onga:ONGA_NNNNNNN` id")
                tid = meaning.split(":", 1)[1]
                if tid in where:
                    raise ProjectionError(f"id {tid} is on both {where[tid]} and "
                                          f"{(mod, enum_name, label)}")
                where[tid] = (mod, enum_name, label)
    return docs, where


def desired_state(where, policy):
    """{term id: {"slots": {slot: [curie]}, "negated": {(slot, curie)},
    "element_type": [SO ids] | None, "fit": str | None, "reason": str}}"""
    errs = []
    terms = {tid: ids.Term(tid, m, e, lbl) for tid, (m, e, lbl) in where.items()}
    licensed = policy["set_denoting_so"]

    state = {}

    def rec(key):
        return state.setdefault(key, {"slots": {}, "negated": set(), "so": [],
                                      "fit": None, "none": None, "related_so": False})

    for fname, r in all_rows():
        try:
            term = subject_term(r, terms)
        except SubjectError as e:
            errs.append(f"{fname}: {e}")
            continue
        key, label = term.id, term.label
        pred, obj = r["predicate_id"], r["object_id"]
        s = rec(key)
        if pred == HAS_ELEMENT_TYPE:
            if is_negated(r):
                continue
            fit = r.get("element_type_fit", "")
            if s["fit"] is not None and s["fit"] != fit:
                errs.append(f"{fname}: {term.enum} {label!r} has conflicting "
                            f"element_type_fit {s['fit']!r} vs {fit!r}")
            s["fit"] = fit
            if obj == NO_TERM_FOUND:
                s["none"] = r.get("comment", "")
            elif obj not in s["so"]:
                s["so"].append(obj)
        elif pred in SKOS_SLOT:
            slot = SKOS_SLOT[pred]
            if obj in licensed and pred in policy["banned_skos"]:
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
        name = f"{terms[key].enum} {terms[key].label!r}"
        if s["none"] is not None and s["so"]:
            errs.append(f"{name} has both sssom:NoTermFound and SO "
                        f"element types {s['so']}")
        if s["related_so"] and (s["so"] or s["none"] is not None):
            errs.append(f"{name} is both a membership row and an SO "
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


def project(docs, where, state):
    """Apply `state` to the ruamel docs in place."""
    errs = []
    empty = {"slots": {}, "negated": set(), "element_type": None, "fit": None, "none": None}
    for tid, (mod, enum_name, term) in where.items():
        pv = docs[mod].data["enums"][enum_name]["permissible_values"][term]
        want = state.get(tid, empty)

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
            if target:
                seq = CommentedSeq(target)
                if slot in pv:
                    pv[slot] = seq
                else:
                    # House order: description, meaning, annotations, *_mappings, in_subset, ...
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
            continue
        if ann is None:
            ann = CommentedMap()
            keys = list(pv.keys())
            # House order: description, meaning, annotations, *_mappings, ...
            pos = max((keys.index(k) + 1 for k in ("description", "meaning") if k in keys),
                      default=0)
            pv.insert(pos, "annotations", ann)
        for k in ANNOTATION_KEYS:
            if k in ann:
                del ann[k]
        if want_et:
            ann.insert(0, "element_type", want_et)
        ann.insert(1 if want_et else 0, "element_type_fit", want_fit)
        if want["none"]:
            ann.yaml_add_eol_comment(want["none"], "element_type_fit")
    if errs:
        raise ProjectionError("\n".join(errs))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="write nothing; exit non-zero if the projection would change src/")
    args = ap.parse_args()

    try:
        docs, where = load_pools()
        state = desired_state(where, load_policy())
        project(docs, where, state)
    except ProjectionError as e:
        print(f"PROJECTION FAILED:\n  " + str(e).replace("\n", "\n  "))
        sys.exit(1)

    stale = []
    for mod, doc in docs.items():
        path = ids.SRC / f"{mod}.yaml"
        before, after = path.read_text(), yamlio.dumps(doc)
        if after == before:
            continue
        rel = path.relative_to(ROOT)
        stale.append(str(rel))
        if args.check:
            sys.stdout.writelines(difflib.unified_diff(
                before.splitlines(True), after.splitlines(True),
                f"a/{rel}", f"b/{rel}", n=1))
        else:
            yamlio.dump(doc, path)

    if args.check:
        if stale:
            print(f"project-mappings check FAILED: {', '.join(stale)} disagree with "
                  f"mappings/*.sssom.tsv; run `make mappings`")
            sys.exit(1)
        print(f"project-mappings OK: src/ agrees with mappings/*.sssom.tsv "
              f"({len(where)} values in {len(docs)} modules)")
        return
    print(f"projected mappings/*.sssom.tsv onto src/: "
          f"{', '.join(stale) or 'no changes'}")


if __name__ == "__main__":
    main()
