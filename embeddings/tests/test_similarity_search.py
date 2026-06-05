"""Tests for similarity search module."""

import numpy as np
import pytest
from pathlib import Path
import tempfile

from onga_embeddings.similarity_search import (
    InternalSimilarityPair,
    SimilarityResult,
    SimilaritySearcher,
    TermSimilarityResults,
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
