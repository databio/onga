"""Tests for similarity search module."""

import numpy as np
import pytest
from pathlib import Path
import tempfile

from onga_embeddings.lexical_match import HEAD_NOUN, WHOLE_NAME, LexicalIndex
from onga_embeddings.ontology_loader import OntologyTerm
from onga_embeddings.similarity_search import (
    EMBEDDING,
    CandidateMatch,
    InternalSimilarityPair,
    SimilarityResult,
    SimilaritySearcher,
    TermSimilarityResults,
    blend_candidates,
)


@pytest.fixture
def mock_embeddings_dir(tmp_path):
    """Create mock embedding files for testing."""
    # Create normalized embeddings (unit vectors)
    onga_emb = np.array([
        [1.0, 0.0, 0.0],  # term1
        [0.0, 1.0, 0.0],  # term2
        [0.9, 0.1, 0.0],  # term3 (similar to term1)
    ])
    onga_emb = onga_emb / np.linalg.norm(onga_emb, axis=1, keepdims=True)

    onga_meta = [
        {"name": "term1", "category": "DataType", "subset": "alignment", "definition": "Test term 1"},
        {"name": "term2", "category": "FeatureType", "subset": "peak_set", "definition": "Test term 2"},
        {"name": "term3", "category": "DataType", "subset": "alignment", "definition": "Test term 3"},
    ]

    np.savez(tmp_path / "onga.npz", embeddings=onga_emb, metadata=np.array(onga_meta, dtype=object))

    # Create test ontology
    edam_emb = np.array([
        [1.0, 0.0, 0.0],  # Similar to term1/term3
        [0.0, 0.0, 1.0],  # Different from all
    ])
    edam_emb = edam_emb / np.linalg.norm(edam_emb, axis=1, keepdims=True)

    edam_meta = [
        {"id": "EDAM:001", "name": "Sequence alignment", "ontology": "edam", "definition": "Alignment of sequences"},
        {"id": "EDAM:002", "name": "Other thing", "ontology": "edam", "definition": "Something else"},
    ]

    np.savez(tmp_path / "edam.npz", embeddings=edam_emb, metadata=np.array(edam_meta, dtype=object))

    return tmp_path


def test_load_onga_embeddings(mock_embeddings_dir):
    searcher = SimilaritySearcher(mock_embeddings_dir)
    searcher.load_onga_embeddings()
    assert len(searcher.onga_metadata) == 3
    assert searcher.onga_embeddings.shape == (3, 3)


def test_find_similar_terms(mock_embeddings_dir):
    searcher = SimilaritySearcher(mock_embeddings_dir)
    results = searcher.find_similar_terms("edam", top_k=2, threshold=0.0)

    assert len(results) == 3  # One result list per ONGA term
    assert results[0][0].match_term == "Sequence alignment"  # term1 matches EDAM:001
    assert results[0][0].similarity > 0.9  # High similarity


def test_find_internal_similarity(mock_embeddings_dir):
    searcher = SimilaritySearcher(mock_embeddings_dir)
    pairs = searcher.find_internal_similarity(threshold=0.8)

    # term1 and term3 should be similar
    assert len(pairs) >= 1
    pair = pairs[0]
    assert {pair.term1_name, pair.term2_name} == {"term1", "term3"}
    assert pair.similarity > 0.9


def test_internal_similarity_pair_recommendation():
    pair = InternalSimilarityPair(
        term1_name="a", term1_category="DataType", term1_subset="x",
        term2_name="b", term2_category="FeatureType", term2_subset="y",
        similarity=0.9, crosses_categories=True
    )
    assert "different categories" in pair.recommendation()


