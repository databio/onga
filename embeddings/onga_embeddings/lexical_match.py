"""Lexical matching of ONGA term names against external ontology labels.

Embeddings alone are unreliable for the cases a curator finds obvious. The ONGA
term ``candidate enhancers`` scores only ~0.31 cosine against SO:0000165
``enhancer``, far below unrelated noise, because "candidate" dominates the
sentence embedding. A head-noun matcher finds it immediately.

This module supplies that missing half of the search: normalisation,
singularisation, variant generation, trailing-token (head-noun) suffixes, and an
index over any iterable of :class:`~onga_embeddings.ontology_loader.OntologyTerm`
built from both labels and synonyms.

Two match kinds are distinguished:

``WHOLE_NAME`` (``"lexical"``)
    The whole ONGA term name (or its singular form) is a label or synonym of the
    ontology term.

``HEAD_NOUN`` (``"lexical-suffix"``)
    Only a trailing run of tokens matches, e.g. ``candidate enhancers`` ->
    ``enhancer``. The dropped leading tokens are usually ONGA derivation facets
    ("candidate", "predicted", "curated") that no external ontology models.

Example:
    >>> index = LexicalIndex(load_ontology("data/ontologies/so.obo", "so"))
    >>> hits = index.search("candidate enhancers")
    >>> hits[0].term.id, hits[0].match_kind
    ('SO:0000165', 'lexical-suffix')
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Iterator

from onga_embeddings.ontology_loader import OntologyTerm

# Match kinds. These strings are written verbatim into candidate reports.
WHOLE_NAME = "lexical"
HEAD_NOUN = "lexical-suffix"

LEXICAL_MATCH_KINDS = (WHOLE_NAME, HEAD_NOUN)

# Irregular / domain plurals that a naive trailing-"s" strip would mangle, plus
# the common genomics head nouns we want to be certain about.
SINGULARIZE: dict[str, str] = {
    "peaks": "peak",
    "reads": "read",
    "alignments": "alignment",
    "regions": "region",
    "sites": "site",
    "elements": "element",
    "motifs": "motif",
    "junctions": "junction",
    "variants": "variant",
    "genes": "gene",
    "transcripts": "transcript",
    "loops": "loop",
    "domains": "domain",
    "boundaries": "boundary",
    "footprints": "footprint",
    "enhancers": "enhancer",
    "promoters": "promoter",
    "insulators": "insulator",
    "silencers": "silencer",
    "hotspots": "hotspot",
    "contacts": "contact",
    "compartments": "compartment",
    "stripes": "stripe",
    "anchors": "anchor",
    "calls": "call",
    "quantifications": "quantification",
}


def normalize(text: str) -> str:
    """Fold a label to a comparable form.

    Lowercases, turns ``_``, ``-`` and ``/`` into spaces, drops every remaining
    non-alphanumeric character, and collapses whitespace.

    Example:
        >>> normalize("Candidate Cis-Regulatory Elements")
        'candidate cis regulatory elements'
    """
    text = text.lower()
    text = re.sub(r"[_\-/]", " ", text)
    text = re.sub(r"[^a-z0-9 ]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def variants(text: str) -> list[str]:
    """Return the comparable forms of ``text``, normalised form first.

    At most two forms are produced: the normalised string, and its singular
    form when the final token is a known or apparent plural. Order is stable so
    that indexing and lookup are reproducible across runs (a ``set`` here would
    make results depend on the interpreter's hash seed).

    Example:
        >>> variants("candidate enhancers")
        ['candidate enhancers', 'candidate enhancer']
    """
    normalized = normalize(text)
    out = [normalized]
    tokens = normalized.split()
    if tokens:
        last = tokens[-1]
        if last in SINGULARIZE:
            singular = " ".join(tokens[:-1] + [SINGULARIZE[last]])
        elif last.endswith("s") and len(last) > 3:
            singular = " ".join(tokens[:-1] + [last[:-1]])
        else:
            singular = None
        if singular is not None and singular != normalized:
            out.append(singular)
    return out


def token_suffixes(text: str) -> list[tuple[str, int]]:
    """Trailing token n-grams of ``text``, longest first, with their offsets.

    Each entry is ``(variant, start)`` where ``start`` is the token offset the
    suffix begins at; ``start == 0`` means the whole name.

    Example:
        >>> token_suffixes("candidate enhancers")
        [('candidate enhancers', 0), ('candidate enhancer', 0), ('enhancers', 1), ('enhancer', 1)]
    """
    tokens = normalize(text).split()
    out: list[tuple[str, int]] = []
    for start in range(len(tokens)):
        for variant in variants(" ".join(tokens[start:])):
            out.append((variant, start))
    return out


@dataclass(frozen=True)
class LexicalHit:
    """One ontology term matched lexically to an ONGA term name."""

    term: OntologyTerm
    matched_on: str
    """The ontology label or synonym text that matched, verbatim."""
    match_kind: str
    """``WHOLE_NAME`` or ``HEAD_NOUN``."""
    label_kind: str
    """``"name"`` or ``"synonym"`` - which field of the ontology term matched."""
    suffix_start: int
    """Token offset the matched suffix began at (0 for a whole-name match)."""

    @property
    def is_whole_name(self) -> bool:
        return self.match_kind == WHOLE_NAME


class LexicalIndex:
    """Normalised label/synonym index over an ontology, for head-noun lookup.

    Works with any iterable of :class:`OntologyTerm`, so EDAM (OWL), SO (OBO)
    and any future ontology are searched identically.

    Example:
        >>> index = LexicalIndex(terms)
        >>> index.has_whole_name_match("contigs")
        True
    """

    def __init__(self, terms: Iterable[OntologyTerm]):
        self._terms: list[OntologyTerm] = []
        self._index: dict[str, list[tuple[OntologyTerm, str, str]]] = {}
        for term in terms:
            self.add(term)

    def add(self, term: OntologyTerm) -> None:
        """Index one term under every variant of its name and synonyms."""
        self._terms.append(term)
        labels = [(term.name, "name")]
        labels += [(syn, "synonym") for syn in term.synonyms]
        for label, label_kind in labels:
            if not label:
                continue
            for variant in variants(label):
                self._index.setdefault(variant, []).append((term, label, label_kind))

    @property
    def terms(self) -> list[OntologyTerm]:
        """The indexed terms, in insertion order."""
        return self._terms

    def __len__(self) -> int:
        return len(self._terms)

    def __contains__(self, variant: str) -> bool:
        return variant in self._index

    def lookup(self, variant: str) -> list[tuple[OntologyTerm, str, str]]:
        """Raw index lookup for an already-normalised variant string."""
        return self._index.get(variant, [])

    def search(self, name: str) -> list[LexicalHit]:
        """Return ranked lexical hits for an ONGA term name.

        The longest matching suffix wins: the whole name is tried first, then
        progressively shorter trailing runs of tokens. The first suffix with any
        index hit produces the result and the search stops, so a whole-name
        match is never diluted by head-noun noise. Hits are de-duplicated by
        ontology term id and returned in ontology file order.

        Returns an empty list when nothing matches.
        """
        hits: list[LexicalHit] = []
        seen: set[str] = set()
        for variant, start in token_suffixes(name):
            entries = self.lookup(variant)
            if not entries:
                continue
            kind = WHOLE_NAME if start == 0 else HEAD_NOUN
            for term, label, label_kind in entries:
                if term.id in seen:
                    continue
                seen.add(term.id)
                hits.append(
                    LexicalHit(
                        term=term,
                        matched_on=label,
                        match_kind=kind,
                        label_kind=label_kind,
                        suffix_start=start,
                    )
                )
            if hits:
                break
        return hits

    def has_whole_name_match(self, name: str) -> bool:
        """True when the whole ONGA name (or its singular) is a label/synonym."""
        return any(variant in self._index for variant in variants(name))

    def has_any_match(self, name: str) -> bool:
        """True when any trailing run of tokens matches - head noun included."""
        return any(variant in self._index for variant, _ in token_suffixes(name))


def build_lexical_index(terms: Iterable[OntologyTerm]) -> LexicalIndex:
    """Build a :class:`LexicalIndex` from an iterable of ontology terms."""
    return LexicalIndex(terms)


def iter_lexical_hits(
    names: Iterable[str], index: LexicalIndex
) -> Iterator[tuple[str, list[LexicalHit]]]:
    """Yield ``(name, hits)`` for each ONGA term name."""
    for name in names:
        yield name, index.search(name)
