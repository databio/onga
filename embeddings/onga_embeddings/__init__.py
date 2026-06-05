"""ONGA Embeddings - Compare ONGA terms against genomics ontologies."""

from onga_embeddings.embedding_model import (
    EmbeddingModel,
    PUBMEDBERT,
    MINILM,
    save_embeddings,
    load_embeddings,
)
from onga_embeddings.onga_parser import ONGATerm, parse_onga
from onga_embeddings.ontology_loader import OntologyTerm, load_ontology
from onga_embeddings.similarity_search import (
    InternalSimilarityPair,
    SimilarityResult,
    SimilaritySearcher,
    TermSimilarityResults,
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
    "InternalSimilarityPair",
    "SimilarityResult",
    "SimilaritySearcher",
    "TermSimilarityResults",
    "ReportGenerator",
]
__version__ = "0.1.0"
