#!/usr/bin/env python3
"""Round-trip integrity check for the ONGA faceting program.

This is the enforced invariant behind the "lossless ENCODE round-trip" claim.
It asserts that the facet decomposition map and the live enums are mutually
consistent, so the curated `mappings/facet_decomposition.tsv` cannot silently
drift out of sync with `src/file_content.yaml`.

Checks:
  1. Every `src/*.yaml` parses, and every non-builtin import in `onga.yaml`
     resolves to a file.
  2. Every row in `facet_decomposition.tsv` resolves to a base that exists in
     the live enum, following chained decompositions transitively (a base may
     itself be an `encode_term` decomposed further).
  3. No compound `encode_term` from the map is still present in the enums
     (every faceted term was actually removed).
  4. Every `scope_delegations.tsv` `content_base` exists in the live enum.

(Check 5, the prose-regex comparison against `DECISIONS.md` "Current state",
is gone: that list is now a generated block, kept current by
`scripts/render_decisions.py --check`.)

The set/element invariants (operation #18, design principle #7; see the ADR
"ONGA terms denote sets; SO terms denote elements"). ONGA terms denote SETS of
genomic elements, SO classes denote INDIVIDUAL element types, so ONGA never
asserts identity, equivalence or hierarchy against an SO class:

  6. Opaque term ids. Every permissible value in every enum in `src/` has
     `meaning: onga:ONGA_NNNNNNN` and nothing else there (`meaning:` sets the
     value's IRI, so an external CURIE would HIJACK that class or COLLAPSE
     distinct values into one OWL node). Ids are unique across `src/`, the live
     ids equal the `live` rows of `curation/term_ids.tsv`, every `onga:` CURIE
     in a value's `see_also` is a live id, and every `subject_id` in
     `mappings/*.sssom.tsv` is a live id whose `subject_label` is its label.
  7. No SO CURIE appears in `exact_mappings`, `close_mappings` or
     `broad_mappings` on any permissible value in `src/`, except the SO
     sequence attributes (`mappings/policy.yaml` sequence_attribute_so).
  8. `mappings/so.sssom.tsv` uses no `skos:exactMatch` / `closeMatch` /
     `broadMatch`, except against the whitelisted SO classes that are themselves
     set-denoting, or the SO sequence attributes (`mappings/policy.yaml`).
  9. Every `element_type` annotation CURIE resolves to a live, non-obsolete SO
     id in `embeddings/data/ontologies/so.obo`, and every `element_type_fit`
     value is one of the four allowed strings.
 10. `src/*.yaml` enum values are exactly the projection of `mappings/*.sssom.tsv`
     (`scripts/project_mappings.py --check`): the SSSOM files are the source of
     truth, and the mapping slots and `annotations:` blocks are generated.

Checks 7-9 read the policy (banned predicates, set-denoting SO whitelist,
sequence attributes, fit grades) from `mappings/policy.yaml`.

Exit code 0 = all invariants hold; non-zero = at least one failed (details
printed). Wire into CI / `make test`. Checks 1-9 are stdlib + pyyaml; check 10
runs the projector, which needs ruamel.yaml. No LinkML needed.
"""
import csv
import glob
import os
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from workbench import ids  # noqa: E402
from workbench.mappings import (  # noqa: E402
    HAS_ELEMENT_TYPE, NO_TERM_FOUND, SubjectError, all_rows, load_policy,
    skos_licensed_so, subject_term,
)

_POLICY = load_policy()
FITS = _POLICY["fits"]
SET_DENOTING_SO = _POLICY["set_denoting_so"]
ATTRIBUTE_SO = _POLICY["sequence_attribute_so"]
LICENSED_SO = skos_licensed_so(_POLICY)
BANNED_SKOS = _POLICY["banned_skos"]
SRC = os.path.join(ROOT, "src", "file_content.yaml")
ONGA = os.path.join(ROOT, "src", "onga.yaml")
FACET_TSV = os.path.join(ROOT, "mappings", "facet_decomposition.tsv")
SO_TSV = os.path.join(ROOT, "mappings", "so.sssom.tsv")
SO_OBO = os.path.join(ROOT, "embeddings", "data", "ontologies", "so.obo")
MAPPING_SLOTS = ("exact_mappings", "close_mappings", "broad_mappings")
ADR = 'the ADR "ONGA terms denote sets; SO terms denote elements"'

