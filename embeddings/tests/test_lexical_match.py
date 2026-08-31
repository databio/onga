"""Tests for the lexical matcher."""

from pathlib import Path

import pytest

from onga_embeddings.lexical_match import (
    HEAD_NOUN,
    WHOLE_NAME,
    LexicalIndex,
    build_lexical_index,
    normalize,
    token_suffixes,
    variants,
)
from onga_embeddings.ontology_loader import OntologyTerm, load_ontology


SO_OBO_PATH = Path(__file__).parent.parent / "data" / "ontologies" / "so.obo"


@pytest.fixture
def terms():
    """A miniature ontology exercising names, synonyms and shared head nouns."""
    return [
        OntologyTerm("SO:0000165", "enhancer", "A cis-acting sequence", ontology="so"),
        OntologyTerm("SO:0000167", "promoter", "A regulatory region", ontology="so"),
        OntologyTerm("SO:0000149", "contig", "A contiguous sequence", ontology="so"),
        OntologyTerm(
            "SO:0001019",
            "copy_number_variation",
            "A variation in copy number",
            synonyms=["copy number variation", "CNV"],
            ontology="so",
        ),
        OntologyTerm(
            "SO:0000694",
            "SNP",
            "A single nucleotide polymorphism",
            synonyms=["single nucleotide polymorphism"],
            ontology="so",
        ),
        OntologyTerm(
            "SO:0002307", "chromatin_loop", "A chromatin loop", ontology="so"
        ),
    ]


@pytest.fixture
def index(terms):
    return build_lexical_index(terms)


class TestNormalize:
    """Tests for label normalisation."""

    def test_lowercases_and_strips_punctuation(self):
        assert normalize("Candidate Cis-Regulatory Elements!") == (
            "candidate cis regulatory elements"
        )

    def test_underscores_and_slashes_become_spaces(self):
        assert normalize("copy_number_variation") == "copy number variation"
        assert normalize("A/B compartments") == "a b compartments"
        assert normalize("open-chromatin") == "open chromatin"

    def test_collapses_whitespace(self):
        assert normalize("  open   chromatin  ") == "open chromatin"

    def test_keeps_digits(self):
        assert normalize("m6A methylation state") == "m6a methylation state"


class TestVariants:
    """Tests for singular/plural variant generation."""

    def test_normalized_form_comes_first(self):
        assert variants("candidate enhancers")[0] == "candidate enhancers"

    def test_known_plural_is_singularized(self):
        assert variants("candidate enhancers") == [
            "candidate enhancers",
            "candidate enhancer",
        ]

    def test_generic_trailing_s_is_stripped(self):
        assert variants("gRNAs") == ["grnas", "grna"]

    def test_singular_input_yields_one_variant(self):
        assert variants("enhancer") == ["enhancer"]

    def test_short_words_are_not_stripped(self):
        # len <= 3 and not in SINGULARIZE, so no bogus singular
        assert variants("its") == ["its"]

    def test_order_is_deterministic(self):
        # A set would depend on the interpreter hash seed; a list must not.
        assert variants("peaks") == variants("peaks") == ["peaks", "peak"]


class TestTokenSuffixes:
    """Tests for trailing token n-gram generation."""

    def test_longest_first_with_offsets(self):
        assert token_suffixes("candidate enhancers") == [
            ("candidate enhancers", 0),
            ("candidate enhancer", 0),
            ("enhancers", 1),
            ("enhancer", 1),
        ]

    def test_single_token(self):
        assert token_suffixes("contigs") == [("contigs", 0), ("contig", 0)]

    def test_empty_string(self):
        assert token_suffixes("") == []

    def test_three_token_name_reaches_head_noun(self):
        suffixes = dict(token_suffixes("open chromatin regions"))
        assert suffixes["open chromatin regions"] == 0
        assert suffixes["chromatin regions"] == 1
        assert suffixes["region"] == 2


