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
  5. The DataType / FeatureType counts match the numbers recorded in
     `DECISIONS.md` "Current state" (catches forgotten doc updates).

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
SRC = os.path.join(ROOT, "src", "file_content.yaml")
ONGA = os.path.join(ROOT, "src", "onga.yaml")
FACET_TSV = os.path.join(ROOT, "mappings", "facet_decomposition.tsv")
SCOPE_TSV = os.path.join(ROOT, "mappings", "scope_delegations.tsv")
DECISIONS = os.path.join(ROOT, "DECISIONS.md")

failures = []


def fail(msg):
    failures.append(msg)


def load_enums():
    d = yaml.safe_load(open(SRC))
    dt = set(d["enums"]["DataType"]["permissible_values"])
    ft = set(d["enums"]["FeatureType"]["permissible_values"])
    return dt, ft


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


def check_counts(dt, ft):
    text = open(DECISIONS).read()
    m_dt = re.search(r"\*\*DataType:\*\*\s*(\d+)\s*terms", text)
    m_ft = re.search(r"\*\*FeatureType:\*\*\s*(\d+)\s*terms", text)
    if m_dt and int(m_dt.group(1)) != len(dt):
        fail(f"[counts] DECISIONS says DataType={m_dt.group(1)} but enum has {len(dt)}")
    if m_ft and int(m_ft.group(1)) != len(ft):
        fail(f"[counts] DECISIONS says FeatureType={m_ft.group(1)} but enum has {len(ft)}")


def main():
    dt, ft = load_enums()
    check_schemas_parse()
    n_facet = check_facet_roundtrip(dt, ft)
    n_scope = check_scope(dt, ft)
    check_counts(dt, ft)
    if failures:
        print(f"ROUND-TRIP CHECK FAILED ({len(failures)} issue(s)):")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print(
        f"Round-trip OK: DataType={len(dt)} FeatureType={len(ft)} "
        f"total={len(dt) + len(ft)}; {n_facet} facet rows, {n_scope} scope "
        f"delegations, 0 dangling, 0 compound terms remaining."
    )


if __name__ == "__main__":
    main()