SCOPE_TSV = os.path.join(ROOT, "mappings", "scope_delegations.tsv")

failures = []


def fail(msg):
    failures.append(msg)


def load_pools():
    """{enum name: {term: permissible-value body}} from src/file_content.yaml."""
    d = yaml.safe_load(open(SRC))
    return {name: d["enums"][name]["permissible_values"]
            for name in ("DataType", "FeatureType")}


def check_schemas_parse():
    for f in sorted(glob.glob(os.path.join(ROOT, "src", "*.yaml"))):
        try:
            yaml.safe_load(open(f))
        except Exception as e:  # noqa: BLE001
            fail(f"[parse] {os.path.basename(f)} does not parse: {e}")
    o = yaml.safe_load(open(ONGA))
    for imp in o.get("imports", []):
        if imp.startswith("linkml"):
            continue
        p = os.path.join(ROOT, "src", f"{imp}.yaml")
        if not os.path.exists(p):
            fail(f"[import] onga.yaml imports '{imp}' but src/{imp}.yaml is missing")


def _rows(path):
    return list(csv.DictReader(
        (l for l in open(path) if not l.startswith("#")), delimiter="\t"))


def check_facet_roundtrip(dt, ft):
    rows = _rows(FACET_TSV)
    encode_terms = {r["encode_term"] for r in rows}
    by_term = {r["encode_term"]: r for r in rows}
    for r in rows:
        base = (r.get("output_type") or "").strip() or (r.get("feature_type") or "").strip()
        pool = dt if (r.get("output_type") or "").strip() else ft
        if not base:
            fail(f"[facet] row '{r['encode_term']}' has no output_type/feature_type base")
            continue
        cur, seen = base, set()
        while cur not in pool and cur in encode_terms and cur not in seen:
            seen.add(cur)
            nxt = by_term[cur]
            cur = (nxt.get("output_type") or "").strip() or (nxt.get("feature_type") or "").strip()
        if cur not in pool:
            fail(f"[facet] '{r['encode_term']}' -> base '{base}' does not resolve in the enum")
    still = sorted(t for t in encode_terms if t in dt or t in ft)
    for s in still:
        fail(f"[facet] compound term '{s}' is still present in an enum (should be removed)")
    return len(rows)


def check_scope(dt, ft):
    if not os.path.exists(SCOPE_TSV):
        return 0
    rows = _rows(SCOPE_TSV)
    for r in rows:
        base = (r.get("content_base") or "").strip()
        if base and base not in dt and base not in ft:
            fail(f"[scope] delegation '{r.get('encode_term')}' content_base '{base}' missing from enums")
    return len(rows)


def so_rows():
    """mappings/so.sssom.tsv read BY HEADER NAME (robust to column insertion)."""
    if not os.path.exists(SO_TSV):
        return None
    return _rows(SO_TSV)


def enum_values():
    """[(module file, enum, label, body)] for every permissible value in src/."""
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "src", "*.yaml"))):
        base = os.path.basename(f)
        if base == "linkml_lint_config.yaml":
            continue
        try:
            d = yaml.safe_load(open(f))
        except Exception:  # noqa: BLE001  (reported by check_schemas_parse)
            continue
        for enum_name, enum_def in ((d or {}).get("enums") or {}).items():
            for term, pv in ((enum_def or {}).get("permissible_values") or {}).items():
                out.append((base, enum_name, term, pv if isinstance(pv, dict) else {}))
    return out


