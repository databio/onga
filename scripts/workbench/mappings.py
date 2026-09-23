"""Readers shared by the mapping scripts: SSSOM rows, the mapping policy, the SO ontology.

The SSSOM files in mappings/*.sssom.tsv are the source of truth for term-level
mappings. Everything here reads columns BY HEADER NAME, never by position.
Stdlib + pyyaml only, so `scripts/check_roundtrip.py` can use it too.
"""
import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MAPPINGS = ROOT / "mappings"
POLICY = MAPPINGS / "policy.yaml"
CONTENT = ROOT / "src" / "file_content.yaml"
SO_OBO = ROOT / "embeddings" / "data" / "ontologies" / "so.obo"

CONTENT_ENUMS = ("DataType", "FeatureType")
HAS_ELEMENT_TYPE = "onga:has_element_type"
RELATED_MATCH = "skos:relatedMatch"
NO_TERM_FOUND = "sssom:NoTermFound"

# SKOS predicate -> the LinkML permissible-value slot it projects onto.
SKOS_SLOT = {
    "skos:exactMatch": "exact_mappings",
    "skos:closeMatch": "close_mappings",
    "skos:broadMatch": "broad_mappings",
    "skos:narrowMatch": "narrow_mappings",
    "skos:relatedMatch": "related_mappings",
}


def sssom_files():
    return sorted(MAPPINGS.glob("*.sssom.tsv"))


def read_sssom(path):
    """Data rows of one SSSOM TSV as dicts keyed by header name (comments skipped)."""
    with open(path) as fh:
        return list(csv.DictReader(
            (line for line in fh if not line.startswith("#")), delimiter="\t"))


def all_rows():
    """[(file name, row)] over every mappings/*.sssom.tsv, in file then row order."""
    return [(p.name, r) for p in sssom_files() for r in read_sssom(p)]


def load_policy():
    p = yaml.safe_load(open(POLICY))
    return {
        "banned_skos": set(p["banned_skos"]),
        "set_denoting_so": set(p["set_denoting_so"]),
        "fits": set(p["fits"]),
        "subject_category": p["subject_category"],
        "object_category": p["object_category"],
    }


def is_negated(row):
    return (row.get("predicate_modifier") or "").strip() == "Not"


def live_so_terms():
    """{id: name} for every non-obsolete SO term in so.obo (stdlib stanza scan)."""
    if not SO_OBO.exists():
        return None
    out, cur, name, obsolete, in_term = {}, None, "", False, False

    def flush():
        if in_term and cur and not obsolete:
            out[cur] = name

    with open(SO_OBO) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("["):
                flush()
                in_term = line == "[Term]"
                cur, name, obsolete = None, "", False
            elif line.startswith("id: "):
                cur = line[4:].strip()
            elif line.startswith("name: "):
                name = line[6:].strip()
            elif line.startswith("is_obsolete: true"):
                obsolete = True
    flush()
    return out
