"""Similarity search for comparing ONGA terms against ontology embeddings."""

import numpy as np
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


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

    def recommendation(self) -> str:
        """Generate a recommendation based on the similarity."""
        if self.crosses_categories:
            return "Review: similar terms in different categories"
        if self.similarity > 0.95:
            return "Consider merging"
        if self.similarity > 0.85:
            return "Consider hierarchy relationship"
        return "Review for potential consolidation"


class SimilaritySearcher:
    """Search engine for finding similar terms using pre-computed embeddings."""

    def __init__(self, embedding_dir: Path):
        self.embedding_dir = Path(embedding_dir)
        self._onga_embeddings: Optional[np.ndarray] = None
        self._onga_metadata: Optional[list[dict]] = None
        self._ontology_embeddings: dict[str, np.ndarray] = {}
        self._ontology_metadata: dict[str, list[dict]] = {}

    def load_onga_embeddings(self) -> None:
        """Load ONGA embeddings from disk."""
        path = self.embedding_dir / "onga.npz"
        if not path.exists():
            raise FileNotFoundError(f"ONGA embeddings not found at {path}")
        data = np.load(path, allow_pickle=True)
        self._onga_embeddings = data["embeddings"]
        self._onga_metadata = data["metadata"].tolist()

    def load_ontology_embeddings(self, ontology_name: str) -> None:
        """Load embeddings for a specific ontology."""
        path = self.embedding_dir / f"{ontology_name}.npz"
        if not path.exists():
            raise FileNotFoundError(f"Ontology embeddings not found at {path}")
        data = np.load(path, allow_pickle=True)
        self._ontology_embeddings[ontology_name] = data["embeddings"]
        self._ontology_metadata[ontology_name] = data["metadata"].tolist()

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
                existing_mapping=meta.get("edam_mapping"),
                matches_by_ontology={}
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
                        )
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
