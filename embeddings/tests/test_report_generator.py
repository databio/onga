"""Tests for report generator module."""

import json
import pytest
from pathlib import Path

from onga_embeddings.similarity_search import (
    InternalSimilarityPair,
    SimilarityResult,
    TermSimilarityResults,
)
from onga_embeddings.report_generator import ReportGenerator


@pytest.fixture
def sample_results():
    """Create sample similarity results for testing."""
    return [
        TermSimilarityResults(
            term_name="alignments",
            category="DataType",
            subset="alignment",
            definition="Sequence alignment data",
            existing_mapping="edam:data_0863",
            matches_by_ontology={
                "edam": [
                    SimilarityResult(
                        "alignments", "ONGA", "Sequence alignment", "edam",
                        "data_0863", 0.92, "An alignment of sequences"
                    ),
                ],
                "so": [
                    SimilarityResult(
                        "alignments", "ONGA", "aligned_sequence", "so",
                        "SO:0000149", 0.65, "A sequence that has been aligned"
                    ),
                ]
            }
        ),
        TermSimilarityResults(
            term_name="novel_term",
            category="DataType",
            subset="deep_learning",
            definition="Some novel concept",
            existing_mapping=None,
            matches_by_ontology={
                "edam": [
                    SimilarityResult(
                        "novel_term", "ONGA", "Data", "edam",
                        "data_0006", 0.35, "Generic data"
                    ),
                ]
            }
        ),
    ]


@pytest.fixture
def sample_pairs():
    """Create sample internal similarity pairs for testing."""
    return [
        InternalSimilarityPair(
            term1_name="signal", term1_category="DataType", term1_subset="signal",
            term2_name="signal_all_reads", term2_category="DataType", term2_subset="signal",
            similarity=0.91, crosses_categories=False
        ),
        InternalSimilarityPair(
            term1_name="peaks", term1_category="DataType", term1_subset="peak_set",
            term2_name="peak_regions", term2_category="FeatureType", term2_subset="peak_set",
            similarity=0.88, crosses_categories=True
        ),
    ]


def test_generate_mapping_report_json(tmp_path, sample_results):
    generator = ReportGenerator(tmp_path)
    outputs = generator.generate_mapping_report(sample_results, format="json")

    assert "json" in outputs
    assert outputs["json"].exists()

    with open(outputs["json"]) as f:
        data = json.load(f)

    assert data["total_terms"] == 2
    assert len(data["terms"]) == 2


def test_generate_mapping_report_markdown(tmp_path, sample_results):
    generator = ReportGenerator(tmp_path)
    outputs = generator.generate_mapping_report(sample_results, format="markdown")

    assert "markdown" in outputs
    assert outputs["markdown"].exists()

    content = outputs["markdown"].read_text()
    assert "# ONGA Ontology Mapping Report" in content
    assert "alignments" in content


def test_generate_internal_similarity_report(tmp_path, sample_pairs):
    generator = ReportGenerator(tmp_path)
    outputs = generator.generate_internal_similarity_report(sample_pairs, format="both")

    assert "json" in outputs
    assert "markdown" in outputs

    with open(outputs["json"]) as f:
        data = json.load(f)

    assert data["total_pairs"] == 2
    assert data["cross_category_pairs"] == 1


def test_generate_gap_analysis_report(tmp_path, sample_results):
    generator = ReportGenerator(tmp_path)
    gap_terms = [r for r in sample_results if r.max_similarity() < 0.5]
    outputs = generator.generate_gap_analysis_report(gap_terms, sample_results, format="both")

    assert "json" in outputs
    assert "markdown" in outputs

    with open(outputs["json"]) as f:
        data = json.load(f)

    assert data["gap_terms_count"] == 1
    assert "novel_term" in str(data)


def test_generate_all_reports(tmp_path, sample_results, sample_pairs):
    generator = ReportGenerator(tmp_path)
    all_outputs = generator.generate_all_reports(sample_results, sample_pairs, gap_threshold=0.5)

    assert "mapping" in all_outputs
    assert "internal_similarity" in all_outputs
    assert "gap_analysis" in all_outputs

    # Check all files exist
    for report_type, paths in all_outputs.items():
        for fmt, path in paths.items():
            assert path.exists(), f"Missing {report_type} {fmt} report"
