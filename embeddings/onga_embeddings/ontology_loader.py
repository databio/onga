"""Load and parse OWL/OBO ontology files into :class:`OntologyTerm` objects.

OBO files are parsed by a small stdlib-only stanza reader (:func:`parse_obo`), so
loading SO, CL, UBERON or EFO needs no third-party parser at all. OWL files still
need ``pronto``, which is imported lazily - only a caller that actually loads an
``.owl`` file (EDAM, OBI, CLO) pays for it.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class OntologyTerm:
    """A term from an external ontology."""

    id: str  # e.g., "EDAM:data_0863" or "SO:0000149"
    name: str
    definition: str
    synonyms: list[str] = field(default_factory=list)
    ontology: str = ""  # e.g., "edam", "so", "obi", "go"

    def embedding_text(self) -> str:
        """Generate text representation for embedding.

        Combines name, definition, and top synonyms for richer semantic representation.
        """
        parts = [self.name]
        if self.definition:
            parts.append(self.definition)
        if self.synonyms:
            # Include up to 3 synonyms to avoid overwhelming the embedding
            parts.append(f"Also known as: {', '.join(self.synonyms[:3])}")
        return " ".join(parts)

    def to_dict(self) -> dict:
        """Convert to dictionary for metadata storage."""
        return {
            "id": self.id,
            "name": self.name,
            "definition": self.definition,
            "ontology": self.ontology,
            "synonyms": self.synonyms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OntologyTerm":
        """Rebuild a term from the metadata stored alongside embeddings."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            definition=data.get("definition", ""),
            synonyms=list(data.get("synonyms") or []),
            ontology=data.get("ontology", ""),
        )


# --------------------------------------------------------------- OBO parsing


def parse_obo(path: str | Path) -> list[dict]:
    """Parse an OBO file with the standard library only.

    Reads ``[Term]`` stanzas and returns one dict per non-obsolete, named term
    with the keys ``id``, ``name``, ``def``, ``synonyms`` (a list of
    ``(text, scope)`` pairs), ``is_a``, and ``namespace``.

    This is deliberately dependency-free: ``pronto`` cannot parse several OBO
    releases we care about (SO, CL, UBERON, EFO) and ``obonet`` pulls in
    networkx, so an OBO release should not require either.

    Args:
        path: Path to a ``.obo`` file.

    Returns:
        List of raw term dicts in file order.

    Example:
        >>> terms = parse_obo("data/ontologies/so.obo")
        >>> len(terms)
        2409
    """
    terms: list[dict] = []
    current: dict | None = None
    in_term = False

    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if line.startswith("["):
                if current and in_term:
                    terms.append(current)
                in_term = line.strip() == "[Term]"
                current = {"synonyms": [], "xrefs": [], "is_a": []} if in_term else None
                continue
            if not in_term or not line or ":" not in line:
                continue
            tag, _, value = line.partition(": ")
            value = value.strip()
            if tag == "id":
                current["id"] = value
            elif tag == "name":
                current["name"] = value
            elif tag == "def":
                match = re.match(r'"(.*)"\s*\[', value)
                current["def"] = match.group(1) if match else value
            elif tag == "synonym":
                match = re.match(r'"(.*?)"\s+(\w+)', value)
                if match:
                    current["synonyms"].append((match.group(1), match.group(2)))
            elif tag == "is_obsolete" and value == "true":
                current["obsolete"] = True
            elif tag == "is_a":
                current["is_a"].append(value.split(" ! ")[0])
            elif tag == "namespace":
                current["namespace"] = value

    if current and in_term:
        terms.append(current)

    return [t for t in terms if not t.get("obsolete") and "name" in t]


def _load_from_obo(path: Path, ontology_name: str) -> Iterator[OntologyTerm]:
    """Yield :class:`OntologyTerm` objects from an OBO file (stdlib only)."""
    count = 0
    for raw in parse_obo(path):
        yield OntologyTerm(
            id=raw.get("id", ""),
            name=raw["name"],
            definition=raw.get("def", "") or "",
            synonyms=[text for text, _scope in raw["synonyms"]],
            ontology=ontology_name,
        )
        count += 1
    print(f"  Loaded {count} terms from {ontology_name} (stdlib OBO parser)")


# --------------------------------------------------------------- OWL parsing


def _load_from_owl(path: Path, ontology_name: str) -> Iterator[OntologyTerm]:
    """Yield :class:`OntologyTerm` objects from an OWL file via pronto.

    ``pronto`` is imported here rather than at module scope so that the OBO path
    - and everything else in this package - works without it installed.
    """
    try:
        import pronto
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            f"Reading {path.name} requires the optional 'pronto' dependency "
            "(pip install 'onga-embeddings[owl]'). OBO files need no extra "
            "dependency."
        ) from exc

    onto = pronto.Ontology(path)

    count = 0
    for term in onto.terms():
        if term.obsolete:
            continue

        synonyms = [syn.description for syn in term.synonyms]

        yield OntologyTerm(
            id=term.id,
            name=term.name or term.id,
            definition=term.definition or "",
            synonyms=synonyms,
            ontology=ontology_name,
        )
        count += 1

    print(f"  Loaded {count} terms from {ontology_name} (pronto)")


def load_ontology(
    path: str | Path, ontology_name: str | None = None
) -> Iterator[OntologyTerm]:
    """Load terms from an OWL or OBO ontology file.

    ``.obo`` files use the built-in stdlib parser and need no third-party
    package. Everything else (``.owl``, ``.ttl``, ...) is handed to ``pronto``,
    which is imported lazily.

    Args:
        path: Path to the ontology file (.owl or .obo).
        ontology_name: Name to assign to terms (defaults to filename stem).

    Yields:
        OntologyTerm objects for each term in the ontology.

    Example:
        >>> terms = list(load_ontology("data/ontologies/edam.owl", "edam"))
        >>> len(terms)
        3500
        >>> terms[0].ontology
        'edam'
    """
    path = Path(path)
    if ontology_name is None:
        ontology_name = path.stem.lower()

    print(f"Loading {ontology_name} from {path}...")

    if path.suffix.lower() == ".obo":
        yield from _load_from_obo(path, ontology_name)
    else:
        yield from _load_from_owl(path, ontology_name)


def load_multiple_ontologies(
    paths: dict[str, str | Path]
) -> Iterator[OntologyTerm]:
    """Load terms from multiple ontology files.

    Args:
        paths: Mapping of ontology name to file path.

    Yields:
        OntologyTerm objects from all ontologies.

    Example:
        >>> ontologies = {
        ...     "edam": "data/ontologies/edam.owl",
        ...     "so": "data/ontologies/so.obo",
        ... }
        >>> terms = list(load_multiple_ontologies(ontologies))
    """
    for name, path in paths.items():
        yield from load_ontology(path, name)
