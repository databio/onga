#!/usr/bin/env python3
"""Build embeddings for ONGA and all downloaded ontologies.

Usage:
    python scripts/build_embeddings.py                    # Use PubMedBERT (default)
    python scripts/build_embeddings.py --model minilm     # Use MiniLM (faster)
    python scripts/build_embeddings.py --onga-only        # Only build ONGA embeddings
    python scripts/build_embeddings.py --ontology edam    # Only build specific ontology

An existing .npz is reused only while it still matches its source: onga.npz
records the ``schema_fingerprint`` of ``curation/subjects.json``, and each
ontology .npz the sha256 of its ontology file. A mismatch rebuilds it and says
why; ``--force`` always rebuilds.
"""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

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
from onga_embeddings.provenance import DEFAULT_SUBJECTS, sha256_file

# Default paths
PROJECT_ROOT = Path(__file__).parent.parent
ONTOLOGY_DIR = PROJECT_ROOT / "data" / "ontologies"
EMBEDDING_DIR = PROJECT_ROOT / "data" / "embeddings"
ONGA_PATH = Path(__file__).resolve().parents[1] / ".." / "src" / "file_content.yaml"


def stale_reason(npz_path: Path, key: str, current: str) -> str | None:
    """Why ``npz_path`` must be rebuilt, or None when it is current.

    The .npz is current when it exists and its stored ``key`` equals ``current``.
    """
    if not npz_path.exists():
        return "missing"
    with np.load(npz_path, allow_pickle=True) as data:
        if key not in data.files:
            return f"records no {key}"
        stored = str(data[key])
    if stored != current:
        return f"{key} changed ({stored} -> {current})"
    return None


def build_onga_embeddings(
    model: EmbeddingModel, output_dir: Path, schema_fingerprint: str
) -> int:
    """Build embeddings for ONGA terms.

    Args:
        model: Initialized embedding model.
        output_dir: Directory for output .npz file.
        schema_fingerprint: ``subjects.json`` fingerprint stored in the .npz.

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
    save_embeddings(
        output_path, embeddings, metadata, model.model_name,
        provenance={"schema_fingerprint": schema_fingerprint},
    )
    print(f"  Saved {len(terms)} ONGA terms to {output_path}")

    return len(terms)


def build_ontology_embeddings(
    model: EmbeddingModel,
    ontology_dir: Path,
    output_dir: Path,
    ontology_name: str | None = None,
    force: bool = False,
) -> tuple[dict[str, int], dict[str, str]]:
    """Build embeddings for downloaded ontologies.

    Args:
        model: Initialized embedding model.
        ontology_dir: Directory containing .owl/.obo files.
        output_dir: Directory for output .npz files.
        ontology_name: If set, only build this ontology.
        force: Rebuild even when the .npz matches its source file.

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

        source_sha256 = sha256_file(onto_file)
        reason = "--force" if force else stale_reason(
            output_path, "source_sha256", source_sha256
        )
        if reason is None:
            print(f"Skipping {name} (up to date at {output_path})")
            continue

        print(f"Building {name} embeddings from {onto_file} ({reason})...")

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

        save_embeddings(
            output_path, embeddings, metadata, model.model_name,
            provenance={"source_file": onto_file.name, "source_sha256": source_sha256},
        )
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
        "--subjects",
        type=Path,
        default=DEFAULT_SUBJECTS,
        help=f"Subject registry whose schema_fingerprint onga.npz records (default: {DEFAULT_SUBJECTS})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild embeddings even when they match their source",
    )

    args = parser.parse_args()

    # Select model (loaded lazily, so an up-to-date run never loads it)
    model_name = PUBMEDBERT if args.model == "pubmedbert" else MINILM
    print(f"Using model: {model_name}")
    model = EmbeddingModel(model_name)

    with open(args.subjects) as fh:
        schema_fingerprint = json.load(fh)["schema_fingerprint"]

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Track totals
    total_terms = 0

    # Build ONGA embeddings
    if not args.ontology:
        onga_output = args.output_dir / "onga.npz"
        reason = "--force" if args.force else stale_reason(
            onga_output, "schema_fingerprint", schema_fingerprint
        )
        if reason is None:
            print(f"Skipping ONGA (up to date at {onga_output})")
        else:
            print(f"Rebuilding ONGA: {reason}")
            total_terms += build_onga_embeddings(
                model, args.output_dir, schema_fingerprint
            )

    # Build ontology embeddings
    failed = {}
    if not args.onga_only:
        results, failed = build_ontology_embeddings(
            model,
            args.ontology_dir,
            args.output_dir,
            args.ontology,
            force=args.force,
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