class TestLexicalIndex:
    """Tests for the index and its ranked search."""

    def test_len_counts_terms(self, index, terms):
        assert len(index) == len(terms)

    def test_whole_name_match(self, index):
        hits = index.search("contigs")
        assert len(hits) == 1
        assert hits[0].term.id == "SO:0000149"
        assert hits[0].match_kind == WHOLE_NAME
        assert hits[0].is_whole_name
        assert hits[0].suffix_start == 0
        assert hits[0].label_kind == "name"

    def test_head_noun_match(self, index):
        """The motivating case: embeddings rank this ~0.31, lexical nails it."""
        hits = index.search("candidate enhancers")
        assert [h.term.id for h in hits] == ["SO:0000165"]
        assert hits[0].match_kind == HEAD_NOUN
        assert hits[0].suffix_start == 1
        assert hits[0].matched_on == "enhancer"
        assert not hits[0].is_whole_name

    def test_synonym_match(self, index):
        """A query matching only a synonym still resolves, and says so."""
        hits = index.search("CNVs")
        assert [h.term.id for h in hits] == ["SO:0001019"]
        assert hits[0].label_kind == "synonym"
        assert hits[0].matched_on == "CNV"
        assert hits[0].match_kind == WHOLE_NAME

    def test_name_wins_over_synonym_for_the_same_variant(self, index):
        hits = index.search("copy number variation")
        assert [h.term.id for h in hits] == ["SO:0001019"]
        assert hits[0].label_kind == "name"
        assert hits[0].matched_on == "copy_number_variation"

    def test_underscored_name_matches_spaced_query(self, index):
        hits = index.search("chromatin loops")
        assert [h.term.id for h in hits] == ["SO:0002307"]
        assert hits[0].match_kind == WHOLE_NAME

    def test_plural_query_matches_singular_synonym(self, index):
        hits = index.search("SNPs")
        assert [h.term.id for h in hits] == ["SO:0000694"]
        assert hits[0].match_kind == WHOLE_NAME

    def test_longest_suffix_wins(self, terms):
        """A whole-name match must not be diluted by shorter head-noun hits."""
        extended = terms + [
            OntologyTerm("SO:9999999", "candidate enhancer", "", ontology="so")
        ]
        hits = LexicalIndex(extended).search("candidate enhancers")
        assert [h.term.id for h in hits] == ["SO:9999999"]
        assert hits[0].match_kind == WHOLE_NAME

    def test_all_terms_sharing_a_head_noun_are_returned(self, terms):
        extended = terms + [
            OntologyTerm("SO:8888888", "enhancer", "A duplicate label", ontology="so")
        ]
        hits = LexicalIndex(extended).search("predicted enhancers")
        assert [h.term.id for h in hits] == ["SO:0000165", "SO:8888888"]
        assert all(h.match_kind == HEAD_NOUN for h in hits)

    def test_deduplicates_by_term_id(self):
        """A term whose name and synonym normalise alike appears once."""
        dup = OntologyTerm(
            "SO:0000165", "enhancers", "", synonyms=["enhancer"], ontology="so"
        )
        hits = LexicalIndex([dup]).search("enhancer")
        assert len(hits) == 1
        assert hits[0].term.id == "SO:0000165"

    def test_no_match_returns_empty(self, index):
        assert index.search("nonexistent widget thing") == []

    def test_has_whole_name_match(self, index):
        assert index.has_whole_name_match("contigs")
        assert not index.has_whole_name_match("candidate enhancers")

    def test_has_any_match_includes_head_nouns(self, index):
        assert index.has_any_match("contigs")
        assert index.has_any_match("candidate enhancers")
        assert not index.has_any_match("nonexistent widget thing")

    def test_contains_uses_normalized_variants(self, index):
        assert "enhancer" in index
        assert "copy number variation" in index
        assert "widget" not in index

    def test_empty_labels_are_skipped(self):
        index = LexicalIndex([OntologyTerm("SO:1", "", "", ontology="so")])
        assert index.search("") == []


@pytest.mark.skipif(not SO_OBO_PATH.exists(), reason="so.obo not downloaded")
class TestLexicalIndexAgainstSO:
    """Regression tests against the real Sequence Ontology release."""

    @pytest.fixture(scope="class")
    def so_index(self):
        return build_lexical_index(load_ontology(SO_OBO_PATH, "so"))

    def test_index_covers_whole_ontology(self, so_index):
        assert len(so_index) > 2000

    def test_candidate_enhancers_finds_so_enhancer(self, so_index):
        hits = so_index.search("candidate enhancers")
        assert hits[0].term.id == "SO:0000165"
        assert hits[0].match_kind == HEAD_NOUN

    def test_known_whole_name_matches(self, so_index):
        for name, so_id in [
            ("contigs", "SO:0000149"),
            ("reads", "SO:0000150"),
            ("splice junctions", "SO:0001421"),
        ]:
            hits = so_index.search(name)
            assert hits, f"no lexical hit for {name!r}"
            assert hits[0].match_kind == WHOLE_NAME
            assert so_id in {h.term.id for h in hits}
