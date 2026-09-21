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
  5. The DataType / FeatureType counts and the SO mapping-set counts match the
     numbers recorded in `DECISIONS.md` "Current state" (catches forgotten doc
     updates).

The set/element invariants (operation #18, design principle #7; see the ADR
"ONGA terms denote sets; SO terms denote elements"). ONGA terms denote SETS of
genomic elements, SO classes denote INDIVIDUAL element types, so ONGA never
asserts identity, equivalence or hierarchy against an SO class:

  6. No permissible value in either enum has a `meaning:` key. `meaning:` sets
     the value's IRI, so an SO CURIE there HIJACKS the SO class (gen-owl
     relabels, redefines and re-parents it) and a repeated EDAM CURIE COLLAPSES
     distinct permissible values into a single OWL node.
  7. No SO CURIE appears in `exact_mappings`, `close_mappings` or
     `broad_mappings` in `src/file_content.yaml`.
  8. `mappings/so.sssom.tsv` uses no `skos:exactMatch` / `closeMatch` /
     `broadMatch`, except against the whitelisted SO classes that are themselves
     set-denoting.
  9. Every `element_type` annotation CURIE resolves to a live, non-obsolete SO
     id in `embeddings/data/ontologies/so.obo`, and every `element_type_fit`
     value is one of the four allowed strings.
 10. `mappings/so.sssom.tsv` and the `annotations:` blocks agree in both
     directions (the two-sources-of-truth guard).

