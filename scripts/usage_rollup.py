#!/usr/bin/env python3
"""Roll ENCODE term usage up onto live ONGA content terms.

Reads `encode-term-use-frequency/seed_term_frequency.tsv` (one row per ENCODE
output_type seed term with its file and dataset counts) and credits each row to
the live DataType / FeatureType term it resolves to:

  1. the label is a live content term label;
  2. the label is a compound term in `mappings/facet_decomposition.tsv`: walk its
     output_type / feature_type base transitively until a live label is reached
     (the same chained resolution as check_roundtrip.py's facet round-trip);
  3. the label is ejected to an external ontology by
     `mappings/scope_delegations.tsv`: recorded under the top-level `delegated`
     key, not credited to the content base;
  4. otherwise the label is resolved through `curation/term_crosswalk.json`
     (former and retired labels), following a retired id to its live successor.

Anything left over is listed under `unresolved`.

Output `curation/usage.json` (generated, tracked):
  {sid: {encode_files, encode_datasets, contributing_seed_terms}, ...,
   delegated: {...}, unresolved: [...]}
Every live content term gets an entry, including zero-usage ones.

  python scripts/usage_rollup.py           # write curation/usage.json
  python scripts/usage_rollup.py --check   # exit 1 if it would change
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_TSV = ROOT / "encode-term-use-frequency" / "seed_term_frequency.tsv"
FACET_TSV = ROOT / "mappings" / "facet_decomposition.tsv"
SCOPE_TSV = ROOT / "mappings" / "scope_delegations.tsv"
SUBJECTS = ROOT / "curation" / "subjects.json"
CROSSWALK = ROOT / "curation" / "term_crosswalk.json"
OUT = ROOT / "curation" / "usage.json"

CONTENT_ENUMS = ("DataType", "FeatureType")


def _tsv(path):
    with open(path) as fh:
        return list(csv.DictReader(
            (line for line in fh if not line.startswith("#")), delimiter="\t"))


def _base(row):
    return (row.get("output_type") or "").strip() or (row.get("feature_type") or "").strip()


def build():
    subjects = list(json.loads(SUBJECTS.read_text())["subjects"].values())
    live = {}  # label -> sid, content terms only
    for s in subjects:
        if s["kind"] == "term" and not s.get("retired") and s.get("enum") in CONTENT_ENUMS:
            live[s["label"]] = s["sid"]
    crosswalk = json.loads(CROSSWALK.read_text())["labels"]
    # A retired id's payload carries its successor(s), |-joined; follow the first.
    replaced_by = {s["sid"]: "term:" + s["payload"]["replaced_by"].split("|")[0]
                   for s in subjects
                   if s["kind"] == "term" and s.get("retired") and s["payload"].get("replaced_by")}

    def resolve_legacy(label):
        """Former/retired label -> live sid, following retired ids to their successor."""
        tid = crosswalk.get(label)
        sid, seen = (f"term:{tid}" if tid else None), set()
        while sid and sid not in live.values() and sid not in seen:
            seen.add(sid)
            sid = replaced_by.get(sid)
        return sid

    facet = {r["encode_term"]: r for r in _tsv(FACET_TSV)}
    scope = {r["encode_term"]: r for r in _tsv(SCOPE_TSV)}

    def resolve(label):
        """-> ('term', sid) | ('delegated', row) | (None, None)"""
        cur, seen = label, set()
        while cur not in live and cur in facet and cur not in seen:
            seen.add(cur)
            cur = _base(facet[cur])
        if cur in live:
            return "term", live[cur]
        if label in scope:
            return "delegated", scope[label]
        sid = resolve_legacy(cur)
        if sid in live.values():
            return "term", sid
        return None, None

    usage = {sid: {"encode_files": 0, "encode_datasets": 0, "contributing_seed_terms": []}
             for sid in sorted(live.values())}
    delegated, unresolved = {}, []
    for row in _tsv(SEED_TSV):
        label = row["term"].strip()
        files, datasets = int(row["file_count"] or 0), int(row["dataset_count"] or 0)
        how, target = resolve(label)
        if how == "term":
            u = usage[target]
            u["encode_files"] += files
            u["encode_datasets"] += datasets
            u["contributing_seed_terms"].append(label)
        elif how == "delegated":
            base = target["content_base"].strip()
            delegated[label] = {
                "content_base": live.get(base),
                "delegated_axis": target["delegated_axis"],
                "delegated_value": target["delegated_value"],
                "external_curie": target["external_curie"],
                "encode_files": files,
                "encode_datasets": datasets,
            }
        else:
            unresolved.append({"term": label, "encode_files": files,
                               "encode_datasets": datasets})
    for u in usage.values():
        u["contributing_seed_terms"].sort()
    out = {"_generated_by": "scripts/usage_rollup.py"}
    out.update(usage)
    out["delegated"] = dict(sorted(delegated.items()))
    out["unresolved"] = sorted(unresolved, key=lambda r: r["term"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if curation/usage.json would change")
    args = ap.parse_args()
    data = build()
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    terms = [k for k in data if k.startswith("term:")]
    used = sum(1 for k in terms if data[k]["encode_files"])
    summary = (f"usage: {len(terms)} content terms, {used} with ENCODE files, "
               f"{len(data['delegated'])} delegated, {len(data['unresolved'])} unresolved seed terms")
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"usage_rollup --check: {OUT.relative_to(ROOT)} is stale; run `make usage`")
            sys.exit(1)
        print(f"{summary} (up to date)")
        return
    OUT.write_text(text)
    print(summary)


if __name__ == "__main__":
    main()
