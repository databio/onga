"""Tests for report generator module."""

import json
import pytest
from pathlib import Path

from onga_embeddings.similarity_search import (
    InternalSimilarityPair,
    SimilarityResult,
    TermSimilarityResults,
)
from onga_embeddings.provenance import (
    build_provenance,
    gap_id,
    mapping_id,
    similarity_id,
)
from onga_embeddings.report_generator import ReportGenerator


@pytest.fixture
def provenance():
    return build_provenance(
        model_name="test-model",
        schema_fingerprint="sha256:abc",
        subject_count=2,
        ontologies=[{"name": "so", "source_file": "so.obo", "sha256": "sha256:1", "term_count": 1}],
        params={"threshold": 0.5},
    )


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
            term_id="ONGA_0000001",
            sid="term:ONGA_0000001",
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
            term_id="ONGA_0000002",
            sid="term:ONGA_0000002",
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
            similarity=0.91, crosses_categories=False,
            term1_id="ONGA_0000010", term1_sid="term:ONGA_0000010",
            term2_id="ONGA_0000011", term2_sid="term:ONGA_0000011",
        ),
        InternalSimilarityPair(
            term1_name="peaks", term1_category="DataType", term1_subset="peak_set",
            term2_name="peak_regions", term2_category="FeatureType", term2_subset="peak_set",
            similarity=0.88, crosses_categories=True,
            term1_id="ONGA_0000020", term1_sid="term:ONGA_0000020",
            term2_id="ONGA_0000021", term2_sid="term:ONGA_0000021",
        ),
    ]


def test_generate_mapping_report_json(tmp_path, provenance, sample_results):
    generator = ReportGenerator(tmp_path, provenance)
    outputs = generator.generate_mapping_report(sample_results, format="json")

    assert "json" in outputs
    assert outputs["json"].exists()

    with open(outputs["json"]) as f:
        data = json.load(f)

    assert data["total_terms"] == 2
    assert len(data["terms"]) == 2


def test_generate_mapping_report_markdown(tmp_path, provenance, sample_results):
    generator = ReportGenerator(tmp_path, provenance)
    outputs = generator.generate_mapping_report(sample_results, format="markdown")

    assert "markdown" in outputs
    assert outputs["markdown"].exists()

    content = outputs["markdown"].read_text()
    assert "# ONGA Ontology Mapping Report" in content
    assert "alignments" in content


def test_generate_internal_similarity_report(tmp_path, provenance, sample_pairs):
    generator = ReportGenerator(tmp_path, provenance)
    outputs = generator.generate_internal_similarity_report(sample_pairs, format="both")

    assert "json" in outputs
    assert "markdown" in outputs

    with open(outputs["json"]) as f:
        data = json.load(f)

    assert data["total_pairs"] == 2
    assert data["cross_category_pairs"] == 1


def test_generate_gap_analysis_report(tmp_path, provenance, sample_results):
    generator = ReportGenerator(tmp_path, provenance)
    gap_terms = [r for r in sample_results if r.max_similarity() < 0.5]
    outputs = generator.generate_gap_analysis_report(gap_terms, sample_results, format="both")

    assert "json" in outputs
    assert "markdown" in outputs

    with open(outputs["json"]) as f:
        data = json.load(f)

    assert data["gap_terms_count"] == 1
    assert "novel_term" in str(data)


def test_generate_all_reports(tmp_path, provenance, sample_results, sample_pairs):
    generator = ReportGenerator(tmp_path, provenance)
    all_outputs = generator.generate_all_reports(sample_results, sample_pairs, gap_threshold=0.5)

    assert "mapping" in all_outputs
    assert "internal_similarity" in all_outputs
    assert "gap_analysis" in all_outputs

    # Check all files exist
    for report_type, paths in all_outputs.items():
        for fmt, path in paths.items():
            assert path.exists(), f"Missing {report_type} {fmt} report"


def test_every_report_carries_provenance(tmp_path, provenance, sample_results, sample_pairs):
    generator = ReportGenerator(tmp_path, provenance)
    all_outputs = generator.generate_all_reports(sample_results, sample_pairs, gap_threshold=0.5)
    for report_type, paths in all_outputs.items():
        data = json.loads(paths["json"].read_text())
        assert data["provenance"] == provenance, report_type
        assert "generated_at" not in data
    assert set(provenance) == {
        "generated_at", "generator_version", "model_name", "schema_fingerprint",
        "subject_count", "ontologies", "params",
    }
    assert provenance["generator_version"].startswith("onga-embeddings/")


