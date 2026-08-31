"""Tests for ONGA and ontology parsers."""

from pathlib import Path

import pytest

from onga_embeddings.onga_parser import ONGATerm, parse_onga
from onga_embeddings.ontology_loader import OntologyTerm, load_ontology, parse_obo


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
    def test_parse_onga_extracts_meanings(self):
        """parse_onga should extract `meaning:` values from any ontology.

        `meaning:` is ontology-neutral -- it names the one identifier that IS
        the term. Cross-references to other ontologies live in the typed
        exact/close/broad/related mapping slots instead, so asserting a raw
        count of EDAM meanings would drift every time curation moves one.
        """
        terms = parse_onga(ONGA_PATH)
        with_meaning = [t for t in terms if t.meaning is not None]

        assert with_meaning, "no term carries a meaning"
        # A meaning is always a CURIE, never a bare label.
        for term in with_meaning:
            assert ":" in term.meaning, f"{term.name}: {term.meaning!r} is not a CURIE"

        # Meanings are drawn from more than one ontology.
        prefixes = {t.meaning.split(":", 1)[0] for t in with_meaning}
        assert "edam" in prefixes
        assert "SO" in prefixes

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
            meaning="edam:data_3002",
        )
        d = term.to_dict()
        assert d["name"] == "peaks"
        assert d["ontology"] == "ONGA"
        assert d["category"] == "DataType"


SO_OBO_PATH = Path(__file__).parent.parent / "data" / "ontologies" / "so.obo"


class TestOntologyLoader:
    """Tests for OWL/OBO ontology loader."""

    @pytest.mark.skipif(not SO_OBO_PATH.exists(), reason="so.obo not downloaded")
    def test_load_obo_needs_no_third_party_parser(self):
        """load_ontology should parse so.obo with the stdlib parser alone."""
        terms = list(load_ontology(SO_OBO_PATH, "so"))
        assert len(terms) > 1000
        assert all(t.ontology == "so" for t in terms)
        assert all(t.name for t in terms)

    @pytest.mark.skipif(not SO_OBO_PATH.exists(), reason="so.obo not downloaded")
    def test_load_obo_does_not_import_pronto_or_obonet(self, monkeypatch):
        """The OBO path must work in an environment without pronto/obonet."""
        import builtins

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.split(".")[0] in {"pronto", "obonet"}:
                raise ImportError(f"{name} is not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked)
        terms = list(load_ontology(SO_OBO_PATH, "so"))
        assert len(terms) > 1000

    @pytest.mark.skipif(not SO_OBO_PATH.exists(), reason="so.obo not downloaded")
    def test_parse_obo_returns_raw_stanzas(self):
        """parse_obo keeps the raw dict shape that build_so_sssom.py consumes."""
        raw = parse_obo(SO_OBO_PATH)
        by_id = {t["id"]: t for t in raw}
        assert by_id["SO:0000165"]["name"] == "enhancer"
        assert all("obsolete" not in t for t in raw)
        # Synonyms keep their scope, e.g. ("CNV", "EXACT").
        cnv = by_id["SO:0001019"]["synonyms"]
        assert all(len(pair) == 2 for pair in cnv)

    @pytest.mark.skipif(not SO_OBO_PATH.exists(), reason="so.obo not downloaded")
    def test_load_obo_carries_synonyms(self):
        """Synonym text must survive; the lexical matcher indexes it."""
        terms = {t.id: t for t in load_ontology(SO_OBO_PATH, "so")}
        assert "CNV" in terms["SO:0001019"].synonyms

    def test_load_owl_reports_missing_pronto(self, tmp_path, monkeypatch):
        """An OWL file without pronto installed should say what to install."""
        import builtins

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.split(".")[0] == "pronto":
                raise ImportError("no pronto")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked)
        owl = tmp_path / "edam.owl"
        owl.write_text("<rdf/>")
        with pytest.raises(ImportError, match="pronto"):
            list(load_ontology(owl, "edam"))

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