def test_term_similarity_results_best_match():
    result = TermSimilarityResults(
        term_name="test",
        category="DataType",
        subset="alignment",
        definition="Test",
        existing_mapping=None,
        matches_by_ontology={
            "edam": [
                SimilarityResult("test", "ONGA", "match1", "edam", "E:1", 0.9, ""),
                SimilarityResult("test", "ONGA", "match2", "edam", "E:2", 0.7, ""),
            ],
            "so": [
                SimilarityResult("test", "ONGA", "match3", "so", "S:1", 0.8, ""),
            ]
        }
    )

    best = result.best_overall_match()
    assert best.match_term == "match1"
    assert best.similarity == 0.9

    best_per_onto = result.best_match_per_ontology()
    assert best_per_onto["edam"].match_term == "match1"
    assert best_per_onto["so"].match_term == "match3"


# ---------------------------------------------------------------------------
# Blended lexical + embedding candidate search
# ---------------------------------------------------------------------------


@pytest.fixture
def so_terms():
    """Three ontology terms; only the first is lexically reachable."""
    return [
        OntologyTerm("SO:0000165", "enhancer", "A cis-acting sequence", ontology="so"),
        OntologyTerm("SO:0000110", "sequence_feature", "Any feature", ontology="so"),
        OntologyTerm("SO:0000001", "region", "A sequence region", ontology="so"),
    ]


def test_blend_puts_lexical_hits_first_despite_low_score(so_terms):
    """The motivating case: the right term scores lowest but must rank first."""
    index = LexicalIndex(so_terms)
    similarities = np.array([0.31, 0.80, 0.70])  # enhancer scores worst

    candidates = blend_candidates(
        {"name": "candidate enhancers", "category": "FeatureType", "subset": "regulatory"},
        index.search("candidate enhancers"),
        similarities,
        so_terms,
        top_k=2,
        ontology_name="so",
    )

    assert [c.match_id for c in candidates] == ["SO:0000165", "SO:0000110", "SO:0000001"]
    assert [c.match_kind for c in candidates] == [HEAD_NOUN, EMBEDDING, EMBEDDING]
    assert [c.rank for c in candidates] == [1, 2, 3]
    assert candidates[0].score == pytest.approx(0.31)
    assert candidates[0].matched_on == "enhancer"
    assert candidates[0].is_lexical
    assert not candidates[1].is_lexical


def test_blend_deduplicates_by_match_id(so_terms):
    """A term found lexically must not reappear as an embedding hit."""
    index = LexicalIndex(so_terms)
    similarities = np.array([0.95, 0.80, 0.70])  # enhancer also tops the embeddings

    candidates = blend_candidates(
        {"name": "enhancers"}, index.search("enhancers"), similarities, so_terms,
        top_k=3, ontology_name="so",
    )

    ids = [c.match_id for c in candidates]
    assert len(ids) == len(set(ids))
    assert candidates[0].match_kind == WHOLE_NAME
    assert [c.match_kind for c in candidates[1:]] == [EMBEDDING, EMBEDDING]


def test_blend_without_lexical_hits_is_embedding_only(so_terms):
    index = LexicalIndex(so_terms)
    similarities = np.array([0.31, 0.80, 0.70])

    candidates = blend_candidates(
        {"name": "unrelated widget"}, index.search("unrelated widget"), similarities,
        so_terms, top_k=2, ontology_name="so",
    )

    assert [c.match_kind for c in candidates] == [EMBEDDING, EMBEDDING]
    assert [c.match_id for c in candidates] == ["SO:0000110", "SO:0000001"]


def test_blend_always_returns_top_k_embedding_hits(so_terms):
    """Lexical hits must not eat into the embedding quota."""
    index = LexicalIndex(so_terms)
    similarities = np.array([0.95, 0.80, 0.70])

    candidates = blend_candidates(
        {"name": "enhancers"}, index.search("enhancers"), similarities, so_terms,
        top_k=2, ontology_name="so",
    )

    assert sum(1 for c in candidates if c.match_kind == EMBEDDING) == 2


