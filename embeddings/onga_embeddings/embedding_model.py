"""Embedding model wrapper for biomedical text."""

from pathlib import Path
from typing import TypeAlias

import numpy as np
from sentence_transformers import SentenceTransformer

Metadata: TypeAlias = list[dict]

# Model options
PUBMEDBERT = "NeuML/pubmedbert-base-embeddings"  # 768-dim, domain-specific
MINILM = "all-MiniLM-L6-v2"  # 384-dim, fast fallback


class EmbeddingModel:
    """Wrapper around sentence-transformers for generating embeddings.

    Attributes:
        model_name: HuggingFace model identifier
        embedding_dim: Dimension of output embeddings (768 for PubMedBERT, 384 for MiniLM)
    """

    def __init__(self, model_name: str = PUBMEDBERT):
        """Initialize the embedding model.

        Args:
            model_name: HuggingFace model identifier. Defaults to PubMedBERT.
        """
        self.model_name = model_name
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-load the model on first access."""
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def embedding_dim(self) -> int:
        """Return the embedding dimension for this model."""
        return self.model.get_sentence_embedding_dimension()

    def embed(
        self,
        texts: list[str],
        batch_size: int = 32,
        show_progress: bool = True,
    ) -> np.ndarray:
        """Generate normalized embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.
            batch_size: Number of texts to process at once.
            show_progress: Whether to show a progress bar.

        Returns:
            Normalized embeddings as float32 array of shape (len(texts), embedding_dim).
            Normalization enables cosine similarity via dot product.
        """
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
            normalize_embeddings=True,  # Critical: enables cosine sim via dot product
        )
        return embeddings.astype(np.float32)

    def embed_single(self, text: str) -> np.ndarray:
        """Embed a single text string.

        Args:
            text: Text string to embed.

        Returns:
            Normalized embedding as float32 array of shape (embedding_dim,).
        """
        return self.embed([text], show_progress=False)[0]


def save_embeddings(
    path: Path,
    embeddings: np.ndarray,
    metadata: Metadata,
    model_name: str,
) -> None:
    """Save embeddings and metadata to .npz file.

    Args:
        path: Output path (should end in .npz).
        embeddings: Embedding array of shape (n_terms, embedding_dim).
        metadata: List of dicts with term information.
        model_name: Model identifier for provenance tracking.
    """
    np.savez_compressed(
        path,
        embeddings=embeddings,
        metadata=np.array(metadata, dtype=object),
        model_name=np.array(model_name),
    )


def load_embeddings(path: Path) -> tuple[np.ndarray, Metadata, str]:
    """Load embeddings and metadata from .npz file.

    Args:
        path: Path to .npz file.

    Returns:
        Tuple of (embeddings array, metadata list, model_name string).
    """
    data = np.load(path, allow_pickle=True)
    embeddings = data["embeddings"]
    metadata = data["metadata"].tolist()
    model_name = str(data["model_name"])
    return embeddings, metadata, model_name
