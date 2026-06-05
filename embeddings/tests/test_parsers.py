"""Tests for ONGA and ontology parsers."""

from pathlib import Path

import pytest

from onga_embeddings.onga_parser import ONGATerm, parse_onga
from onga_embeddings.ontology_loader import OntologyTerm, load_ontology


# Path to ONGA vocabulary (adjust if needed)
ONGA_PATH = Path(__file__).resolve().parents[2] / "src" / "file_content.yaml"


class TestONGAParser:
    """Tests for ONGA YAML parser."""

    @pytest.mark.skipif(not ONGA_PATH.exists(), reason="ONGA file not found")
    def test_parse_onga_returns_terms(self):
        """parse_onga should return a non-empty list of terms."""
        terms = parse_onga(ONGA_PATH)
        assert len(terms) > 0
        assert isinstance(terms[0], ONGATerm)

    @pytest.mark.skipif(not ONGA_PATH.exists(), reason="ONGA file not found")
    def test_parse_onga_has_both_categories(self):
        """parse_onga should return both DataType and FeatureType terms."""
        terms = parse_onga(ONGA_PATH)
        categories = {t.category for t in terms}
        assert "DataType" in categories
        assert "FeatureType" in categories

    @pytest.mark.skipif(not ONGA_PATH.exists(), reason="ONGA file not found")
    def test_parse_onga_extracts_subsets(self):
        """parse_onga should extract subset information."""
        terms = parse_onga(ONGA_PATH)
        subsets = {t.subset for t in terms}
        # Check for known subsets from the ONGA file
        assert "alignment" in subsets
        assert "peak_set" in subsets
        assert "signal_track" in subsets

    @pytest.mark.skipif(not ONGA_PATH.exists(), reason="ONGA file not found")
    def test_parse_onga_extracts_edam_mappings(self):
        """parse_onga should extract existing EDAM mappings."""
        terms = parse_onga(ONGA_PATH)
        edam_terms = [t for t in terms if t.edam_mapping is not None]
        # We know there are ~84 existing EDAM mappings
        assert len(edam_terms) > 50

    def test_onga_term_embedding_text(self):
        """ONGATerm.embedding_text should combine name and description."""
        term = ONGATerm(
            name="peaks",
            description="Discrete genomic regions of enrichment",
            category="DataType",
            subset="peak_set",
        )
        text = term.embedding_text()
        assert "peaks" in text
        assert "Discrete genomic regions" in text

    def test_onga_term_to_dict(self):
        """ONGATerm.to_dict should return expected keys."""
        term = ONGATerm(
            name="peaks",
            description="Test description",
            category="DataType",
            subset="peak_set",
            edam_mapping="edam:data_3002",
        )
        d = term.to_dict()
        assert d["name"] == "peaks"
        assert d["ontology"] == "ONGA"
        assert d["category"] == "DataType"


SO_OBO_PATH = Path(__file__).parent.parent / "data" / "ontologies" / "so.obo"


class TestOntologyLoader:
    """Tests for OWL/OBO ontology loader."""

    @pytest.mark.skipif(not SO_OBO_PATH.exists(), reason="so.obo not downloaded")
    def test_load_obo_with_obonet_fallback(self):
        """load_ontology should parse so.obo via obonet when pronto fails."""
        terms = list(load_ontology(SO_OBO_PATH, "so"))
        assert len(terms) > 1000
        assert all(t.ontology == "so" for t in terms)
        assert all(t.name for t in terms)

    def test_ontology_term_embedding_text_basic(self):
        """OntologyTerm.embedding_text should combine name and definition."""
        term = OntologyTerm(
            id="SO:0000001",
            name="region",
            definition="A sequence region",
            ontology="so",
        )
        text = term.embedding_text()
        assert "region" in text
        assert "sequence region" in text

    def test_ontology_term_embedding_text_with_synonyms(self):
        """OntologyTerm.embedding_text should include synonyms."""
        term = OntologyTerm(
            id="SO:0000001",
            name="region",
            definition="A sequence region",
            synonyms=["sequence feature", "genomic region", "locus", "extra"],
            ontology="so",
        )
        text = term.embedding_text()
        assert "Also known as:" in text
        assert "sequence feature" in text
        # Should limit to 3 synonyms
        assert "extra" not in text

    def test_ontology_term_to_dict(self):
        """OntologyTerm.to_dict should return expected keys."""
        term = OntologyTerm(
            id="EDAM:data_0863",
            name="Sequence alignment",
            definition="An alignment of sequences",
            synonyms=["alignment"],
            ontology="edam",
        )
        d = term.to_dict()
        assert d["id"] == "EDAM:data_0863"
        assert d["name"] == "Sequence alignment"
        assert d["ontology"] == "edam"
        assert "alignment" in d["synonyms"]