def test_candidate_to_dict_columns():
    candidate = CandidateMatch(
        query_term="candidate enhancers", rank=1, match_kind=HEAD_NOUN,
        match_ontology="so", match_id="SO:0000165", match_term="enhancer",
        matched_on="enhancer", score=0.31, match_definition="A cis-acting sequence",
        query_category="FeatureType", query_subset="regulatory", query_mapping=None,
    )
    row = candidate.to_dict()
    assert row["onga_term"] == "candidate enhancers"
    assert row["match_id"] == "SO:0000165"
    assert row["match_kind"] == HEAD_NOUN
    assert row["existing_mapping"] == ""


@pytest.fixture
def candidate_embeddings_dir(tmp_path):
    """Mock .npz files whose metadata carries labels and synonyms."""
    onga_emb = np.array([[1.0, 0.0], [0.0, 1.0]])
    onga_meta = [
        {"name": "candidate enhancers", "category": "FeatureType",
         "subset": "regulatory", "definition": "Putative enhancers",
         "meaning": None},
        {"name": "contigs", "category": "FeatureType", "subset": "assembly",
         "definition": "Contiguous sequences", "meaning": "edam:data_0006"},
    ]
    np.savez(tmp_path / "onga.npz", embeddings=onga_emb,
             metadata=np.array(onga_meta, dtype=object))

    so_emb = np.array([[0.0, 1.0], [1.0, 0.0]])
    so_meta = [
        {"id": "SO:0000165", "name": "enhancer", "ontology": "so",
         "definition": "A cis-acting sequence", "synonyms": []},
        {"id": "SO:0000149", "name": "contig", "ontology": "so",
         "definition": "A contiguous sequence", "synonyms": ["contig sequence"]},
    ]
    np.savez(tmp_path / "so.npz", embeddings=so_emb,
             metadata=np.array(so_meta, dtype=object))
    return tmp_path


def test_ontology_terms_round_trip_from_metadata(candidate_embeddings_dir):
    searcher = SimilaritySearcher(candidate_embeddings_dir)
    terms = searcher.ontology_terms("so")
    assert [t.id for t in terms] == ["SO:0000165", "SO:0000149"]
    assert terms[1].synonyms == ["contig sequence"]


def test_find_candidates_blends_for_every_onga_term(candidate_embeddings_dir):
    searcher = SimilaritySearcher(candidate_embeddings_dir)
    results = searcher.find_candidates("so", top_k=1)

    assert len(results) == 2
    # "candidate enhancers" embeds orthogonally to SO:0000165, so only the
    # lexical matcher can find it.
    first = results[0]
    assert first[0].match_id == "SO:0000165"
    assert first[0].match_kind == HEAD_NOUN
    assert first[0].score == pytest.approx(0.0)
    assert first[0].query_category == "FeatureType"

    second = results[1]
    assert second[0].match_id == "SO:0000149"
    assert second[0].match_kind == WHOLE_NAME
    assert second[0].query_mapping == "edam:data_0006"


def test_find_candidates_for_term(candidate_embeddings_dir):
    searcher = SimilaritySearcher(candidate_embeddings_dir)
    candidates = searcher.find_candidates_for_term("so", "candidate enhancers", top_k=1)
    assert candidates[0].match_id == "SO:0000165"
    assert candidates[0].match_kind == HEAD_NOUN


def test_find_candidates_for_unknown_term_raises(candidate_embeddings_dir):
    searcher = SimilaritySearcher(candidate_embeddings_dir)
    with pytest.raises(KeyError):
        searcher.find_candidates_for_term("so", "no such term")


def test_lexical_index_is_cached(candidate_embeddings_dir):
    searcher = SimilaritySearcher(candidate_embeddings_dir)
    assert searcher.lexical_index("so") is searcher.lexical_index("so")


def test_embedding_only_search_still_works(candidate_embeddings_dir):
    """find_similar_terms must be unaffected by the blended additions."""
    searcher = SimilaritySearcher(candidate_embeddings_dir)
    results = searcher.find_similar_terms("so", top_k=1, threshold=0.0)
    assert len(results) == 2
    assert results[0][0].match_term == "contig"
    assert isinstance(results[0][0], SimilarityResult)
