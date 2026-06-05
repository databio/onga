#!/usr/bin/env python3
"""
Fetch ENCODE output_type usage frequencies.

Strategy
--------
The ENCODE search API (https://www.encodeproject.org/search/) returns faceted
counts. A single request with `type=File&limit=0` yields a facet for
`output_type` listing `{key, doc_count}` for the top ~200 most-used terms --
essentially a ready-made frequency table.

The facet is capped (ENCODE returns at most ~200 terms per facet), and our seed
list has 310 terms, so any seed term not present in the facet response is
queried individually with `output_type=<term>&limit=0` to get its exact file
count (which may be a small non-zero number or genuinely zero).

Outputs
-------
- raw_output_type_facet.json   : raw API response (provenance)
- output_type_frequencies.tsv  : every ENCODE output_type -> file_count (desc)
- seed_term_frequency.tsv       : 310 seed terms reconciled against ENCODE
"""

import csv
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

try:
    import requests
    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False
    import urllib.request

HERE = Path(__file__).resolve().parent
SEED_FILE = HERE.parent / "original-terms.md"
RAW_FACET = HERE / "raw_output_type_facet.json"
FREQ_TSV = HERE / "output_type_frequencies.tsv"
SEED_TSV = HERE / "seed_term_frequency.tsv"

BASE = "https://www.encodeproject.org/search/"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "onga-vocab-research/1.0 (nsheff@databio.org)",
}


class NotFound(Exception):
    """ENCODE returns HTTP 404 when a search matches zero records."""


def get_json(url):
    """GET a URL and return parsed JSON. Raises NotFound on HTTP 404."""
    if HAVE_REQUESTS:
        r = requests.get(url, headers=HEADERS, timeout=120)
        if r.status_code == 404:
            raise NotFound(url)
        r.raise_for_status()
        return r.json()
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:  # noqa: F821
        if e.code == 404:
            raise NotFound(url)
        raise


def load_seed_terms():
    terms = []
    for line in SEED_FILE.read_text().splitlines():
        m = re.match(r"^- (.+)$", line.strip())
        if m:
            terms.append(m.group(1).strip())
    return terms


def fetch_facet():
    """One request: File search with no records, returns facets."""
    url = BASE + "?type=File&format=json&limit=0"
    data = get_json(url)
    RAW_FACET.write_text(json.dumps(data, indent=2))
    facet = next(
        (f for f in data.get("facets", []) if f.get("field") == "output_type"),
        None,
    )
    if facet is None:
        raise RuntimeError("No output_type facet in API response")
    counts = {t["key"]: t["doc_count"] for t in facet["terms"]}
    return counts


def file_count_for_term(term):
    """Exact file count for a single output_type value."""
    q = urllib.parse.quote(term, safe="")
    url = BASE + f"?type=File&output_type={q}&format=json&limit=0"
    try:
        data = get_json(url)
    except NotFound:
        return 0
    return int(data.get("total", 0))


def dataset_count_for_term(term):
    """Count of datasets/experiments that have a file with this output_type."""
    q = urllib.parse.quote(term, safe="")
    url = (
        "https://www.encodeproject.org/search/"
        f"?type=Experiment&files.output_type={q}&format=json&limit=0"
    )
    try:
        data = get_json(url)
        return int(data.get("total", 0))
    except NotFound:
        return 0
    except Exception:
        return None


def main(with_datasets=False):
    seeds = load_seed_terms()
    print(f"Loaded {len(seeds)} seed terms from {SEED_FILE}")

    print("Fetching output_type facet (1 request) ...")
    facet_counts = fetch_facet()
    print(f"  facet returned {len(facet_counts)} output_type terms")

    # Any seed term not in the facet needs an individual exact count.
    missing = [s for s in seeds if s not in facet_counts]
    print(f"  {len(missing)} seed terms absent from facet; querying individually ...")
    all_counts = dict(facet_counts)
    for i, term in enumerate(missing, 1):
        c = file_count_for_term(term)
        all_counts[term] = c
        if i % 20 == 0:
            print(f"    {i}/{len(missing)} done")
        time.sleep(0.15)  # be polite
    print("  individual queries complete")

    # ---- output_type_frequencies.tsv : every ENCODE term we observed ----
    rows = sorted(all_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    with FREQ_TSV.open("w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["output_type", "file_count"])
        for k, v in rows:
            w.writerow([k, v])
    print(f"Wrote {FREQ_TSV} ({len(rows)} rows)")

    # ---- seed_term_frequency.tsv : reconciliation against the 310 seeds ----
    ds_counts = {}
    if with_datasets:
        print("Fetching dataset counts per seed term ...")
        for i, term in enumerate(seeds, 1):
            ds_counts[term] = dataset_count_for_term(term)
            time.sleep(0.15)

    with SEED_TSV.open("w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        header = ["term", "in_encode", "file_count"]
        if with_datasets:
            header.append("dataset_count")
        w.writerow(header)
        for term in sorted(seeds):
            count = all_counts.get(term, 0)
            in_encode = "yes" if count > 0 else "no"
            row = [term, in_encode, count]
            if with_datasets:
                row.append(ds_counts.get(term, ""))
            w.writerow(row)
    print(f"Wrote {SEED_TSV} ({len(seeds)} rows)")

    # ---- summary ----
    zero = [s for s in seeds if all_counts.get(s, 0) == 0]
    seed_set = set(seeds)
    not_in_seed = sorted(
        [(k, v) for k, v in all_counts.items() if k not in seed_set and v > 0],
        key=lambda kv: -kv[1],
    )
    print("\n=== SUMMARY ===")
    print(f"Seed terms total           : {len(seeds)}")
    print(f"Seed terms with ZERO usage : {len(zero)}")
    print(f"ENCODE terms not in seeds  : {len(not_in_seed)}")
    print("\nTop 10 most-used output_types:")
    for k, v in rows[:10]:
        print(f"  {v:>9,}  {k}")
    if zero:
        print(f"\nSeed terms with zero ENCODE usage ({len(zero)}):")
        for s in sorted(zero):
            print(f"  - {s}")
    if not_in_seed:
        print(f"\nENCODE output_types NOT in seed list ({len(not_in_seed)}):")
        for k, v in not_in_seed:
            print(f"  {v:>9,}  {k}")


if __name__ == "__main__":
    main(with_datasets="--datasets" in sys.argv)
