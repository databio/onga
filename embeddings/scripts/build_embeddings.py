#!/usr/bin/env python3
"""Build embeddings for ONGA and all downloaded ontologies.

Usage:
    python scripts/build_embeddings.py                    # Use PubMedBERT (default)
    python scripts/build_embeddings.py --model minilm     # Use MiniLM (faster)
    python scripts/build_embeddings.py --onga-only        # Only build ONGA embeddings
    python scripts/build_embeddings.py --ontology edam    # Only build specific ontology
"""

import argparse
from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from onga_embeddings.embedding_model import (
    EmbeddingModel,
    PUBMEDBERT,
    MINILM,
    save_embeddings,
)
from onga_embeddings.ontology_loader import load_ontology
from onga_embeddings.onga_parser import parse_onga

# Default paths
PROJECT_ROOT = Path(__file__).parent.parent
ONTOLOGY_DIR = PROJECT_ROOT / "data" / "ontologies"
EMBEDDING_DIR = PROJECT_ROOT / "data" / "embeddings"
ONGA_PATH = Path(__file__).resolve().parents[1] / ".." / "src" / "file_content.yaml"


def build_onga_embeddings(model: EmbeddingModel, output_dir: Path) -> int:
    """Build embeddings for ONGA terms.

    Args:
        model: Initialized embedding model.
        output_dir: Directory for output .npz file.

    Returns:
        Number of terms embedded.
    """
    print(f"Building ONGA embeddings from {ONGA_PATH}...")

    terms = parse_onga(ONGA_PATH)
    if not terms:
        print("  WARNING: No ONGA terms found!")
        return 0

    texts = [t.embedding_text() for t in terms]
    metadata = [t.to_dict() for t in terms]

    embeddings = model.embed(texts)

    output_path = output_dir / "onga.npz"
    save_embeddings(output_path, embeddings, metadata, model.model_name)
    print(f"  Saved {len(terms)} ONGA terms to {output_path}")

    return len(terms)


def build_ontology_embeddings(
    model: EmbeddingModel,
    ontology_dir: Path,
    output_dir: Path,
    ontology_name: str | None = None,
) -> tuple[dict[str, int], dict[str, str]]:
    """Build embeddings for downloaded ontologies.

    Args:
        model: Initialized embedding model.
        ontology_dir: Directory containing .owl/.obo files.
        output_dir: Directory for output .npz files.
        ontology_name: If set, only build this ontology.

    Returns:
        Tuple of (built: dict mapping ontology name to term count,
                  failed: dict mapping ontology name to error message).
    """
    results = {}
    failures = {}

    # Find ontology files
    onto_files = list(ontology_dir.glob("*.owl")) + list(ontology_dir.glob("*.obo"))
    if not onto_files:
        print(f"No ontology files found in {ontology_dir}")
        return results, failures

    # Filter if specific ontology requested
    if ontology_name:
        onto_files = [f for f in onto_files if f.stem == ontology_name]
        if not onto_files:
            print(f"Ontology '{ontology_name}' not found in {ontology_dir}")
            return results, failures

    for onto_file in onto_files:
        name = onto_file.stem
        output_path = output_dir / f"{name}.npz"

        # Skip if already exists
        if output_path.exists():
            print(f"Skipping {name} (already exists at {output_path})")
            continue

        print(f"Building {name} embeddings from {onto_file}...")

        try:
            terms = list(load_ontology(str(onto_file), name))
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            print(f"  FAILED loading {name}: {msg}")
            failures[name] = msg
            continue

        if not terms:
            print(f"  WARNING: No terms found in {name}")
            continue

        texts = [t.embedding_text() for t in terms]
        metadata = [t.to_dict() for t in terms]

        # Process in batches with progress bar for large ontologies
        print(f"  Embedding {len(terms)} terms...")
        embeddings = model.embed(texts)

        save_embeddings(output_path, embeddings, metadata, model.model_name)
        print(f"  Saved {len(terms)} {name} terms to {output_path}")

        results[name] = len(terms)

    return results, failures


def main():
    parser = argparse.ArgumentParser(
        description="Build embeddings for ONGA and ontologies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--model",
        choices=["pubmedbert", "minilm"],
        default="pubmedbert",
        help="Embedding model to use (default: pubmedbert)",
    )
    parser.add_argument(
        "--onga-only",
        action="store_true",
        help="Only build ONGA embeddings",
    )
    parser.add_argument(
        "--ontology",
        type=str,
        help="Only build embeddings for this specific ontology",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=EMBEDDING_DIR,
        help=f"Output directory for embeddings (default: {EMBEDDING_DIR})",
    )
    parser.add_argument(
        "--ontology-dir",
        type=Path,
        default=ONTOLOGY_DIR,
        help=f"Directory containing ontology files (default: {ONTOLOGY_DIR})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing embeddings",
    )

    args = parser.parse_args()

    # Select model
    model_name = PUBMEDBERT if args.model == "pubmedbert" else MINILM
    print(f"Using model: {model_name}")
    model = EmbeddingModel(model_name)

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Track totals
    total_terms = 0

    # Build ONGA embeddings
    if not args.ontology:
        onga_output = args.output_dir / "onga.npz"
        if args.force and onga_output.exists():
            onga_output.unlink()
        if not onga_output.exists():
            total_terms += build_onga_embeddings(model, args.output_dir)
        else:
            print(f"Skipping ONGA (already exists at {onga_output})")

    # Build ontology embeddings
    failed = {}
    if not args.onga_only:
        results, failed = build_ontology_embeddings(
            model,
            args.ontology_dir,
            args.output_dir,
            args.ontology,
        )
        total_terms += sum(results.values())

    # Summary
    print(f"\nTotal: {total_terms} terms embedded")
    print(f"Output directory: {args.output_dir}")

    # List generated files
    print("\nGenerated files:")
    for f in sorted(args.output_dir.glob("*.npz")):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {f.name}: {size_mb:.1f} MB")

    if failed:
        print(f"\nFAILED ({len(failed)} ontologies):")
        for name, err in failed.items():
            print(f"  {name}: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
