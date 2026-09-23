"""Provenance and stable finding ids for the embeddings reports.

Every report carries one shared ``provenance`` block, so a consumer can tell
which schema, model and ontology files produced it. Every finding carries a
content-derived ``id`` and a ``subjects`` list of term subject ids (SIDs) from
``curation/subjects.json``, so a decision made on a finding stays attached to
it when the reports are regenerated.

Finding ids hash term ids (``ONGA_0000123``), never labels, so a rename keeps
the id.
"""

import hashlib
import json
import tomllib
from datetime import datetime
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
DEFAULT_SUBJECTS = REPO_ROOT / "curation" / "subjects.json"
DEFAULT_CROSSWALK = REPO_ROOT / "curation" / "term_crosswalk.json"

#: Hex characters kept from each finding hash.
FINDING_ID_LENGTH = 12


def generator_version() -> str:
    """``onga-embeddings/<version>``, read from ``pyproject.toml``."""
    with open(PACKAGE_ROOT / "pyproject.toml", "rb") as fh:
        project = tomllib.load(fh)["project"]
    return f"{project['name']}/{project['version']}"


def sha256_file(path: Path) -> str:
    """``sha256:<hex>`` of a file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _finding_id(prefix: str, *parts: str) -> str:
    for part in parts:
        if not part:
            raise ValueError(f"{prefix}: finding id needs non-empty parts, got {parts!r}")
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest[:FINDING_ID_LENGTH]}"


def similarity_id(term_id_a: str, term_id_b: str) -> str:
    """``sim:`` id of an internal-similarity pair; order-independent."""
    return _finding_id("sim", *sorted((term_id_a, term_id_b)))


def gap_id(term_id: str) -> str:
    """``gap:`` id of a gap finding."""
    return _finding_id("gap", term_id)


def mapping_id(term_id: str, ontology: str, object_id: str) -> str:
    """``map:`` id of one mapping suggestion."""
    return _finding_id("map", term_id, ontology, object_id)


class SubjectRegistry:
    """Term lookups over ``curation/subjects.json`` and ``term_crosswalk.json``."""

    def __init__(self, subjects_path: Path, crosswalk_path: Path):
        self.subjects_path = Path(subjects_path)
        self.crosswalk_path = Path(crosswalk_path)
        with open(self.subjects_path) as fh:
            data = json.load(fh)
        with open(self.crosswalk_path) as fh:
            self._labels: dict[str, str] = json.load(fh)["labels"]
        self.schema_fingerprint: str = data["schema_fingerprint"]
        self._term_by_id = {
            s["term_id"]: s for s in data["subjects"].values() if s["kind"] == "term"
        }

    def resolve(self, label: str, enum: str) -> dict:
        """Live term subject record for a label, via the crosswalk.

        Crosswalk labels are unique across all enums (every label ever used,
        live or former). ``enum`` must match the live term's enum.

        Raises:
            KeyError: the label is unknown, resolves to a retired term, or the
                term now lives in a different enum.
        """
        term_id = self._labels.get(label)
        if term_id is None:
            raise KeyError(f"{enum}/{label!r}: not in {self.crosswalk_path}")
        record = self._term_by_id.get(term_id)
        if record is None:
            raise KeyError(f"{enum}/{label!r}: crosswalk id {term_id} not in {self.subjects_path}")
        if record.get("retired"):
            raise KeyError(f"{enum}/{label!r}: resolves to retired term {term_id}")
        if record["enum"] != enum:
            raise KeyError(f"{enum}/{label!r}: {term_id} is now in {record['enum']}")
        return record


def build_provenance(
    *,
    model_name: str,
    schema_fingerprint: str,
    subject_count: int,
    ontologies: list[dict],
    params: dict,
) -> dict:
    """The shared ``provenance`` block written into every report."""
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "generator_version": generator_version(),
        "model_name": model_name,
        "schema_fingerprint": schema_fingerprint,
        "subject_count": subject_count,
        "ontologies": sorted(ontologies, key=lambda o: o["name"]),
        "params": params,
    }
