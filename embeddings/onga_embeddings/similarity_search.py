"""Similarity search for comparing ONGA terms against ontology embeddings.

Two levels of search live here:

* :class:`SimilaritySearcher` - the embedding-only search used by the mapping,
  internal-similarity and gap reports. Unchanged.
* :func:`blend_candidates` and :meth:`SimilaritySearcher.find_candidates` - the
  blended search used to generate curation candidates. Lexical hits from
  :mod:`onga_embeddings.lexical_match` come first, then embedding hits fill the
  remainder, de-duplicated by ontology term id and each labelled with its match
  kind. This is what makes SO:0000165 ``enhancer`` show up for the ONGA term
  ``candidate enhancers``, which embeddings alone rank around cosine 0.31.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from onga_embeddings.lexical_match import LexicalHit, LexicalIndex
from onga_embeddings.ontology_loader import OntologyTerm

#: Match kind recorded for a hit that only the embedding search found.
EMBEDDING = "embedding"


@dataclass
class SimilarityResult:
    """A single similarity match between a query term and a target term."""
    query_term: str
    query_ontology: str
    match_term: str
    match_ontology: str
    match_id: str
    similarity: float
    match_definition: str
    query_category: str = ""
    query_subset: str = ""


@dataclass
class TermSimilarityResults:
    """All similarity results for a single query term across multiple ontologies."""
    term_name: str
    category: str
    subset: str
    definition: str
    existing_mapping: Optional[str]
    matches_by_ontology: dict[str, list[SimilarityResult]] = field(default_factory=dict)
    term_id: str = ""
    sid: str = ""

    def best_match_per_ontology(self) -> dict[str, SimilarityResult]:
        """Return the best match for each ontology."""
        return {
            onto: matches[0] if matches else None
            for onto, matches in self.matches_by_ontology.items()
        }

    def best_overall_match(self) -> Optional[SimilarityResult]:
        """Return the single best match across all ontologies."""
        all_matches = [m for matches in self.matches_by_ontology.values() for m in matches]
        if not all_matches:
            return None
        return max(all_matches, key=lambda m: m.similarity)

    def max_similarity(self) -> float:
        """Return the highest similarity score across all matches."""
        best = self.best_overall_match()
        return best.similarity if best else 0.0


@dataclass
class CandidateMatch:
    """One blended candidate mapping for an ONGA term.

    ``match_kind`` is ``"lexical"`` (whole-name label/synonym hit),
    ``"lexical-suffix"`` (head-noun hit) or ``"embedding"``. ``score`` is always
    the cosine similarity of the two embeddings, including for lexical hits, so
    the column stays comparable across kinds.
    """

    query_term: str
    rank: int
    match_kind: str
    match_ontology: str
    match_id: str
    match_term: str
    matched_on: str
    score: float
    match_definition: str = ""
    query_category: str = ""
    query_subset: str = ""
    query_mapping: Optional[str] = None

    @property
    def is_lexical(self) -> bool:
        """True for whole-name and head-noun hits, False for embedding hits."""
        return self.match_kind != EMBEDDING

    def to_dict(self) -> dict:
        return {
            "onga_term": self.query_term,
            "category": self.query_category,
            "subset": self.query_subset,
            "existing_mapping": self.query_mapping or "",
            "rank": self.rank,
            "match_kind": self.match_kind,
            "match_id": self.match_id,
            "match_label": self.match_term,
            "matched_on": self.matched_on,
            "score": self.score,
            "match_def": self.match_definition,
        }


def blend_candidates(
    query: dict,
    lexical_hits: Sequence[LexicalHit],
    similarities: np.ndarray,
    terms: Sequence[OntologyTerm],
    top_k: int = 5,
    ontology_name: str = "",
    row_of_id: Optional[dict[str, int]] = None,
) -> list[CandidateMatch]:
    """Merge lexical and embedding hits into one ranked candidate list.

    Lexical hits are emitted first, in the order the index returned them, then
    the highest-scoring embedding hits fill up to ``top_k``. Any ontology term
    already emitted as a lexical hit is skipped in the embedding pass, so an id
    never appears twice.

    Args:
        query: ONGA term metadata dict (``name``, ``category``, ``subset``,
            ``meaning``).
        lexical_hits: Hits from :meth:`LexicalIndex.search` for this term.
        similarities: 1-D cosine similarity row aligned with ``terms``.
        terms: The ontology terms, aligned with ``similarities``.
        top_k: How many embedding hits to add after the lexical hits.
        ontology_name: Name recorded on each candidate.
        row_of_id: Optional precomputed ``{term id: row}`` map.

    Returns:
        Ranked candidates, lexical first. Ranks start at 1.
    """
    if row_of_id is None:
        row_of_id = {term.id: i for i, term in enumerate(terms)}

    query_name = query.get("name", "")
    category = query.get("category", "")
    subset = query.get("subset", "")
    mapping = query.get("meaning")

    def make(kind: str, term: OntologyTerm, matched_on: str, score: float) -> CandidateMatch:
        return CandidateMatch(
            query_term=query_name,
            rank=0,  # assigned below
            match_kind=kind,
            match_ontology=ontology_name or term.ontology,
            match_id=term.id,
            match_term=term.name,
            matched_on=matched_on,
            score=score,
            match_definition=term.definition or "",
            query_category=category,
            query_subset=subset,
            query_mapping=mapping,
        )

    candidates: list[CandidateMatch] = []
    seen: set[str] = set()

    for hit in lexical_hits:
        if hit.term.id in seen:
            continue
        seen.add(hit.term.id)
        row = row_of_id.get(hit.term.id)
        score = float(similarities[row]) if row is not None else 0.0
        candidates.append(make(hit.match_kind, hit.term, hit.matched_on, score))

    # Pull a pool large enough that `top_k` unseen terms are always available.
    pool = np.argsort(-similarities)[: top_k + len(seen)]
    added = 0
    for row in pool:
        term = terms[row]
        if term.id in seen:
            continue
        seen.add(term.id)
        candidates.append(make(EMBEDDING, term, term.name, float(similarities[row])))
        added += 1
        if added >= top_k:
            break

    for rank, candidate in enumerate(candidates, 1):
        candidate.rank = rank
    return candidates


#: Values of :meth:`InternalSimilarityPair.machine_recommendation`.
MACHINE_RECOMMENDATIONS = ("merge", "hierarchy", "review_cross_category", "consolidate")


@dataclass
class InternalSimilarityPair:
    """A pair of ONGA terms that are similar to each other."""
    term1_name: str
    term1_category: str
    term1_subset: str
    term2_name: str
    term2_category: str
    term2_subset: str
    similarity: float
    crosses_categories: bool
    term1_id: str = ""
    term1_sid: str = ""
    term2_id: str = ""
    term2_sid: str = ""

    def machine_recommendation(self) -> str:
        """Machine-readable recommendation, one of :data:`MACHINE_RECOMMENDATIONS`."""
        if self.crosses_categories:
            return "review_cross_category"
        if self.similarity > 0.95:
            return "merge"
        if self.similarity > 0.85:
            return "hierarchy"
        return "consolidate"

    def recommendation(self) -> str:
        """Generate a recommendation based on the similarity."""
        if self.crosses_categories:
            return "Review: similar terms in different categories"
        if self.similarity > 0.95:
            return "Consider merging"
        if self.similarity > 0.85:
            return "Consider hierarchy relationship"
        return "Review for potential consolidation"


def _npz_str(data, key: str) -> Optional[str]:
    """A scalar string stored in an ``.npz``, or None when absent."""
    return str(data[key]) if key in data.files else None


class SimilaritySearcher:
    """Search engine for finding similar terms using pre-computed embeddings."""

    def __init__(self, embedding_dir: Path):
        self.embedding_dir = Path(embedding_dir)
        self._onga_embeddings: Optional[np.ndarray] = None
        self._onga_metadata: Optional[list[dict]] = None
        self._onga_model_name: Optional[str] = None
        self._onga_schema_fingerprint: Optional[str] = None
        self._ontology_embeddings: dict[str, np.ndarray] = {}
        self._ontology_metadata: dict[str, list[dict]] = {}
        self._ontology_model_names: dict[str, str] = {}
        self._ontology_sources: dict[str, dict] = {}
        self._ontology_terms: dict[str, list[OntologyTerm]] = {}
        self._lexical_indexes: dict[str, LexicalIndex] = {}

    def load_onga_embeddings(self) -> None:
        """Load ONGA embeddings from disk."""
        path = self.embedding_dir / "onga.npz"
        if not path.exists():
            raise FileNotFoundError(f"ONGA embeddings not found at {path}")
        data = np.load(path, allow_pickle=True)
        self._onga_embeddings = data["embeddings"]
        self._onga_metadata = data["metadata"].tolist()
        self._onga_model_name = _npz_str(data, "model_name")
        self._onga_schema_fingerprint = _npz_str(data, "schema_fingerprint")

    def load_ontology_embeddings(self, ontology_name: str) -> None:
        """Load embeddings for a specific ontology."""
        path = self.embedding_dir / f"{ontology_name}.npz"
        if not path.exists():
            raise FileNotFoundError(f"Ontology embeddings not found at {path}")
        data = np.load(path, allow_pickle=True)
        self._ontology_embeddings[ontology_name] = data["embeddings"]
        self._ontology_metadata[ontology_name] = data["metadata"].tolist()
        self._ontology_model_names[ontology_name] = _npz_str(data, "model_name")
        self._ontology_sources[ontology_name] = {
            "source_file": _npz_str(data, "source_file"),
            "sha256": _npz_str(data, "source_sha256"),
        }

    def load_all_ontologies(self) -> list[str]:
        """Load all available ontology embeddings. Returns list of loaded names."""
        loaded = []
        for path in self.embedding_dir.glob("*.npz"):
            if path.stem == "onga":
                continue
            self.load_ontology_embeddings(path.stem)
            loaded.append(path.stem)
        return loaded

    @property
    def onga_embeddings(self) -> np.ndarray:
        if self._onga_embeddings is None:
            self.load_onga_embeddings()
        return self._onga_embeddings

    @property
    def onga_metadata(self) -> list[dict]:
        if self._onga_metadata is None:
            self.load_onga_embeddings()
        return self._onga_metadata

    @property
    def model_name(self) -> Optional[str]:
        """Model that embedded the ONGA terms, as stored in ``onga.npz``."""
        if self._onga_embeddings is None:
            self.load_onga_embeddings()
        return self._onga_model_name

    @property
    def schema_fingerprint(self) -> Optional[str]:
        """``subjects.json`` fingerprint the ONGA embeddings were built from."""
        if self._onga_embeddings is None:
            self.load_onga_embeddings()
        return self._onga_schema_fingerprint

    def ontology_model_name(self, ontology_name: str) -> Optional[str]:
        """Model that embedded a loaded ontology."""
        return self._ontology_model_names[ontology_name]

    def ontology_provenance(self, ontology_name: str) -> dict:
        """``{name, source_file, sha256, term_count}`` for a loaded ontology."""
        return {
            "name": ontology_name,
            **self._ontology_sources[ontology_name],
            "term_count": len(self._ontology_metadata[ontology_name]),
        }

    def find_similar_terms(
        self,
        ontology_name: str,
        top_k: int = 10,
        threshold: float = 0.5
    ) -> list[list[SimilarityResult]]:
        """Find similar terms between ONGA and a specific ontology.

        Args:
            ontology_name: Name of the target ontology
            top_k: Maximum number of matches to return per query term
            threshold: Minimum similarity score to include a match

        Returns:
            List of match lists, one per ONGA term
        """
        if ontology_name not in self._ontology_embeddings:
            self.load_ontology_embeddings(ontology_name)

        target_embeddings = self._ontology_embeddings[ontology_name]
        target_metadata = self._ontology_metadata[ontology_name]

        # Compute cosine similarity (embeddings are normalized)
        similarities = self.onga_embeddings @ target_embeddings.T

        results = []
        for i, query_meta in enumerate(self.onga_metadata):
            query_sims = similarities[i]
            top_indices = np.argsort(query_sims)[::-1][:top_k]

            query_results = []
            for idx in top_indices:
                sim = float(query_sims[idx])
                if sim < threshold:
                    continue
                target_meta = target_metadata[idx]
                query_results.append(SimilarityResult(
                    query_term=query_meta["name"],
                    query_ontology="ONGA",
                    query_category=query_meta.get("category", ""),
                    query_subset=query_meta.get("subset", ""),
                    match_term=target_meta.get("name", ""),
                    match_ontology=ontology_name,
                    match_id=target_meta.get("id", ""),
                    similarity=sim,
                    match_definition=target_meta.get("definition", "")
                ))
            results.append(query_results)
        return results

    def find_all_similar_terms(
        self,
        top_k: int = 5,
        threshold: float = 0.5
    ) -> list[TermSimilarityResults]:
        """Find similar terms across all loaded ontologies.

        Returns:
            List of TermSimilarityResults, one per ONGA term
        """
        if not self._ontology_embeddings:
            self.load_all_ontologies()

        # Initialize results for each ONGA term
        results = []
        for meta in self.onga_metadata:
            results.append(TermSimilarityResults(
                term_name=meta["name"],
                category=meta.get("category", ""),
                subset=meta.get("subset", ""),
                definition=meta.get("definition", ""),
                existing_mapping=meta.get("meaning"),
                matches_by_ontology={},
                term_id=meta.get("term_id", ""),
                sid=meta.get("sid", ""),
            ))

        # Search against each ontology
        for ontology_name in self._ontology_embeddings:
            matches = self.find_similar_terms(ontology_name, top_k, threshold)
            for i, term_matches in enumerate(matches):
                results[i].matches_by_ontology[ontology_name] = term_matches

        return results

    def find_internal_similarity(
        self,
        threshold: float = 0.8
    ) -> list[InternalSimilarityPair]:
        """Find ONGA terms that are similar to each other.

        Args:
            threshold: Minimum similarity to consider terms as similar

        Returns:
            List of similar term pairs, sorted by similarity (descending)
        """
        # Compute self-similarity matrix
        similarities = self.onga_embeddings @ self.onga_embeddings.T

        # Find pairs above threshold (upper triangle only to avoid duplicates)
        pairs = []
        n = len(self.onga_metadata)
        for i in range(n):
            for j in range(i + 1, n):
                sim = float(similarities[i, j])
                if sim >= threshold:
                    meta_i = self.onga_metadata[i]
                    meta_j = self.onga_metadata[j]
                    pairs.append(InternalSimilarityPair(
                        term1_name=meta_i["name"],
                        term1_category=meta_i.get("category", ""),
                        term1_subset=meta_i.get("subset", ""),
                        term2_name=meta_j["name"],
                        term2_category=meta_j.get("category", ""),
                        term2_subset=meta_j.get("subset", ""),
                        similarity=sim,
                        crosses_categories=(
                            meta_i.get("category") != meta_j.get("category")
                        ),
                        term1_id=meta_i.get("term_id", ""),
                        term1_sid=meta_i.get("sid", ""),
                        term2_id=meta_j.get("term_id", ""),
                        term2_sid=meta_j.get("sid", ""),
                    ))

        # Sort by similarity descending
        pairs.sort(key=lambda p: p.similarity, reverse=True)
        return pairs

    def find_gap_terms(
        self,
        results: list[TermSimilarityResults],
        max_similarity_threshold: float = 0.5
    ) -> list[TermSimilarityResults]:
        """Find ONGA terms with no good matches in any ontology.

        Args:
            results: Results from find_all_similar_terms()
            max_similarity_threshold: Terms with max similarity below this are gaps

        Returns:
            List of TermSimilarityResults for gap terms
        """
        gaps = []
        for term_result in results:
            if term_result.max_similarity() < max_similarity_threshold:
                gaps.append(term_result)
        return gaps

    # ------------------------------------------------------------------
    # Blended lexical + embedding candidate search
    # ------------------------------------------------------------------

    def ontology_terms(self, ontology_name: str) -> list[OntologyTerm]:
        """Rebuild OntologyTerm objects from the cached embedding metadata.

        The metadata stored in each ``.npz`` is exactly ``OntologyTerm.to_dict()``,
        so labels, definitions and synonyms round-trip. No ontology source file
        is needed to run a lexical search.
        """
        if ontology_name not in self._ontology_terms:
            if ontology_name not in self._ontology_metadata:
                self.load_ontology_embeddings(ontology_name)
            self._ontology_terms[ontology_name] = [
                OntologyTerm.from_dict(meta)
                for meta in self._ontology_metadata[ontology_name]
            ]
        return self._ontology_terms[ontology_name]

    def lexical_index(self, ontology_name: str) -> LexicalIndex:
        """Return (and cache) the lexical index for an ontology."""
        if ontology_name not in self._lexical_indexes:
            self._lexical_indexes[ontology_name] = LexicalIndex(
                self.ontology_terms(ontology_name)
            )
        return self._lexical_indexes[ontology_name]

    def find_candidates(
        self,
        ontology_name: str,
        top_k: int = 5,
    ) -> list[list[CandidateMatch]]:
        """Blended lexical + embedding candidates for every ONGA term.

        Args:
            ontology_name: Target ontology (must have a built ``.npz``).
            top_k: Number of embedding hits to append after the lexical hits.

        Returns:
            One ranked candidate list per ONGA term, in ONGA metadata order.
        """
        if ontology_name not in self._ontology_embeddings:
            self.load_ontology_embeddings(ontology_name)

        terms = self.ontology_terms(ontology_name)
        index = self.lexical_index(ontology_name)
        row_of_id = {term.id: i for i, term in enumerate(terms)}

        similarities = self.onga_embeddings @ self._ontology_embeddings[ontology_name].T

        results = []
        for i, query in enumerate(self.onga_metadata):
            results.append(
                blend_candidates(
                    query,
                    index.search(query.get("name", "")),
                    similarities[i],
                    terms,
                    top_k=top_k,
                    ontology_name=ontology_name,
                    row_of_id=row_of_id,
                )
            )
        return results

    def find_candidates_for_term(
        self,
        ontology_name: str,
        term_name: str,
        top_k: int = 5,
    ) -> list[CandidateMatch]:
        """Blended candidates for a single ONGA term, by name.

        Raises:
            KeyError: If the ONGA term is not in the loaded metadata.
        """
        for i, query in enumerate(self.onga_metadata):
            if query.get("name") == term_name:
                break
        else:
            raise KeyError(f"ONGA term not found in embeddings: {term_name!r}")

        if ontology_name not in self._ontology_embeddings:
            self.load_ontology_embeddings(ontology_name)

        terms = self.ontology_terms(ontology_name)
        index = self.lexical_index(ontology_name)
        similarities = (
            self.onga_embeddings[i] @ self._ontology_embeddings[ontology_name].T
        )
        return blend_candidates(
            self.onga_metadata[i],
            index.search(term_name),
            similarities,
            terms,
            top_k=top_k,
            ontology_name=ontology_name,
        )
