"""ONGA's mapping policy and term-id helpers, shared by the plugin and scripts/.

The SSSOM files in mappings/*.sssom.tsv are the source of truth for term-level
mappings; columns are read BY HEADER NAME, never by position. Term ids
(`onga:ONGA_NNNNNNN`) come from curation_workbench's TermIds over ONGA's
workbench.yaml (`term_ids()`).

This module lives in the plugin folder because onga_plugin imports it: every
file the plugin runs must be in curation/plugin/. It imports only the standard
library, `yaml` and `curation_workbench`, and reads only files inside the repo.
Functions that read files take an optional `root` (default: this checkout), so
the plugin can honor `cwb --root`. Scripts import it with
`sys.path.insert(0, <repo>/curation/plugin)`.
"""
import re
from pathlib import Path

import yaml

from curation_workbench.schema import is_negated, read_sssom  # noqa: F401  (re-exported)

ROOT = Path(__file__).resolve().parents[2]
MAPPINGS = ROOT / "mappings"
POLICY = MAPPINGS / "policy.yaml"
SO_OBO = ROOT / "embeddings" / "data" / "ontologies" / "so.obo"

ONGA_BASE = "https://databio.org/onga/"
ID_RE = re.compile(r"^ONGA_\d{7}$")
MEANING_RE = re.compile(r"^onga:ONGA_\d{7}$")

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


def term_ids(root=None):
    """curation_workbench TermIds for ONGA (schema terms, the id ledger)."""
    from curation_workbench.config import Config
    from curation_workbench.termids import TermIds
    root = Path(root) if root else ROOT
    return TermIds(Config.load(ROOT / "workbench.yaml", root=root))


def sssom_files(root=None):
    return sorted(((Path(root) if root else ROOT) / "mappings").glob("*.sssom.tsv"))


def all_rows(root=None):
    """[(file name, row)] over every mappings/*.sssom.tsv, in file then row order."""
    return [(p.name, r) for p in sssom_files(root) for r in read_sssom(p)]


def load_policy(root=None):
    path = (Path(root) / "mappings" / "policy.yaml") if root else POLICY
    p = yaml.safe_load(open(path))
    return {
        "banned_skos": set(p["banned_skos"]),
        "set_denoting_so": set(p["set_denoting_so"]),
        "sequence_attribute_so": set(p["sequence_attribute_so"]),
        "fits": set(p["fits"]),
        "subject_category": p["subject_category"],
        "object_category": p["object_category"],
    }


def skos_licensed_so(policy):
    """SO classes a banned SKOS predicate may target: set-denoting classes and
    sequence attributes (neither is an element type)."""
    return policy["set_denoting_so"] | policy["sequence_attribute_so"]


class SubjectError(Exception):
    pass


def subject_term(row, terms):
    """The live term an SSSOM row is about, by `subject_id` (onga:ONGA_NNNNNNN).

    `terms` is {id: curation_workbench.termids.Term}. Raises SubjectError if the
    id is not a live term or `subject_label` disagrees with the live label."""
    sid = row.get("subject_id", "")
    tid = sid[len("onga:"):] if sid.startswith("onga:") else None
    term = terms.get(tid)
    if term is None:
        raise SubjectError(f"subject_id {sid!r} is not a live ONGA term id")
    if row.get("subject_label", "") != term.label:
        raise SubjectError(f"subject_id {sid} is {term.enum} {term.label!r}, but "
                           f"subject_label says {row.get('subject_label')!r}")
    return term


def live_so_terms(root=None):
    """{id: name} for every non-obsolete SO term in so.obo (stdlib stanza scan),
    or None when so.obo is absent (it is gitignored, so never in a hosted checkout)."""
    path = (Path(root) / "embeddings" / "data" / "ontologies" / "so.obo") if root else SO_OBO
    if not path.exists():
        return None
    out, cur, name, obsolete, in_term = {}, None, "", False, False

    def flush():
        if in_term and cur and not obsolete:
            out[cur] = name

    with open(path) as fh:
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