def check_term_ids(values):
    """Check 6: every value carries a unique onga:ONGA_NNNNNNN id matching the ledger."""
    seen = {}
    for base, enum_name, term, pv in values:
        meaning = str(pv.get("meaning") or "")
        if not ids.MEANING_RE.match(meaning):
            fail(f"[term-id] {base} {enum_name} '{term}' has meaning: {meaning or None!r}; "
                 f"every permissible value must carry its permanent id as "
                 f"`meaning: onga:ONGA_NNNNNNN` (see curation/term_ids.tsv). An "
                 f"external CURIE there would hijack that class or collapse "
                 f"distinct values into one OWL node; cross-references are SSSOM "
                 f"rows. See {ADR}.")
            continue
        tid = meaning.split(":", 1)[1]
        if tid in seen:
            fail(f"[term-id] {tid} is on both {seen[tid]} and {enum_name} '{term}'")
        seen[tid] = f"{enum_name} '{term}'"
    ledger = ids.live_ids()
    for tid in sorted(set(seen) - ledger):
        fail(f"[term-id] {tid} ({seen[tid]}) is not a live row in curation/term_ids.tsv")
    for tid in sorted(ledger - set(seen)):
        fail(f"[term-id] curation/term_ids.tsv says {tid} is live, but no value in src/ has it")
    for base, enum_name, term, pv in values:
        for ref in pv.get("see_also") or []:
            ref = str(ref)
            if ref.startswith("onga:") and ref.split(":", 1)[1] not in seen:
                fail(f"[term-id] {enum_name} '{term}' see_also {ref} is not a live "
                     f"term id (write the target's onga:ONGA_NNNNNNN)")
    terms = {t.id: t for t in ids.schema_terms() if t.id}
    for fname, r in all_rows():
        try:
            subject_term(r, terms)
        except SubjectError as e:
            fail(f"[term-id] mappings/{fname}: {e}")
    return len(seen)


def check_no_so_in_skos_slots(values):
    """Check 7: no SO CURIE in exact/close/broad_mappings, except sequence attributes."""
    for base, enum_name, term, pv in values:
        for slot in MAPPING_SLOTS:
            for v in (pv.get(slot) or []):
                if str(v).startswith("SO:") and str(v) not in ATTRIBUTE_SO:
                    fail(f"[so-skos] {base} {enum_name} '{term}' has {v} in {slot}. "
                         f"ONGA terms denote SETS and SO classes denote "
                         f"ELEMENTS, so exact/close/broadMatch are not "
                         f"licensed. Use an element_type annotation. See {ADR}.")


def check_so_predicates(rows):
    """Check 8: no banned SKOS predicate against a non-set-denoting SO class."""
    if rows is None:
        return
    for r in rows:
        pred, obj = r["predicate_id"], r["object_id"]
        if pred in BANNED_SKOS and obj not in LICENSED_SO:
            fail(f"[so-predicate] '{r['subject_label']}' -> {obj} uses {pred}. "
                 f"Only {sorted(SET_DENOTING_SO)} (set-denoting) and "
                 f"{sorted(ATTRIBUTE_SO)} (sequence attributes) are whitelisted. "
                 f"Use {HAS_ELEMENT_TYPE} with an "
                 f"element_type_fit grade, or skos:relatedMatch. See {ADR}.")
        if pred not in BANNED_SKOS and pred not in (HAS_ELEMENT_TYPE, "skos:relatedMatch"):
            fail(f"[so-predicate] '{r['subject_label']}' -> {obj} uses unknown "
                 f"predicate {pred}")


def live_so_ids():
    """Non-obsolete SO ids from so.obo, via a tiny stdlib stanza scan."""
    if not os.path.exists(SO_OBO):
        return None
    ids, cur, obsolete = set(), None, False
    with open(SO_OBO) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("["):
                if cur and not obsolete:
                    ids.add(cur)
                cur, obsolete = None, False
            elif line.startswith("id: "):
                cur = line[4:].strip()
            elif line.startswith("is_obsolete: true"):
                obsolete = True
    if cur and not obsolete:
        ids.add(cur)
    return ids