def test_mapping_suggestions_have_ids_and_subjects(tmp_path, provenance, sample_results):
    generator = ReportGenerator(tmp_path, provenance)
    data = json.loads(
        generator.generate_mapping_report(sample_results, format="json")["json"].read_text()
    )
    term = next(t for t in data["terms"] if t["onga_term"] == "alignments")
    assert term["subject"] == "term:ONGA_0000001"
    assert term["onga_term_id"] == "ONGA_0000001"
    by_object = {m["term_id"]: m for m in term["suggested_mappings"]}
    assert by_object["data_0863"]["id"] == mapping_id("ONGA_0000001", "edam", "data_0863")
    assert by_object["data_0863"]["subjects"] == ["term:ONGA_0000001"]
    assert by_object["SO:0000149"]["id"].startswith("map:")
    ids = [m["id"] for t in data["terms"] for m in t["suggested_mappings"]]
    assert len(ids) == len(set(ids))


def test_pairs_have_ids_subjects_and_machine_recommendation(tmp_path, provenance, sample_pairs):
    generator = ReportGenerator(tmp_path, provenance)
    data = json.loads(
        generator.generate_internal_similarity_report(sample_pairs, format="json")["json"].read_text()
    )
    first, second = data["pairs"]
    assert first["id"] == similarity_id("ONGA_0000010", "ONGA_0000011")
    assert first["subjects"] == ["term:ONGA_0000010", "term:ONGA_0000011"]
    assert first["machine_recommendation"] == "hierarchy"
    assert second["machine_recommendation"] == "review_cross_category"


def test_gap_items_have_ids_and_onga_term(tmp_path, provenance, sample_results):
    generator = ReportGenerator(tmp_path, provenance)
    gap_terms = [r for r in sample_results if r.max_similarity() < 0.5]
    data = json.loads(
        generator.generate_gap_analysis_report(gap_terms, sample_results, format="json")["json"].read_text()
    )
    (item,) = data["by_subset"]["deep_learning"]["terms"]
    assert item["onga_term"] == "novel_term"
    assert "name" not in item
    assert item["id"] == gap_id("ONGA_0000002")
    assert item["subjects"] == ["term:ONGA_0000002"]


def test_unresolved_term_is_an_error(tmp_path, provenance, sample_results):
    sample_results[0].sid = ""
    generator = ReportGenerator(tmp_path, provenance)
    with pytest.raises(ValueError, match="no subject id"):
        generator.generate_mapping_report(sample_results, format="json")


def test_finding_ids_hash_ids_not_order():
    assert similarity_id("ONGA_0000001", "ONGA_0000002") == similarity_id("ONGA_0000002", "ONGA_0000001")
    assert similarity_id("ONGA_0000001", "ONGA_0000002") != similarity_id("ONGA_0000001", "ONGA_0000003")
    assert gap_id("ONGA_0000001").startswith("gap:")
    assert len(gap_id("ONGA_0000001")) == len("gap:") + 12
    assert mapping_id("ONGA_0000001", "so", "SO:1") != mapping_id("ONGA_0000001", "edam", "SO:1")


REPO_ROOT = Path(__file__).resolve().parents[2]
SUBJECTS = REPO_ROOT / "curation" / "subjects.json"
CROSSWALK = REPO_ROOT / "curation" / "term_crosswalk.json"


@pytest.mark.skipif(not SUBJECTS.exists(), reason="curation/subjects.json not generated")
def test_registry_resolves_live_labels():
    from onga_embeddings.onga_parser import parse_onga
    from onga_embeddings.provenance import SubjectRegistry

    registry = SubjectRegistry(SUBJECTS, CROSSWALK)
    terms = parse_onga(REPO_ROOT / "src" / "file_content.yaml")
    for term in terms:
        record = registry.resolve(term.name, term.category)
        assert record["term_id"] == term.term_id
        assert record["sid"] == f"term:{term.term_id}"
    with pytest.raises(KeyError, match="not in"):
        registry.resolve("no such term", "DataType")
    other = "FeatureType" if terms[0].category == "DataType" else "DataType"
    with pytest.raises(KeyError, match="is now in"):
        registry.resolve(terms[0].name, other)
