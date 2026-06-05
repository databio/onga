"""Load and parse OWL/OBO ontology files using pronto, with obonet fallback."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import pronto


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


def _parse_obo_def(def_str: str) -> str:
    """Extract definition text from an OBO def field value.

    OBO format: "text" [xref1, xref2]
    """
    match = re.match(r'^"(.*?)"\s*\[', def_str, re.DOTALL)
    if match:
        return match.group(1)
    return def_str


def _parse_obo_synonym(syn_str: str) -> str:
    """Extract synonym text from an OBO synonym field value.

    OBO format: "text" RELATED/EXACT/NARROW/BROAD [xrefs]
    """
    match = re.match(r'^"(.*?)"', syn_str)
    if match:
        return match.group(1)
    return syn_str


def _load_with_obonet(path: Path, ontology_name: str) -> Iterator[OntologyTerm]:
    """Load an OBO file using obonet when pronto cannot parse it."""
    import obonet

    graph = obonet.read_obo(str(path))
    count = 0

    for node_id, data in graph.nodes(data=True):
        if data.get("is_obsolete") == "true":
            continue

        name = data.get("name", node_id)

        def_str = data.get("def", "")
        definition = _parse_obo_def(def_str) if def_str else ""

        syn_list = data.get("synonym", [])
        if isinstance(syn_list, str):
            syn_list = [syn_list]
        synonyms = [_parse_obo_synonym(s) for s in syn_list]

        yield OntologyTerm(
            id=node_id,
            name=name,
            definition=definition,
            synonyms=synonyms,
            ontology=ontology_name,
        )
        count += 1

    print(f"  Loaded {count} terms from {ontology_name} (via obonet)")


def load_ontology(
    path: str | Path, ontology_name: str | None = None
) -> Iterator[OntologyTerm]:
    """Load terms from an OWL or OBO ontology file.

    Tries pronto first; falls back to obonet for OBO files that pronto cannot parse.

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

    try:
        onto = pronto.Ontology(path)
    except Exception as e:
        if path.suffix == ".obo":
            print(f"  pronto failed ({type(e).__name__}: {e}), falling back to obonet...")
            yield from _load_with_obonet(path, ontology_name)
            return
        raise

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

    print(f"  Loaded {count} terms from {ontology_name}")


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
