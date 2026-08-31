"""ONGA Embeddings - Compare ONGA terms against genomics ontologies.

Two complementary searches, one code path:

* lexical (:mod:`onga_embeddings.lexical_match`) - normalised label and synonym
  matching, including head-noun suffixes, over any iterable of
  :class:`OntologyTerm`.
* embedding (:mod:`onga_embeddings.similarity_search`) - cosine similarity over
  cached sentence-transformer embeddings.

:meth:`SimilaritySearcher.find_candidates` blends the two.
"""

from onga_embeddings.embedding_model import (
    EmbeddingModel,
    PUBMEDBERT,
    MINILM,
    save_embeddings,
    load_embeddings,
)
from onga_embeddings.onga_parser import ONGATerm, parse_onga
from onga_embeddings.ontology_loader import (
    OntologyTerm,
    load_ontology,
    load_multiple_ontologies,
    parse_obo,
)
from onga_embeddings.lexical_match import (
    HEAD_NOUN,
    LEXICAL_MATCH_KINDS,
    LexicalHit,
    LexicalIndex,
    SINGULARIZE,
    WHOLE_NAME,
    build_lexical_index,
    normalize,
    token_suffixes,
    variants,
)
from onga_embeddings.similarity_search import (
    EMBEDDING,
    CandidateMatch,
    InternalSimilarityPair,
    SimilarityResult,
    SimilaritySearcher,
    TermSimilarityResults,
    blend_candidates,
)
from onga_embeddings.report_generator import ReportGenerator

__all__ = [
    "EmbeddingModel",
    "PUBMEDBERT",
    "MINILM",
    "save_embeddings",
    "load_embeddings",
    "ONGATerm",
    "parse_onga",
    "OntologyTerm",
    "load_ontology",
    "load_multiple_ontologies",
    "parse_obo",
    "HEAD_NOUN",
    "WHOLE_NAME",
    "EMBEDDING",
    "LEXICAL_MATCH_KINDS",
    "LexicalHit",
    "LexicalIndex",
    "SINGULARIZE",
    "build_lexical_index",
    "normalize",
    "token_suffixes",
    "variants",
    "CandidateMatch",
    "blend_candidates",
    "InternalSimilarityPair",
    "SimilarityResult",
    "SimilaritySearcher",
    "TermSimilarityResults",
    "ReportGenerator",
]
__version__ = "0.1.0"