def check_annotations(pools):
    """Check 9: element_type CURIEs resolve; element_type_fit is in range."""
    so = live_so_ids()
    if so is None:
        fail(f"[annotation] {SO_OBO} is missing; cannot verify element_type CURIEs")
    for enum_name, pool in pools.items():
        for term, pv in pool.items():
            ann = (pv or {}).get("annotations") if isinstance(pv, dict) else None
            if not ann:
                continue
            fit = ann.get("element_type_fit")
            if fit is None:
                fail(f"[annotation] {enum_name} '{term}' has annotations but no "
                     f"element_type_fit")
            elif fit not in FITS:
                fail(f"[annotation] {enum_name} '{term}' element_type_fit={fit!r} "
                     f"is not one of {sorted(FITS)}")
            et = ann.get("element_type")
            if et is None:
                continue
            if not isinstance(et, str):
                fail(f"[annotation] {enum_name} '{term}' element_type must be a "
                     f"pipe-joined STRING, not {type(et).__name__} (a YAML list "
                     f"stringifies badly in gen-owl output)")
                continue
            for curie in et.split("|"):
                if not curie.startswith("SO:"):
                    fail(f"[annotation] {enum_name} '{term}' element_type {curie!r} "
                         f"is not an SO CURIE")
                elif so is not None and curie not in so:
                    fail(f"[annotation] {enum_name} '{term}' element_type {curie} "
                         f"is not a live, non-obsolete SO id")


def check_projection():
    """Check 10: the src/*.yaml enum values are exactly the projection of the SSSOM files."""
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "project_mappings.py"), "--check"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        out = (proc.stdout + proc.stderr).strip()
        fail("[agree] src/*.yaml does not match the projection of "
             "mappings/*.sssom.tsv (`python scripts/project_mappings.py --check`):\n"
             + out)


def main():
    pools = load_pools()
    dt = set(pools["DataType"])
    ft = set(pools["FeatureType"])
    rows = so_rows()
    check_schemas_parse()
    n_facet = check_facet_roundtrip(dt, ft)
    n_scope = check_scope(dt, ft)
    values = enum_values()
    n_ids = check_term_ids(values)
    check_no_so_in_skos_slots(values)
    check_so_predicates(rows)
    check_annotations(pools)
    check_projection()
    if failures:
        print(f"ROUND-TRIP CHECK FAILED ({len(failures)} issue(s)):")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    n_et = sum(1 for r in (rows or []) if r["predicate_id"] == HAS_ELEMENT_TYPE
               and r["object_id"] != NO_TERM_FOUND)
    n_rel = sum(1 for r in (rows or []) if r["predicate_id"] == "skos:relatedMatch")
    n_s2s = sum(1 for r in (rows or []) if r["predicate_id"] in BANNED_SKOS
                and r["object_id"] in SET_DENOTING_SO)
    n_attr = sum(1 for r in (rows or []) if r["predicate_id"] in BANNED_SKOS
                 and r["object_id"] in ATTRIBUTE_SO)
    print(
        f"Round-trip OK: DataType={len(dt)} FeatureType={len(ft)} "
        f"total={len(dt) + len(ft)}; {n_facet} facet rows, {n_scope} scope "
        f"delegations, 0 dangling, 0 compound terms remaining."
    )
    print(
        f"Term ids OK: {n_ids} values carry unique onga:ONGA_ ids matching "
        f"curation/term_ids.tsv; every SSSOM subject_id and see_also is a live id."
    )
    print(
        f"Set/element OK: 0 SO element types in exact/close/broad_mappings; "
        f"so.sssom.tsv {n_et} {HAS_ELEMENT_TYPE} + {n_rel} skos:relatedMatch + "
        f"{n_s2s} whitelisted set-to-set + {n_attr} sequence-attribute rows, all "
        f"agreeing with the annotations: blocks."
    )


if __name__ == "__main__":
    main()