Exit code 0 = all invariants hold; non-zero = at least one failed (details
printed). Wire into CI / `make test`. Pure-stdlib + pyyaml; no LinkML needed.
"""
import csv
import glob
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

# The curated SO tables are the single source of truth for the whitelist, the
# allowed fit grades, and the expected annotations. build_so_sssom only needs
# pyyaml plus the stdlib-only OBO reader, so `make test` stays dependency-light.
from build_so_sssom import (  # noqa: E402
    FITS, SET_DENOTING_SO, BANNED_SKOS, HAS_ELEMENT_TYPE,
    element_type_annotations,
)
SRC = os.path.join(ROOT, "src", "file_content.yaml")
ONGA = os.path.join(ROOT, "src", "onga.yaml")
FACET_TSV = os.path.join(ROOT, "mappings", "facet_decomposition.tsv")
SO_TSV = os.path.join(ROOT, "mappings", "so.sssom.tsv")
SO_OBO = os.path.join(ROOT, "embeddings", "data", "ontologies", "so.obo")
MAPPING_SLOTS = ("exact_mappings", "close_mappings", "broad_mappings")
ADR = 'the ADR "ONGA terms denote sets; SO terms denote elements"'

SCOPE_TSV = os.path.join(ROOT, "mappings", "scope_delegations.tsv")
DECISIONS = os.path.join(ROOT, "DECISIONS.md")

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


def check_counts(dt, ft, rows):
    """Check 5: DECISIONS.md 'Current state' vs. the live enums and mapping set."""
    text = open(DECISIONS).read()
    m_dt = re.search(r"\*\*DataType:\*\*\s*(\d+)\s*terms", text)
    m_ft = re.search(r"\*\*FeatureType:\*\*\s*(\d+)\s*terms", text)
    if m_dt and int(m_dt.group(1)) != len(dt):
        fail(f"[counts] DECISIONS says DataType={m_dt.group(1)} but enum has {len(dt)}")
    if m_ft and int(m_ft.group(1)) != len(ft):
        fail(f"[counts] DECISIONS says FeatureType={m_ft.group(1)} but enum has {len(ft)}")
    if rows is None:
        return
    live = {
        "SO element-type rows": sum(1 for r in rows
                                    if r["predicate_id"] == HAS_ELEMENT_TYPE),
        "SO relatedMatch rows": sum(1 for r in rows
                                    if r["predicate_id"] == "skos:relatedMatch"),
        "SO set-to-set rows": sum(1 for r in rows
                                  if r["predicate_id"] in BANNED_SKOS),
    }
    for label, n in live.items():
        m = re.search(r"\*\*" + re.escape(label) + r":\*\*\s*(\d+)", text)
        if m is None:
            fail(f"[counts] DECISIONS 'Current state' has no '{label}' entry "
                 f"(live value {n})")
        elif int(m.group(1)) != n:
            fail(f"[counts] DECISIONS says {label}={m.group(1)} but "
                 f"so.sssom.tsv has {n}")


def check_no_meaning(pools):
    """Check 6: `meaning:` is banned on DataType / FeatureType values."""
    for enum_name, pool in pools.items():
        for term, pv in pool.items():
            if isinstance(pv, dict) and "meaning" in pv:
                fail(f"[meaning] {enum_name} '{term}' has meaning: {pv['meaning']!r}. "
                     f"`meaning:` makes the value's IRI BE that CURIE, so an SO "
                     f"CURIE hijacks the SO class and a repeated EDAM CURIE "
                     f"collapses distinct values into one OWL node. Use "
                     f"exact/close/broad_mappings or an element_type annotation. "
                     f"See {ADR}.")


# `meaning:` is grandfathered ONLY in these files (each CURIE used exactly once
# on a facet value, so neither the hijack nor the collapse bug applies — see
# DECISIONS "Cleanup decisions"). Everything else in src/, including every
# module ported from the FGA-WG schema, is banned from using it.
MEANING_WHITELIST = {"format.yaml", "reference_build_sex.yaml"}


def check_no_meaning_all_src():
    """Check 6b: no `meaning:` key in ANY src/*.yaml enum outside the whitelist."""
    for f in sorted(glob.glob(os.path.join(ROOT, "src", "*.yaml"))):
        base = os.path.basename(f)
        if base in MEANING_WHITELIST or base == "linkml_lint_config.yaml":
            continue
        try:
            d = yaml.safe_load(open(f))
        except Exception:  # noqa: BLE001  (reported by check_schemas_parse)
            continue
        for enum_name, enum_def in ((d or {}).get("enums") or {}).items():
            for term, pv in (enum_def.get("permissible_values") or {}).items():
                if isinstance(pv, dict) and "meaning" in pv:
                    fail(f"[meaning] {base} enum {enum_name} '{term}' has "
                         f"meaning: {pv['meaning']!r}. `meaning:` is banned "
                         f"across src/ (design principle #7); use "
                         f"exact/close/broad_mappings or annotations. See {ADR}.")


def check_no_so_in_skos_slots(pools):
    """Check 7: no SO CURIE in exact_mappings / close_mappings / broad_mappings."""
    for enum_name, pool in pools.items():
        for term, pv in pool.items():
            if not isinstance(pv, dict):
                continue
            for slot in MAPPING_SLOTS:
                for v in (pv.get(slot) or []):
                    if str(v).startswith("SO:"):
                        fail(f"[so-skos] {enum_name} '{term}' has {v} in {slot}. "
                             f"ONGA terms denote SETS and SO classes denote "
                             f"ELEMENTS, so exact/close/broadMatch are not "
                             f"licensed. Use an element_type annotation. See {ADR}.")


def check_so_predicates(rows):
    """Check 8: no banned SKOS predicate against a non-set-denoting SO class."""
    if rows is None:
        return
    for r in rows:
        pred, obj = r["predicate_id"], r["object_id"]
        if pred in BANNED_SKOS and obj not in SET_DENOTING_SO:
            fail(f"[so-predicate] '{r['subject_label']}' -> {obj} uses {pred}. "
                 f"Only {sorted(SET_DENOTING_SO)} are whitelisted (they are "
                 f"themselves set-denoting). Use {HAS_ELEMENT_TYPE} with an "
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


def check_sssom_agrees(pools, rows):
    """Check 10: so.sssom.tsv and the annotations: blocks say the same thing."""
    if rows is None:
        fail("[agree] mappings/so.sssom.tsv is missing; run "
             "`python scripts/build_so_sssom.py`")
        return
    # From the TSV: subject -> the SO ids asserted with has_element_type.
    from_tsv = {}
    for r in rows:
        if r["predicate_id"] != HAS_ELEMENT_TYPE:
            continue
        label = r["subject_label"]
        enum_name = next((e for e, pool in pools.items() if label in pool), None)
        if enum_name is None:
            fail(f"[agree] so.sssom.tsv subject '{label}' is in neither enum")
            continue
        from_tsv.setdefault((enum_name, label), []).append(r["object_id"])
    # From the schema: the element_type annotations.
    from_yaml = {}
    for enum_name, pool in pools.items():
        for term, pv in pool.items():
            ann = (pv or {}).get("annotations") if isinstance(pv, dict) else None
            if ann and ann.get("element_type"):
                from_yaml[(enum_name, term)] = str(ann["element_type"]).split("|")
    for key in sorted(set(from_tsv) | set(from_yaml)):
        tsv, yml = from_tsv.get(key), from_yaml.get(key)
        if tsv is None:
            fail(f"[agree] {key[0]} '{key[1]}' has an element_type annotation "
                 f"{yml} but no {HAS_ELEMENT_TYPE} row in so.sssom.tsv")
        elif yml is None:
            fail(f"[agree] {key[0]} '{key[1]}' has {HAS_ELEMENT_TYPE} rows {tsv} "
                 f"in so.sssom.tsv but no element_type annotation")
        elif sorted(tsv) != sorted(yml):
            fail(f"[agree] {key[0]} '{key[1]}' element_type mismatch: "
                 f"so.sssom.tsv {sorted(tsv)} vs annotation {sorted(yml)}")
    # And the fit grades / not_applicable declarations implied by the curated tables.
    expected = element_type_annotations()
    for key, want in expected.items():
        pv = pools.get(key[0], {}).get(key[1])
        got = (pv or {}).get("annotations") if isinstance(pv, dict) else None
        if not got:
            fail(f"[agree] {key[0]} '{key[1]}' is curated in build_so_sssom.py but "
                 f"has no annotations: block. Run "
                 f"`python scripts/apply_element_type.py`.")
            continue
        if got.get("element_type_fit") != want["element_type_fit"]:
            fail(f"[agree] {key[0]} '{key[1]}' element_type_fit is "
                 f"{got.get('element_type_fit')!r}, curated value is "
                 f"{want['element_type_fit']!r}")


def main():
    pools = load_pools()
    dt = set(pools["DataType"])
    ft = set(pools["FeatureType"])
    rows = so_rows()
    check_schemas_parse()
    n_facet = check_facet_roundtrip(dt, ft)
    n_scope = check_scope(dt, ft)
    check_counts(dt, ft, rows)
    check_no_meaning(pools)
    check_no_meaning_all_src()
    check_no_so_in_skos_slots(pools)
    check_so_predicates(rows)
    check_annotations(pools)
    check_sssom_agrees(pools, rows)
    if failures:
        print(f"ROUND-TRIP CHECK FAILED ({len(failures)} issue(s)):")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    n_et = sum(1 for r in (rows or []) if r["predicate_id"] == HAS_ELEMENT_TYPE)
    n_rel = sum(1 for r in (rows or []) if r["predicate_id"] == "skos:relatedMatch")
    n_s2s = sum(1 for r in (rows or []) if r["predicate_id"] in BANNED_SKOS)
    print(
        f"Round-trip OK: DataType={len(dt)} FeatureType={len(ft)} "
        f"total={len(dt) + len(ft)}; {n_facet} facet rows, {n_scope} scope "
        f"delegations, 0 dangling, 0 compound terms remaining."
    )
    print(
        f"Set/element OK: 0 meaning: keys, 0 SO CURIEs in exact/close/broad_mappings; "
        f"so.sssom.tsv {n_et} {HAS_ELEMENT_TYPE} + {n_rel} skos:relatedMatch + "
        f"{n_s2s} whitelisted set-to-set rows, all agreeing with the "
        f"annotations: blocks."
    )


if __name__ == "__main__":
    main()
