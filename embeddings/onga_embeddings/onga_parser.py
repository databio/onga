"""Parse ONGA LinkML YAML vocabulary files."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import yaml


@dataclass
class ONGATerm:
    """A term from the ONGA vocabulary."""

    name: str
    description: str
    category: str  # "DataType" or "FeatureType"
    subset: str  # e.g., "alignment", "peak_set", "signal_track"
    edam_mapping: str | None = None
    see_also: list[str] = field(default_factory=list)

    def embedding_text(self) -> str:
        """Generate text representation for embedding.

        Combines name and description for semantic embedding.
        """
        return f"{self.name}: {self.description}"

    def to_dict(self) -> dict:
        """Convert to dictionary for metadata storage."""
        return {
            "name": self.name,
            "definition": self.description,
            "ontology": "ONGA",
            "category": self.category,
            "subset": self.subset,
            "edam_mapping": self.edam_mapping,
            "see_also": self.see_also,
        }


def parse_onga(path: str | Path) -> list[ONGATerm]:
    """Parse ONGA LinkML YAML file and extract terms.

    Args:
        path: Path to the ONGA file_content.yaml file.

    Returns:
        List of ONGATerm objects from DataType and FeatureType enums.

    Example:
        >>> terms = parse_onga("/path/to/file_content.yaml")
        >>> len(terms)
        325
        >>> terms[0].category
        'DataType'
    """
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)

    terms: list[ONGATerm] = []

    for enum_name in ["DataType", "FeatureType"]:
        if enum_name not in data.get("enums", {}):
            continue

        enum_def = data["enums"][enum_name]
        permissible_values = enum_def.get("permissible_values", {})

        for term_name, term_data in permissible_values.items():
            if term_data is None:
                term_data = {}

            # Extract subset (first element if list, else "other")
            in_subset = term_data.get("in_subset", [])
            subset = in_subset[0] if in_subset else "other"

            terms.append(
                ONGATerm(
                    name=term_name,
                    description=term_data.get("description", ""),
                    category=enum_name,
                    subset=subset,
                    edam_mapping=term_data.get("meaning"),
                    see_also=term_data.get("see_also", []),
                )
            )

    return terms


def iter_onga(path: str | Path) -> Iterator[ONGATerm]:
    """Iterate over ONGA terms (memory-efficient for large files)."""
    yield from parse_onga(path)
